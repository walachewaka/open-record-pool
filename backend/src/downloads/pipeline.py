"""
The download post-fetch pipeline (MOO-78 D5): probe -> pre-fetch dedup check ->
fetch -> tag-normalize -> store (sharded /library) -> Songs insert -> search
index -> analyzer (which auto-chains dedup). Runs inside the fetch_track worker
task on the heavy tier; updates both the download_requests row and its jobs row
as it advances. Cancellation is cooperative: the row status is re-checked
between stages and the run aborts if the user cancelled.
"""
import os
import shutil

import aiofiles

from src.database.models import DownloadRequests, Jobs, Songs
from src.downloads import service
from src.downloads.providers.base import ToolError, DOWNLOAD_MAX_FILE_MB
from src.utils import storage

WORKDIR_ROOT = os.path.join(storage.LIBRARY_PATH, "tmp", "fetch")


def _utcnow():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


async def _set_progress(request, job, value):
    request.progress = value
    await request.save(update_fields=["progress"])
    if job is not None:
        job.progress = value
        await job.save(update_fields=["progress"])


async def _is_cancelled(request_id):
    row = await DownloadRequests.get_or_none(id=request_id)
    return row is not None and row.status == "cancelled"


async def _terminal(request, job, status, song_id=None, error=None, error_kind=None):
    request.status = status
    request.finished_at = _utcnow()
    if song_id is not None:
        request.song_id = song_id
    if error is not None:
        request.error = str(error).replace("\x00", "")[:4000]
    if error_kind is not None:
        request.error_kind = error_kind
    if status in ("imported", "duplicate_skipped"):
        request.progress = 1.0
    await request.save()
    if job is not None:
        if status in ("imported", "duplicate_skipped"):
            job.status = "succeeded"
            job.progress = 1.0
            job.result = {
                "request_id": request.id,
                "status": status,
                "song_id": song_id,
            }
        elif status == "cancelled":
            job.status = "cancelled"
        else:
            job.status = "failed"
            job.error = request.error
        job.finished_at = _utcnow()
        await job.save()
    await _audit_terminal(request)
    await service.fire_completion_hooks(request)
    return request


async def _audit_terminal(request):
    from src.security import audit

    event = {
        "imported": "download.imported",
        "duplicate_skipped": "download.duplicate",
        "failed": "download.failed",
        "cancelled": "download.cancelled",
    }.get(request.status)
    if not event:
        return
    await audit.audit_event(
        event,
        actor=service._actor(request.requested_by_id),
        target_type="download",
        target_id=request.id,
        detail={"provider": request.provider, "song_id": request.song_id},
    )


async def _normalize_tags(path, meta, source_url):
    """Fill missing title/artist ID3 frames from the probe and stamp the source
    URL. Best-effort -- a tag failure never fails the import."""
    try:
        from mutagen.id3 import ID3, ID3NoHeaderError, TIT2, TPE1, TXXX

        try:
            tags = ID3(path)
        except ID3NoHeaderError:
            tags = ID3()
        if meta.get("title") and not tags.getall("TIT2"):
            tags.add(TIT2(encoding=3, text=[meta["title"]]))
        if meta.get("artist") and not tags.getall("TPE1"):
            tags.add(TPE1(encoding=3, text=[meta["artist"]]))
        tags.delall("TXXX:ORP_SOURCE_URL")
        tags.add(TXXX(encoding=3, desc="ORP_SOURCE_URL", text=[source_url]))
        tags.save(path)
    except Exception:
        pass


async def _prefetch_dedup(provider, external_id, meta):
    """MOO-90 pre-fetch library check: skip the download if the recording is
    already held and this source would not improve quality. Returns an existing
    song_id to skip to, or None to proceed."""
    try:
        from src.services import dedup
    except Exception:
        return None
    kwargs = dict(
        artist=meta.get("artist"),
        title=meta.get("title"),
        duration_seconds=meta.get("duration_seconds"),
        source=provider,
    )
    if provider == "spotify" and external_id:
        kwargs["spotify_id"] = external_id
    try:
        verdict = await dedup.check_library(**kwargs)
    except Exception:
        return None
    if verdict and verdict.get("found") and not verdict.get("would_improve"):
        return verdict.get("canonical_song_id")
    return None


