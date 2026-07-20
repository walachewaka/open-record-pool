"""
Our member-library routes: favorites, play events, download history and
quota, and the charts aggregates (MOO-65).
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from tortoise.functions import Count

import src.crud.library as crud
from src.auth.jwthandler import get_current_user
from src.database.models import Downloads, Favorites, PlayEvents, Songs
from src.schemas.library import (
    ChartEntry,
    ChartsResponse,
    DownloadListResponse,
    DownloadOutSchema,
    FavoriteToggleResponse,
    PlayEventResponse,
    QuotaResponse,
)
from src.schemas.songs import SongListResponse, song_to_schema
from src.schemas.users import UserOutSchema
from src.search import outbox
from src.telemetry import events

router = APIRouter()

CHART_MODES = ("most_downloaded", "most_played", "added_this_month")


async def _get_song_or_404(song_id):
    song = await Songs.get_or_none(id=song_id)
    if song is None:
        raise HTTPException(status_code=404, detail="Song not found")
    return song


@router.post("/songs/{song_id}/favorite", response_model=FavoriteToggleResponse)
async def toggle_favorite(
    song_id: int, current_user: UserOutSchema = Depends(get_current_user)
) -> FavoriteToggleResponse:
    """
    Toggles the current user's favorite flag on a song.
    """
    song = await _get_song_or_404(song_id)
    favorite = await Favorites.get_or_none(user_id=current_user.id, song_id=song.id)
    if favorite is not None:
        await favorite.delete()
        return FavoriteToggleResponse(song_id=song.id, is_favorite=False)
    await Favorites.create(user_id=current_user.id, song_id=song.id)
    return FavoriteToggleResponse(song_id=song.id, is_favorite=True)


@router.get("/favorites", response_model=SongListResponse)
async def list_favorites(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=300),
    current_user: UserOutSchema = Depends(get_current_user),
) -> SongListResponse:
    """
    The current user's favorite songs, most recently favorited first.
    """
    # Only surface published, canonical tracks to members (MOO-71, MOO-90).
    base = Favorites.filter(
        user_id=current_user.id,
        song__status="published",
        song__version_status="canonical",
    )
    total = await base.count()
    favorites = (
        await base.order_by("-created_at", "-id")
        .offset((page - 1) * page_size)
        .limit(page_size)
        .prefetch_related("song")
    )
    items = [song_to_schema(f.song, {f.song_id}) for f in favorites]
    return SongListResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("/songs/{song_id}/play", response_model=PlayEventResponse)
async def log_play_event(
    song_id: int, current_user: UserOutSchema = Depends(get_current_user)
) -> PlayEventResponse:
    """
    Logs that the current user started playback of a song, and returns the
    song's aggregate play count.
    """
    song = await _get_song_or_404(song_id)
    await PlayEvents.create(user_id=current_user.id, song_id=song.id)
    play_count = await PlayEvents.filter(song_id=song.id).count()
    # The doc's play_count changed (MOO-79); the drain coalesces bursts.
    await outbox.enqueue_song_upsert(song.id)
    await outbox.nudge_drain()
    # Telemetry is a dual write (MOO-83 D8): the PlayEvents row above stays the
    # authoritative counter behind the charts; this feeds the ES dashboards.
    events.play_start(current_user, song)
    return PlayEventResponse(song_id=song.id, play_count=play_count)


@router.get("/downloads", response_model=DownloadListResponse)
async def list_downloads(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=300),
    current_user: UserOutSchema = Depends(get_current_user),
) -> DownloadListResponse:
    """
    The current user's download history, newest first. Songs already in
    the history can be re-downloaded without spending quota.
    """
    base = Downloads.filter(user_id=current_user.id)
    total = await base.count()
    downloads = (
        await base.order_by("-downloaded_at", "-id")
        .offset((page - 1) * page_size)
        .limit(page_size)
        .prefetch_related("song")
    )
    favorites = await crud.favorite_song_ids(
        current_user.id, [d.song_id for d in downloads]
    )
    items = [
        DownloadOutSchema(
            id=d.id,
            format=d.format,
            counted_against_quota=d.counted_against_quota,
            downloaded_at=d.downloaded_at,
            song=song_to_schema(d.song, favorites),
        )
        for d in downloads
    ]
    return DownloadListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


@router.get("/downloads/quota", response_model=QuotaResponse)
async def get_download_quota(
    current_user: UserOutSchema = Depends(get_current_user),
) -> QuotaResponse:
    """
    The current user's monthly download quota: used and remaining.
    """
    return QuotaResponse(**await crud.quota_status(current_user.id))


@router.get("/charts", response_model=ChartsResponse)
async def get_charts(
    mode: str = Query(
        "most_downloaded", description=f"One of: {', '.join(CHART_MODES)}"
    ),
    limit: int = Query(20, ge=1, le=100),
    current_user: UserOutSchema = Depends(get_current_user),
) -> ChartsResponse:
    """
    Ranked charts over the library (MOO-65): most downloaded, most played,
    or added this month. The metric is the download count, the play count,
    or the days since the song was added, respectively.
    """
    if mode not in CHART_MODES:
        raise HTTPException(
            status_code=422, detail=f"mode must be one of: {', '.join(CHART_MODES)}"
        )

    # Charts only rank published, canonical tracks (MOO-71, MOO-90).
    now = datetime.now(timezone.utc)
    if mode == "most_downloaded":
        songs = (
            await Songs.filter(status="published", version_status="canonical")
            .annotate(metric=Count("downloads"))
            .filter(metric__gt=0)
            .order_by("-metric", "id")
            .limit(limit)
        )
        metrics = [int(s.metric) for s in songs]
    elif mode == "most_played":
        songs = (
            await Songs.filter(status="published", version_status="canonical")
            .annotate(metric=Count("play_events"))
            .filter(metric__gt=0)
            .order_by("-metric", "id")
            .limit(limit)
        )
        metrics = [int(s.metric) for s in songs]
    else:  # added_this_month
        songs = (
            await Songs.filter(
                created_at__gte=crud.current_month_start(),
                status="published",
                version_status="canonical",
            )
            .order_by("-created_at", "id")
            .limit(limit)
        )
        metrics = [
            max((now - s.created_at.astimezone(timezone.utc)).days, 0) for s in songs
        ]

    favorites = await crud.favorite_song_ids(current_user.id, [s.id for s in songs])
    entries = [
        ChartEntry(rank=i + 1, metric=metric, song=song_to_schema(song, favorites))
        for i, (song, metric) in enumerate(zip(songs, metrics))
    ]
    return ChartsResponse(mode=mode, entries=entries)
