"""
Admin artist-follows API (MOO-80): bounded aggregate overview + a manual
poll trigger (202 job envelope -- the Beatport/MusicBrainz call always
happens inside the worker job, never here, MOO-77 D2).
"""
from fastapi import APIRouter, Depends, HTTPException

from src.auth.permissions import require_permission
from src.database import models
from src.jobs.queue import QUEUE_DEFAULT, submit_job
from src.jobs.tasks_follows import poll_release_sources_pending
from src.schemas.follows import AdminFollowsOverviewOut
from src.schemas.jobs import JobOut
from src.schemas.users import UserOutSchema
from src.sources.registry import get_release_sources

router = APIRouter(prefix="/admin/follows", tags=["admin: follows"])


@router.get("/overview", response_model=AdminFollowsOverviewOut)
async def overview(
    current_user: UserOutSchema = Depends(require_permission("view_reports")),
) -> AdminFollowsOverviewOut:
    followed_artists = await models.ArtistFollows.all().values_list(
        "artist_id", flat=True
    )
    resolved_artists = await models.Artists.filter(
        beatport_artist_id__isnull=False
    ).count()
    releases_total = await models.Releases.all().count()
    by_status = {}
    for status in ("missing", "in_library", "grabbed", "ignored"):
        by_status[status] = await models.Releases.filter(status=status).count()
    last_poll = (
        await models.Jobs.filter(kind="poll_release_sources", status="succeeded")
        .order_by("-finished_at")
        .first()
    )
    sources = get_release_sources()
    return AdminFollowsOverviewOut(
        followed_artists=len(set(followed_artists)),
        resolved_artists=resolved_artists,
        releases_total=releases_total,
        releases_by_status=by_status,
        last_poll_at=(last_poll.finished_at if last_poll else None),
        sources_configured=[source.name for source in sources],
    )


@router.post("/poll", response_model=JobOut, status_code=202)
async def trigger_poll(
    current_user: UserOutSchema = Depends(require_permission("site_settings")),
) -> JobOut:
    if await poll_release_sources_pending():
        raise HTTPException(
            status_code=409, detail="A release poll is already queued or running"
        )
    return await submit_job(
        "poll_release_sources", user_id=current_user.id, queue=QUEUE_DEFAULT
    )