async def run_fetch(job, request):
    """Execute the full fetch pipeline for one request. `job` may be None
    (defensive); both rows are advanced through their lifecycles here."""
    from src.downloads.providers import get_adapter

    if request.status in ("cancelled",) + service.TERMINAL_STATES:
        return request

    # 1. Re-validate the URL and re-check the gate (defense in depth, D5.2).
    from src.security.urlcheck import validate_provider_url
    from fastapi import HTTPException

    try:
        validate_provider_url(request.url)
    except HTTPException as error:
        return await _terminal(
            request, job, "failed", error=error.detail, error_kind="validation"
        )
    if not await service.downloads_enabled() or not await service.provider_enabled(
        request.provider
    ):
        return await _terminal(
            request,
            job,
            "failed",
            error="Provider disabled",
            error_kind="validation",
        )

    adapter = get_adapter(request.provider)
    if adapter is None:
        return await _terminal(
            request, job, "failed", error="No adapter", error_kind="tool"
        )

    request.status = "fetching"
    request.started_at = _utcnow()
    request.attempts = (request.attempts or 0) + 1
    await request.save(update_fields=["status", "started_at", "attempts"])
    if job is not None and job.status != "running":
        job.status = "running"
        job.started_at = _utcnow()
        await job.save(update_fields=["status", "started_at"])

    workdir = os.path.join(WORKDIR_ROOT, str(request.id))
    _reset_dir(workdir)
    try:
        await _set_progress(request, job, 0.05)

        # 2. Probe metadata.
        meta = await adapter.probe(request.url, request.external_id, workdir)
        request.source_metadata = _jsonable(meta)
        await request.save(update_fields=["source_metadata"])
        await _set_progress(request, job, 0.10)

        # 3. Pre-fetch dedup check (saves bandwidth).
        existing = await _prefetch_dedup(request.provider, request.external_id, meta)
        if existing is not None:
            return await _terminal(
                request,
                job,
                "duplicate_skipped",
                song_id=existing,
                error_kind="duplicate",
            )
        if await _is_cancelled(request.id):
            return await _reload_terminal(request, job, "cancelled")

        # 4. Fetch audio.
        async def on_progress(fraction):
            await _set_progress(
                request, job, 0.10 + 0.60 * max(0.0, min(1.0, fraction))
            )

        audio_path = await adapter.fetch(
            request.url, request.external_id, workdir, progress_cb=on_progress
        )
        audio_path = _confine(workdir, audio_path)
        _enforce_size(audio_path)
        if await _is_cancelled(request.id):
            return await _reload_terminal(request, job, "cancelled")

        request.status = "postprocessing"
        await request.save(update_fields=["status"])
        await _set_progress(request, job, 0.75)

        # 5. Normalize tags, then store (hash reflects the tagged bytes).
        await _normalize_tags(audio_path, meta, request.url)
        async with aiofiles.open(audio_path, "rb") as reader:
            dest, sha256_hex, _size = await storage.store_stream(reader, ".mp3")

        # 6. Byte-identical duplicate?
        existing_song = await Songs.filter(checksum_sha256=sha256_hex).first()
        if existing_song is not None:
            return await _terminal(
                request,
                job,
                "duplicate_skipped",
                song_id=existing_song.id,
                error_kind="duplicate",
            )

        # 7. Extract + insert the songs row (mirrors crud.content.upload_track).
        song = await _insert_song(dest, sha256_hex, request, meta)
        if song is None:  # dedup_key collision -> already in library
            existing_song = await _song_by_dedup(dest, sha256_hex, meta)
            return await _terminal(
                request,
                job,
                "duplicate_skipped",
                song_id=existing_song.id if existing_song else None,
                error_kind="duplicate",
            )
        await _set_progress(request, job, 0.90)

        # 8. Search index + analyzer (analyzer auto-chains dedup on pass 2).
        await _index_and_analyze(song, request.requested_by_id)

        return await _terminal(request, job, "imported", song_id=song.id)
    except ToolError as error:
        return await _terminal(
            request, job, "failed", error=error, error_kind=error.kind
        )
    except Exception as error:  # pragma: no cover - defensive
        return await _terminal(
            request, job, "failed", error=error, error_kind="postprocess"
        )
    finally:
        _remove_dir(workdir)


