"""
Release Radar routes (MOO-80): the release list/calendar, per-release
ignore/unignore/grab actions, and the follow feed badge state.
"""
import calendar
import re
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

import src.crud.follows as follows_crud
from src.auth.jwthandler import get_current_user
from src.database.models import ArtistFollows, Releases
from src.schemas.follows import (
    CalendarDayOut,
    CalendarResponse,
    FeedStateOut,
    GrabResponseOut,
    ReleaseListResponse,
    STATUSES,
)
from src.schemas.users import UserOutSchema
from src.security.ratelimit import rate_limit
from src.utils.pagination import decode_cursor, encode_cursor, keyset_filter

router = APIRouter(tags=["releases"])

_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_CALENDAR_CAP = 500


async def _get_release_or_404(release_id):
    release = await Releases.filter(id=release_id).prefetch_related("artist").first()
    if release is None:
        raise HTTPException(status_code=404, detail="Release not found")
    return release


def _out(release):
    artist = release.artist
    return follows_crud.serialize_release(release, artist.id, artist.name)


@router.get("/releases", response_model=ReleaseListResponse)
async def list_releases(
    range: str = Query("upcoming"),
    status: Optional[str] = Query(None),
    followed_only: bool = Query(True),
    cursor: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    current_user: UserOutSchema = Depends(get_current_user),
) -> ReleaseListResponse:
    if range not in ("upcoming", "recent", "all"):
        raise HTTPException(
            status_code=422, detail="range must be one of: upcoming, recent, all"
        )
    if status is not None and status not in STATUSES:
        raise HTTPException(
            status_code=422,
            detail="status must be one of: {}".format(", ".join(STATUSES)),
        )

    query = Releases.all()
    if followed_only:
        artist_ids = list(
            await ArtistFollows.filter(user_id=current_user.id).values_list(
                "artist_id", flat=True
            )
        )
        if not artist_ids:
            return ReleaseListResponse(items=[], next_cursor=None)
        query = query.filter(artist_id__in=artist_ids)
    if status:
        query = query.filter(status=status)

    today = date.today()
    order = "asc"
    if range == "upcoming":
        query = query.filter(release_date__gte=today)
    elif range == "recent":
        query = query.filter(release_date__lt=today)
        order = "desc"
    else:
        order = "desc"

    if cursor:
        token = decode_cursor(cursor)
        if token["s"] != "release_date" or token["o"] != order:
            raise HTTPException(status_code=422, detail="Invalid cursor")
        release_date_val, last_id = token["k"]
        query = query.filter(
            keyset_filter(
                "release_date",
                order,
                datetime.fromisoformat(release_date_val).date(),
                last_id,
            )
        )

    prefix = "" if order == "asc" else "-"
    rows = (
        await query.order_by(prefix + "release_date", prefix + "id")
        .limit(limit)
        .prefetch_related("artist")
    )
    items = [_out(row) for row in rows]
    next_cursor = None
    if len(items) == limit:
        last = rows[-1]
        next_cursor = encode_cursor(
            "release_date", order, [last.release_date.isoformat(), last.id]
        )
    return ReleaseListResponse(items=items, next_cursor=next_cursor)


@router.get("/releases/calendar", response_model=CalendarResponse)
async def release_calendar(
    month: Optional[str] = Query(None),
    followed_only: bool = Query(True),
    current_user: UserOutSchema = Depends(get_current_user),
) -> CalendarResponse:
    today = date.today()
    month = month or "{:04d}-{:02d}".format(today.year, today.month)
    if not _MONTH_RE.match(month):
        raise HTTPException(status_code=422, detail="month must be YYYY-MM")
    year, mon = (int(part) for part in month.split("-"))
    first_day = date(year, mon, 1)
    last_day = date(year, mon, calendar.monthrange(year, mon)[1])

    query = Releases.filter(release_date__gte=first_day, release_date__lte=last_day)
    if followed_only:
        artist_ids = list(
            await ArtistFollows.filter(user_id=current_user.id).values_list(
                "artist_id", flat=True
            )
        )
        if not artist_ids:
            return CalendarResponse(month=month, days=[], truncated=False)
        query = query.filter(artist_id__in=artist_ids)

    rows = (
        await query.order_by("release_date", "id")
        .limit(_CALENDAR_CAP + 1)
        .prefetch_related("artist")
    )
    truncated = len(rows) > _CALENDAR_CAP
    rows = rows[:_CALENDAR_CAP]

    by_day = {}
    for row in rows:
        by_day.setdefault(row.release_date, []).append(_out(row))
    days = [
        CalendarDayOut(date=day, releases=releases)
        for day, releases in sorted(by_day.items())
    ]
    return CalendarResponse(month=month, days=days, truncated=truncated)


@router.post("/releases/{release_id}/ignore")
async def ignore_release(
    release_id: int,
    request: Request,
    current_user: UserOutSchema = Depends(get_current_user),
):
    release = await _get_release_or_404(release_id)
    await follows_crud.ensure_follower_or_403(release, current_user)
    if release.status == "in_library":
        raise HTTPException(status_code=409, detail="Release is already in the library")
    if release.status != "ignored":
        release = await follows_crud.ignore_release(
            release, current_user, request=request
        )
    return _out(release)


@router.post("/releases/{release_id}/unignore")
async def unignore_release(
    release_id: int,
    request: Request,
    current_user: UserOutSchema = Depends(get_current_user),
):
    release = await _get_release_or_404(release_id)
    await follows_crud.ensure_follower_or_403(release, current_user)
    if release.status != "ignored":
        raise HTTPException(status_code=409, detail="Release is not ignored")
    release = await follows_crud.unignore_release(
        release, release.artist, request=request, actor=current_user
    )
    return _out(release)


@router.post(
    "/releases/{release_id}/grab", response_model=GrabResponseOut, status_code=202
)
async def grab_release(
    release_id: int,
    request: Request,
    current_user: UserOutSchema = Depends(get_current_user),
) -> GrabResponseOut:
    await rate_limit("release_grab", str(current_user.id), 10, 60)
    release = await _get_release_or_404(release_id)
    await follows_crud.ensure_follower_or_403(release, current_user)
    if release.status in ("in_library", "grabbed"):
        raise HTTPException(
            status_code=409, detail="Release is already {}".format(release.status)
        )
    release, request_ids = await follows_crud.grab_release(
        release, release.artist, current_user, request=request
    )
    return GrabResponseOut(release=_out(release), request_ids=request_ids)


@router.get("/follows/feed/state", response_model=FeedStateOut)
async def feed_state(
    current_user: UserOutSchema = Depends(get_current_user),
) -> FeedStateOut:
    count = await follows_crud.unseen_count(current_user.id)
    return FeedStateOut(unseen_count=count)


@router.post("/follows/feed/seen", response_model=FeedStateOut)
async def mark_feed_seen(
    current_user: UserOutSchema = Depends(get_current_user),
) -> FeedStateOut:
    await follows_crud.mark_feed_seen(current_user.id)
    return FeedStateOut(unseen_count=0)
