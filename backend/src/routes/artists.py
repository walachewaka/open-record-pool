"""
Artist follow routes (MOO-80): browse/search library artists, artist detail
(+ its library tracks and recent releases), and the follow lifecycle.
`/artists/search` is declared before `/artists/{artist_id}` so the literal
path isn't shadowed by the int param (same trick as `/songs/genres`).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from tortoise.functions import Max

import src.crud.follows as follows_crud
import src.crud.library as library_crud
from src.auth.jwthandler import get_current_user
from src.database.models import ArtistFollows, Artists, Releases, Songs
from src.schemas.follows import (
    ArtistDetailOut,
    ArtistListResponse,
    ArtistOut,
    ArtistSearchResponse,
    ExternalArtistOut,
    FollowOut,
    FollowSettingsIn,
    FollowSettingsPatchIn,
)
from src.schemas.songs import SongListResponse, song_to_schema
from src.schemas.users import UserOutSchema
from src.security.ratelimit import rate_limit
from src.sources.registry import get_release_sources
from src.utils.pagination import decode_cursor, encode_cursor, keyset_filter

router = APIRouter(tags=["artists"])


async def _get_artist_or_404(artist_id):
    artist = await Artists.get_or_none(id=artist_id)
    if artist is None:
        raise HTTPException(status_code=404, detail="Artist not found")
    return artist


async def _follow_map(user_id, artist_ids):
    if not artist_ids:
        return {}
    rows = await ArtistFollows.filter(user_id=user_id, artist_id__in=artist_ids)
    return {row.artist_id: row for row in rows}


async def _latest_release_dates(artist_ids):
    if not artist_ids:
        return {}
    rows = (
        await Releases.filter(artist_id__in=artist_ids)
        .annotate(latest=Max("release_date"))
        .group_by("artist_id")
        .values("artist_id", "latest")
    )
    return {row["artist_id"]: row["latest"] for row in rows}


def _artist_out(artist, follow=None, latest_date=None):
    return ArtistOut(
        id=artist.id,
        name=artist.name,
        track_count=artist.track_count,
        beatport_artist_id=artist.beatport_artist_id,
        image_url=artist.image_url,
        is_followed=follow is not None,
        follow_settings=(follow.settings if follow else None),
        latest_release_date=latest_date,
    )


@router.get("/artists", response_model=ArtistListResponse)
async def list_artists(
    q: Optional[str] = Query(None, max_length=100),
    followed: Optional[bool] = Query(None),
    cursor: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    current_user: UserOutSchema = Depends(get_current_user),
) -> ArtistListResponse:
    query = Artists.all()
    if q:
        query = query.filter(name__icontains=q)
    if followed:
        followed_ids = list(
            await ArtistFollows.filter(user_id=current_user.id).values_list(
                "artist_id", flat=True
            )
        )
        query = query.filter(id__in=followed_ids)
    if cursor:
        token = decode_cursor(cursor)
        if token["s"] != "name" or token["o"] != "asc":
            raise HTTPException(status_code=422, detail="Invalid cursor")
        name_val, last_id = token["k"]
        query = query.filter(keyset_filter("name", "asc", name_val, last_id))

    rows = await query.order_by("name", "id").limit(limit)
    artist_ids = [a.id for a in rows]
    follows = await _follow_map(current_user.id, artist_ids)
    latest = await _latest_release_dates(artist_ids)
    items = [_artist_out(a, follows.get(a.id), latest.get(a.id)) for a in rows]
    next_cursor = None
    if len(items) == limit:
        last = rows[-1]
        next_cursor = encode_cursor("name", "asc", [last.name, last.id])
    return ArtistListResponse(items=items, next_cursor=next_cursor)


@router.get("/artists/search", response_model=ArtistSearchResponse)
async def search_artists(
    q: str = Query(..., min_length=2, max_length=100),
    current_user: UserOutSchema = Depends(get_current_user),
) -> ArtistSearchResponse:
    await rate_limit("artist_search", str(current_user.id), 10, 60)

    local_rows = await Artists.filter(name__icontains=q).order_by("name").limit(10)
    artist_ids = [a.id for a in local_rows]
    follows = await _follow_map(current_user.id, artist_ids)
    latest = await _latest_release_dates(artist_ids)
    local = [_artist_out(a, follows.get(a.id), latest.get(a.id)) for a in local_rows]

    sources = get_release_sources()
    external = []
    if sources:
        candidates = await sources[0].search_artists(q)
        for candidate in candidates[:10]:
            existing = await Artists.get_or_none(
                name_norm=follows_crud.normalize_name(candidate.name)
            )
            external.append(
                ExternalArtistOut(
                    source=candidate.source,
                    external_id=candidate.external_id,
                    name=candidate.name,
                    image_url=candidate.image_url,
                    artist_id=(existing.id if existing else None),
                )
            )
    return ArtistSearchResponse(
        local=local, external=external, sources_configured=bool(sources)
    )


@router.get("/artists/{artist_id}", response_model=ArtistDetailOut)
async def get_artist(
    artist_id: int,
    current_user: UserOutSchema = Depends(get_current_user),
) -> ArtistDetailOut:
    artist = await _get_artist_or_404(artist_id)
    follow = (await _follow_map(current_user.id, [artist_id])).get(artist_id)
    latest = (await _latest_release_dates([artist_id])).get(artist_id)
    release_rows = (
        await Releases.filter(artist_id=artist_id).order_by("-release_date").limit(10)
    )
    releases = [
        follows_crud.serialize_release(row, artist.id, artist.name)
        for row in release_rows
    ]
    base = _artist_out(artist, follow, latest)
    return ArtistDetailOut(**base.dict(), releases=releases)


@router.get("/artists/{artist_id}/tracks", response_model=SongListResponse)
async def get_artist_tracks(
    artist_id: int,
    cursor: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    current_user: UserOutSchema = Depends(get_current_user),
) -> SongListResponse:
    artist = await _get_artist_or_404(artist_id)
    query = Songs.filter(status="published", artist__iexact=artist.name)
    if cursor:
        token = decode_cursor(cursor)
        if token["s"] != "id" or token["o"] != "asc":
            raise HTTPException(status_code=422, detail="Invalid cursor")
        last_id = int(token["k"][-1])
        query = query.filter(keyset_filter("id", "asc", last_id, last_id))
    rows = await query.order_by("id").limit(limit)
    favorites = await library_crud.favorite_song_ids(
        current_user.id, [row.id for row in rows]
    )
    items = [song_to_schema(row, favorites) for row in rows]
    next_cursor = None
    if len(items) == limit:
        next_cursor = encode_cursor("id", "asc", [rows[-1].id, rows[-1].id])
    return SongListResponse(
        items=items, total=None, page=1, page_size=limit, next_cursor=next_cursor
    )


@router.post("/artists/{artist_id}/follow", response_model=FollowOut)
async def follow_artist(
    artist_id: int,
    payload: Optional[FollowSettingsIn] = None,
    current_user: UserOutSchema = Depends(get_current_user),
) -> FollowOut:
    await rate_limit("follow", str(current_user.id), 30, 60)
    artist = await _get_artist_or_404(artist_id)
    payload = payload or FollowSettingsIn()
    settings = {"auto_grab": payload.auto_grab, "notify": payload.notify}
    follow, created = await ArtistFollows.get_or_create(
        user_id=current_user.id, artist_id=artist.id, defaults={"settings": settings}
    )
    if not created:
        follow.settings = settings
        await follow.save(update_fields=["settings"])
    return FollowOut(artist_id=artist.id, followed=True, settings=follow.settings)


@router.patch("/artists/{artist_id}/follow", response_model=FollowOut)
async def update_follow_settings(
    artist_id: int,
    payload: FollowSettingsPatchIn,
    current_user: UserOutSchema = Depends(get_current_user),
) -> FollowOut:
    follow = await ArtistFollows.filter(
        user_id=current_user.id, artist_id=artist_id
    ).first()
    if follow is None:
        raise HTTPException(status_code=404, detail="Not following this artist")
    settings = dict(follow.settings or {})
    if payload.auto_grab is not None:
        settings["auto_grab"] = payload.auto_grab
    if payload.notify is not None:
        settings["notify"] = payload.notify
    follow.settings = settings
    await follow.save(update_fields=["settings"])
    return FollowOut(artist_id=artist_id, followed=True, settings=follow.settings)


@router.delete("/artists/{artist_id}/follow", response_model=FollowOut)
async def unfollow_artist(
    artist_id: int,
    current_user: UserOutSchema = Depends(get_current_user),
) -> FollowOut:
    await ArtistFollows.filter(user_id=current_user.id, artist_id=artist_id).delete()
    return FollowOut(artist_id=artist_id, followed=False, settings=None)