async def _insert_song(dest, sha256_hex, request, meta):
    from tortoise.exceptions import IntegrityError

    from src.extract import musicfiles
    from src.utils.normalize import normalize_artist, normalize_title

    record = await musicfiles.extract_music_file_info(dest)
    technical = record.pop("technical", None)
    # Prefer real tags; fall back to the provider metadata for identity.
    if not record.get("title") and meta.get("title"):
        record["title"] = meta["title"]
    if not record.get("artist") and meta.get("artist"):
        record["artist"] = meta["artist"]
    record["dedup_key"] = musicfiles.build_dedup_key(record)
    record["artist_norm"] = normalize_artist(record.get("artist"))
    record["title_norm"] = normalize_title(record.get("title"))[0]
    record["checksum_sha256"] = sha256_hex
    record["source"] = request.provider
    record["source_url"] = request.url
    record["status"] = "pending" if await service.require_approval() else "published"
    record["uploaded_by_id"] = request.requested_by_id
    try:
        song = await Songs.create(**record)
    except IntegrityError:
        return None
    song._technical = technical  # handed to the analyzer step
    return song


async def _song_by_dedup(dest, sha256_hex, meta):
    song = await Songs.filter(checksum_sha256=sha256_hex).first()
    if song is not None:
        return song
    from src.extract import musicfiles

    record = await musicfiles.extract_music_file_info(dest)
    record.pop("technical", None)
    if not record.get("title") and meta.get("title"):
        record["title"] = meta["title"]
    if not record.get("artist") and meta.get("artist"):
        record["artist"] = meta["artist"]
    return await Songs.filter(dedup_key=musicfiles.build_dedup_key(record)).first()


async def _index_and_analyze(song, user_id):
    from src.analysis import dispatch
    from src.search import outbox

    await outbox.enqueue_song_upsert(song.id)
    await outbox.nudge_drain()
    technical = getattr(song, "_technical", None)
    await dispatch.ensure_analysis_row(song.id, technical)
    await dispatch.enqueue_analysis(song.id, user_id=user_id)


async def _reload_terminal(request, job, status):
    fresh = await DownloadRequests.get(id=request.id)
    return await _terminal(fresh, job, status)


# --- workdir + file helpers ------------------------------------------------


def _reset_dir(path):
    _remove_dir(path)
    os.makedirs(path, mode=0o700, exist_ok=True)


def _remove_dir(path):
    try:
        shutil.rmtree(path)
    except (FileNotFoundError, OSError):
        pass


def _confine(workdir, path):
    """Realpath-verify the returned file lives inside workdir (SECURITY.md 4)."""
    root = os.path.realpath(workdir)
    full = os.path.realpath(path)
    if not (full == root or full.startswith(root + os.sep)):
        raise ToolError("tool wrote outside the workdir", transient=False, kind="tool")
    if not os.path.isfile(full):
        raise ToolError("tool produced no audio file", transient=False, kind="tool")
    return full


def _enforce_size(path):
    size_mb = os.path.getsize(path) / (1024 * 1024)
    if size_mb > DOWNLOAD_MAX_FILE_MB:
        raise ToolError(
            "downloaded file is {}MB (limit {}MB)".format(
                int(size_mb), DOWNLOAD_MAX_FILE_MB
            ),
            transient=False,
            kind="too_large",
        )


def _jsonable(meta):
    """Trim the raw provider dump so the JSON column stays reasonable."""
    trimmed = dict(meta or {})
    raw = trimmed.get("raw")
    if isinstance(raw, dict):
        trimmed["raw"] = {
            k: raw.get(k)
            for k in (
                "id",
                "title",
                "artist",
                "uploader",
                "album",
                "duration",
                "webpage_url",
            )
            if k in raw
        }
    return trimmed
