"""
The ingestion-analyzer routes (MOO-87): per-song waveform peaks and analysis
facts for members, plus the admin backfill trigger and the stats surface
that MOO-83 telemetry reads.

Security bar (MOO-89 / SECURITY.md): every route declares its guard (item
1); songs are global so member reads carry the same published-only
visibility as /songs/{id}/stream (item 2 n/a beyond that); the abuse-prone
backfill trigger is rate-limited (item 5) and audited (item 6); no
user-supplied name ever reaches a filesystem path -- waveform artifacts are
resolved purely from songs.checksum_sha256 through the sharded storage
resolver (item 4).
"""
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from tortoise.functions import Count

from src.analysis.versions import ANALYZER_VERSION
from src.auth.jwthandler import get_current_user
from src.auth.permissions import (
    can_view_unpublished,
    has_permission,
    require_permission,
)
from src.database.models import Jobs, Songs, TrackAnalysis
from src.jobs.queue import QUEUE_DEFAULT, submit_job
from src.jobs.tasks_analysis import backfill_pending
from src.schemas.analysis import (
    AnalysisStatsOut,
    BackfillRequest,
    TrackAnalysisOut,
    WaveformOut,
)
from src.schemas.jobs import JobOut
from src.schemas.users import UserOutSchema
from src.security import audit
from src.security.ratelimit import rate_limit
from src.utils import storage

router = APIRouter()

_WAVEFORM_CHUNK = 64 * 1024


async def _get_visible_song(song_id, user):
    """The song, 404ing unknown ids and unpublished tracks for members."""
    song = await Songs.get_or_none(id=song_id)
    if song is None:
        raise HTTPException(status_code=404, detail="Song not found")
    if song.status != "published" and not await can_view_unpublished(user):
        raise HTTPException(status_code=404, detail="Song not found")
    return song


@router.get("/songs/{song_id}/waveform", response_model=WaveformOut)
async def get_waveform(
    song_id: int,
    request: Request,
    current_user: UserOutSchema = Depends(get_current_user),
):
    """
    The persisted waveform peaks for a song (MOO-87 D6): the artifact JSON
    plus the song id. 404 until pass 2 has produced it -- the frontend
    falls back to its seeded bars. Content-addressed by the file checksum,
    so the payload is immutable: ETag + If-None-Match make repeats free.
    """
    song = await _get_visible_song(song_id, current_user)
    if not song.waveform_ready or not song.checksum_sha256:
        raise HTTPException(status_code=404, detail="Waveform not available")

    etag = '"{}"'.format(song.checksum_sha256)
    headers = {"Cache-Control": "private, max-age=86400", "ETag": etag}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)

    path = storage.artifact_path(song.checksum_sha256, "json", "waveform")
    if not os.path.isfile(path):
        # Self-heal: the artifact vanished (volume wipe); stop advertising it.
        song.waveform_ready = False
        await song.save(update_fields=["waveform_ready", "modified_at"])
        raise HTTPException(status_code=404, detail="Waveform not available")
    async with aiofiles.open(path, "rb") as handle:
        body = await handle.read()
    artifact = json.loads(body.decode("utf-8"))
    artifact["song_id"] = song.id
    return JSONResponse(content=artifact, headers=headers)


@router.get("/songs/{song_id}/analysis", response_model=TrackAnalysisOut)
async def get_analysis(
    song_id: int,
    current_user: UserOutSchema = Depends(get_current_user),
) -> TrackAnalysisOut:
    """
    Everything the analyzer derived for one song (MOO-87). Returns the
    pending shape (all-null, both statuses "pending") when analysis has not
    run yet, so clients can poll from the moment a song exists. tags_json
    is included only for callers with edit_metadata.
    """
    song = await _get_visible_song(song_id, current_user)
    row = await TrackAnalysis.get_or_none(song_id=song.id)
    if row is None:
        return TrackAnalysisOut(song_id=song.id)
    data = {
        field: getattr(row, field)
        for field in TrackAnalysisOut.__fields__
        if field != "song_id" and hasattr(row, field)
    }
    data["song_id"] = song.id
    if not await has_permission(current_user, "edit_metadata"):
        data["tags_json"] = None
    return TrackAnalysisOut(**data)


@router.post("/admin/analysis/backfill", response_model=JobOut, status_code=202)
async def start_backfill(
    request: Request,
    payload: Optional[BackfillRequest] = None,
    current_user: UserOutSchema = Depends(require_permission("site_settings")),
) -> JobOut:
    """
    Enqueue the analyze_library backfill (MOO-87 D3): every stale song gets
    an analyze_track job on orp:heavy, in throttled waves. 409 while one is
    already queued/running; rate limited (SECURITY.md 5) and audited (6).
    In inline mode the returned envelope is already terminal.
    """
    payload = payload or BackfillRequest()
    await rate_limit(
        "analysis_backfill", str(current_user.id), limit=3, window_seconds=300
    )
    if await backfill_pending():
        raise HTTPException(
            status_code=409,
            detail="An analysis backfill is already queued or running",
        )
    await audit.audit_event(
        "analysis.backfill_started",
        request=request,
        actor=current_user,
        target_type="analysis",
        detail=payload.dict(exclude_none=True),
    )
    return await submit_job(
        "analyze_library",
        payload=payload.dict(exclude_none=True),
        user_id=current_user.id,
        queue=QUEUE_DEFAULT,
    )


@router.get("/admin/analysis/stats", response_model=AnalysisStatsOut)
async def analysis_stats(
    current_user: UserOutSchema = Depends(require_permission("view_reports")),
) -> AnalysisStatsOut:
    """
    Analyzer coverage and queue health (MOO-87), computed from grouped
    counts only -- no per-row scans at millions-of-tracks scale. Queue depth
    and throughput feed the MOO-83 telemetry dashboards.
    """
    tracks_total = await Songs.all().count()
    by_status = {"pending": 0, "running": 0, "succeeded": 0, "failed": 0}
    grouped = (
        await TrackAnalysis.all()
        .annotate(count=Count("id"))
        .group_by("pass2_status")
        .values("pass2_status", "count")
    )
    for row in grouped:
        if row["pass2_status"] in by_status:
            by_status[row["pass2_status"]] = int(row["count"])
    waveforms = await TrackAnalysis.filter(waveform_peaks_count__isnull=False).count()
    fingerprints = await TrackAnalysis.filter(fingerprint__isnull=False).count()
    heavy_queued = await Jobs.filter(kind="analyze_track", status="queued").count()
    heavy_running = await Jobs.filter(kind="analyze_track", status="running").count()
    hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    succeeded_last_hour = await Jobs.filter(
        kind="analyze_track", status="succeeded", finished_at__gte=hour_ago
    ).count()
    return AnalysisStatsOut(
        tracks_total=tracks_total,
        analyzed=by_status["succeeded"],
        pending=by_status["pending"] + max(tracks_total - sum(by_status.values()), 0),
        running=by_status["running"],
        failed=by_status["failed"],
        waveforms=waveforms,
        fingerprints=fingerprints,
        heavy_jobs_queued=heavy_queued,
        heavy_jobs_running=heavy_running,
        succeeded_last_hour=succeeded_last_hour,
        throughput_per_min=round(succeeded_last_hour / 60.0, 2),
        analyzer_version=ANALYZER_VERSION,
    )
