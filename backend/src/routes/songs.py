"""
Our songs routes: extraction into the database, library listing and search,
sample playback, release detail, and quota-enforced download.
"""
import os
import re
import time
from datetime import datetime
from typing import List, Optional

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from tortoise.functions import Count

import src.crud.library as library_crud
import src.crud.songs as crud
from src.auth.jwthandler import get_current_user
from src.auth.permissions import can_view_unpublished, require_permission
from src.database.models import (
    Downloads,
    Favorites,
    PlayEvents,
    Songs,
    TrackAnalysis,
)
from src.extract import musicfiles
from src.jobs.queue import submit_job
from src.jobs.tasks import scan_pending
from src.schemas.jobs import JobOut
from src.schemas.songs import (
    GenreStat,
    SongDetailResponse,
    SongListResponse,
    SongVersion,
    song_to_schema,
)
from src.schemas.users import UserOutSchema
from src.search import outbox
from src.telemetry import events
from src.utils import storage
from src.utils.pagination import decode_cursor, encode_cursor, keyset_filter


router = APIRouter()

# Keyset-paginable sorts (MOO-77): non-nullable columns only. Text-sorted
# deep browsing moves to Elasticsearch in MOO-79.
CURSOR_SORTS = {"id", "created_at"}

# Legacy offset pagination is capped at this row depth (MOO-77): OFFSET over
# a millions-row table reads and throws away every skipped row.
OFFSET_DEPTH_CAP = 10000

SORTABLE_FIELDS = {
    "id",
    "title",
    "artist",
    "album",
    "genre",
    "year",
    "bpm",
    "duration_seconds",
    "created_at",
}

# Aggregate and compound sorts (MOO-65). musical_key stays deliberately
# non-sortable: alphabetic key order is musically meaningless.
SPECIAL_SORTS = {"most_downloaded", "most_played", "genre_title"}

DOWNLOAD_FORMATS = ("mp3",)

STREAM_CHUNK_SIZE = 64 * 1024

_RANGE_PATTERN = re.compile(r"^bytes=(\d*)-(\d*)$")


@router.post("/songs/extract", response_model=JobOut, status_code=202)
async def extract_songs(
    current_user: UserOutSchema = Depends(require_permission("site_settings")),
) -> JobOut:
    """
    Enqueues a scan of the music volume that synchronizes the songs table
    with it (#5, #9) and returns the job envelope (MOO-77). Requires the
    site_settings permission: a full library scan is an instance-wide
    mutation. In inline mode (WORKERS_ENABLED=false) the returned job is
    already terminal with result set to the old ExtractionResult shape;
    otherwise poll GET /admin/jobs/{id}.
    """
    if await scan_pending():
        raise HTTPException(
            status_code=409, detail="A library scan is already queued or running"
        )
    return await submit_job("scan_library", user_id=current_user.id)


@router.get("/songs", response_model=SongListResponse)
async def list_songs(
    q: Optional[str] = Query(
        None,
        description=(
            "Free-text search on title, artist, album, genre, and label "
            "(#10, MOO-94); key- and BPM-shaped queries also match those "
            "fields (MOO-69)"
        ),
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=300),
    sort: str = Query(
        "artist",
        description="One of: {} (MOO-65)".format(
            ", ".join(sorted(SORTABLE_FIELDS | SPECIAL_SORTS))
        ),
    ),
    order: str = Query("asc", description="asc or desc"),
    bpm_min: Optional[float] = Query(None, description="Minimum BPM (MOO-65)"),
    bpm_max: Optional[float] = Query(None, description="Maximum BPM (MOO-65)"),
    key: Optional[str] = Query(
        None,
        description="Musical key filter, Camelot ('8A') or raw notation (MOO-65)",
    ),
    genre: Optional[List[str]] = Query(
        None, description="Genre filter, repeatable for multi-select (MOO-65)"
    ),
    cursor: Optional[str] = Query(
        None,
        description=(
            "Keyset cursor (MOO-77). Empty for the first page; pass the "
            "next_cursor of the previous page after that. Cursor mode "
            "supports sort=id or created_at only."
        ),
    ),
    limit: Optional[int] = Query(
        None, ge=1, le=100, description="Page size in cursor mode (MOO-77)"
    ),
    current_user: UserOutSchema = Depends(get_current_user),
) -> SongListResponse:
    """
    Lists the songs in the library, paginated (#6), with an optional
    free-text search (#10) and the extended filters and sorts (MOO-65).
    Passing cursor and/or limit switches to keyset pagination (MOO-77):
    the response carries next_cursor instead of total, and page depth is
    unlimited. Offset mode is capped at row 10000.
    """
    if sort not in SORTABLE_FIELDS and sort not in SPECIAL_SORTS:
        raise HTTPException(
            status_code=422,
            detail="sort must be one of: {}".format(
                ", ".join(sorted(SORTABLE_FIELDS | SPECIAL_SORTS))
            ),
        )
    if order not in ("asc", "desc"):
        raise HTTPException(status_code=422, detail="order must be 'asc' or 'desc'")

    query = crud.filter_songs(
        search=q, bpm_min=bpm_min, bpm_max=bpm_max, key=key, genres=genre
    )
    # Telemetry (MOO-83): a browse is not a search -- only a query or a filter
    # counts, so the zero-result panels stay meaningful.
    started = time.monotonic()
    filters = {"bpm_min": bpm_min, "bpm_max": bpm_max, "key": key, "genre": genre}

    if cursor is not None or limit is not None:
        response = await _list_songs_cursor(
            query, sort, order, cursor, limit or 50, current_user
        )
        _emit_search(current_user, q, filters, response, started)
        return response

    if page * page_size > OFFSET_DEPTH_CAP:
        raise HTTPException(
            status_code=422,
            detail=("Pagination depth beyond 10000 rows requires cursor pagination"),
        )

    total = await query.count()
    prefix = "" if order == "asc" else "-"
    if sort == "most_downloaded":
        page_query = query.annotate(metric=Count("downloads")).order_by(
            prefix + "metric", "id"
        )
    elif sort == "most_played":
        page_query = query.annotate(metric=Count("play_events")).order_by(
            prefix + "metric", "id"
        )
    elif sort == "genre_title":
        page_query = query.order_by(prefix + "genre", prefix + "title", "id")
    elif sort == "bpm":
        # Coalesced tag-then-detected order (MOO-87 D5): filter_songs
        # annotates bpm_eff, backed by the migration-10 expression index.
        page_query = query.order_by(prefix + "bpm_eff", "id")
    else:
        page_query = query.order_by(prefix + sort, "id")
    songs = await page_query.offset((page - 1) * page_size).limit(page_size)
    favorites = await library_crud.favorite_song_ids(
        current_user.id, [s.id for s in songs]
    )
    items = [song_to_schema(s, favorites) for s in songs]
    response = SongListResponse(
        items=items, total=total, page=page, page_size=page_size
    )
    _emit_search(current_user, q, filters, response, started)
    return response


def _emit_search(current_user, q, filters, response, started):
    """One search.query event per filtered /songs listing (MOO-83)."""
    if not q and not any(value is not None for value in filters.values()):
        return
    count = response.total if response.total is not None else len(response.items)
    events.search_query(
        current_user,
        query=q,
        filters=filters,
        result_count=count,
        duration_ms=int((time.monotonic() - started) * 1000),
        engine="pg",
    )


async def _list_songs_cursor(query, sort, order, cursor, limit, current_user):
    """
    Keyset pagination over the filtered song query (MOO-77): stable
    (sort_col, id) tuple ordering, no COUNT(*), no OFFSET. Only non-nullable
    sort columns are supported.
    """
    if sort not in CURSOR_SORTS:
        raise HTTPException(
            status_code=422,
            detail="cursor pagination supports sort=id or created_at",
        )
    if cursor:
        token = decode_cursor(cursor)
        if token["s"] != sort or token["o"] != order or len(token["k"]) != 2:
            raise HTTPException(status_code=422, detail="Invalid cursor")
        raw_value, raw_id = token["k"]
        try:
            last_id = int(raw_id)
            if sort == "id":
                sort_value = int(raw_value)
            else:
                sort_value = datetime.fromisoformat(str(raw_value))
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="Invalid cursor")
        query = query.filter(keyset_filter(sort, order, sort_value, last_id))
    prefix = "" if order == "asc" else "-"
    songs = await query.order_by(prefix + sort, prefix + "id").limit(limit)
    favorites = await library_crud.favorite_song_ids(
        current_user.id, [s.id for s in songs]
    )
    items = [song_to_schema(s, favorites) for s in songs]
    next_cursor = None
    if len(songs) == limit:
        last = songs[-1]
        raw_value = last.id if sort == "id" else last.created_at.isoformat()
        next_cursor = encode_cursor(sort, order, [raw_value, last.id])
    return SongListResponse(
        items=items, total=None, page=1, page_size=limit, next_cursor=next_cursor
    )


@router.get(
    "/songs/genres",
    response_model=List[str],
    dependencies=[Depends(get_current_user)],
)
async def list_genres() -> List[str]:
    """
    The distinct genres present in the library, alphabetically. Feeds the
    genre-chip row of the Browse view (MOO-66). Declared before the
    /songs/{song_id} route so it is not shadowed by the int path param.
    """
    genres = (
        await Songs.filter(
            genre__isnull=False, status="published", version_status="canonical"
        )
        .distinct()
        .values_list("genre", flat=True)
    )
    return sorted((genre for genre in genres if genre), key=str.lower)


@router.get(
    "/songs/genres/stats",
    response_model=List[GenreStat],
    dependencies=[Depends(get_current_user)],
)
async def list_genre_stats() -> List[GenreStat]:
    """
    The distinct genres present in the library with their track counts,
    alphabetically. Feeds the genre tiles of the Genres view (MOO-69).
    Declared before the /songs/{song_id} routes like /songs/genres.
    """
    rows = (
        await Songs.filter(
            genre__isnull=False, status="published", version_status="canonical"
        )
        .annotate(track_count=Count("id"))
        .group_by("genre")
        .values("genre", "track_count")
    )
    stats = [GenreStat(**row) for row in rows if row["genre"]]
    return sorted(stats, key=lambda stat: stat.genre.lower())


@router.get("/songs/{song_id}", response_model=SongDetailResponse)
async def get_song_detail(
    song_id: int, current_user: UserOutSchema = Depends(get_current_user)
) -> SongDetailResponse:
    """
    The release-detail view of one song (MOO-65): tags, aggregate download
    and play counts, and the versions/formats list. The library holds a
    single MP3 file per song today, so there is one "Original / MP3" version;
    the shape is ready for future versions and formats.
    """
    song = await Songs.get_or_none(id=song_id)
    if song is None:
        raise HTTPException(status_code=404, detail="Song not found")
    await _ensure_song_visible(song, current_user)
    download_count = await Downloads.filter(song_id=song.id).count()
    play_count = await PlayEvents.filter(song_id=song.id).count()
    is_favorite = await Favorites.filter(
        user_id=current_user.id, song_id=song.id
    ).exists()
    data = song_to_schema(song, {song.id} if is_favorite else None).dict()
    data["download_count"] = download_count
    data["play_count"] = play_count
    # Tag-vs-analysis disagreement flags (MOO-87 D5), null until pass 2 ran.
    analysis = await TrackAnalysis.filter(song_id=song.id).values(
        "bpm_mismatch", "key_mismatch"
    )
    if analysis:
        data["bpm_mismatch"] = analysis[0]["bpm_mismatch"]
        data["key_mismatch"] = analysis[0]["key_mismatch"]
    # Recording pointers (MOO-90): canonical_song_id is self for a canonical
    # version and the winner for a superseded one (admins auditioning a
    # losing version can redirect; members never reach this state).
    data["recording_id"] = song.recording_id
    if song.version_status == "canonical":
        data["canonical_song_id"] = song.id
    elif song.recording_id:
        canonical_id = await Songs.filter(
            recording_id=song.recording_id, version_status="canonical"
        ).values_list("id", flat=True)
        data["canonical_song_id"] = canonical_id[0] if canonical_id else None
    data["tags"] = [
        tag
        for tag in (song.genre, song.album, str(song.year) if song.year else None)
        if tag
    ]
    data["versions"] = [
        SongVersion(
            id="original-mp3",
            version="Original",
            format="MP3",
            bitrate_kbps=song.bitrate_kbps,
            file_size_bytes=song.file_size_bytes,
            stream_url=f"/songs/{song.id}/stream",
            download_url=f"/songs/{song.id}/download",
        )
    ]
    return SongDetailResponse(**data)


async def _ensure_song_visible(song, user):
    """
    Members only see published tracks (MOO-71) and only the canonical
    version of a recording (MOO-90). A draft/pending/rejected track or a
    superseded/quarantined version is a 404 unless the caller may view
    unpublished content (moderators/admins), which lets the admin surface
    preview and audition it.
    """
    hidden = song.status != "published" or song.version_status != "canonical"
    if hidden and not await can_view_unpublished(user):
        raise HTTPException(status_code=404, detail="Song not found")


async def _get_song_file(song_id: int):
    """
    Returns the song and the verified path of its file. Exactly three serving
    roots are allowed (MOO-77): the read-only /music library, the legacy
    /uploads volume (MOO-71, kept servable, no new writes), and the managed
    sharded /library volume where all new files land.
    """
    song = await Songs.get_or_none(id=song_id)
    if song is None:
        raise HTTPException(status_code=404, detail="Song not found")

    path = os.path.abspath(song.file_path)
    allowed_roots = (
        os.path.abspath(musicfiles.MUSIC_PATH),
        os.path.abspath(musicfiles.UPLOAD_PATH),
        os.path.abspath(storage.LIBRARY_PATH),
    )
    if not any(path.startswith(root + os.sep) for root in allowed_roots):
        raise HTTPException(
            status_code=404, detail="Song file is not on a served volume"
        )
    if not os.path.isfile(path):
        raise HTTPException(
            status_code=404,
            detail="Song file is missing from the media volume; run /songs/extract again",
        )
    return song, path


async def _read_file_range(path, start, end):
    """
    Yields the bytes of [path] from offset [start] to [end] (inclusive).
    """
    async with aiofiles.open(path, mode="rb") as f:
        await f.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            chunk = await f.read(min(STREAM_CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


@router.get("/songs/{song_id}/stream")
async def stream_song(
    song_id: int,
    request: Request,
    current_user: UserOutSchema = Depends(get_current_user),
):
    """
    Streams the song's audio for in-browser playback (#11).

    Honors single-range HTTP Range requests (206 Partial Content), which the
    HTML5 audio element uses for seeking.
    """
    song, path = await _get_song_file(song_id)
    await _ensure_song_visible(song, current_user)
    file_size = os.path.getsize(path)
    headers = {"Accept-Ranges": "bytes"}

    range_header = request.headers.get("range")
    if range_header:
        match = _RANGE_PATTERN.match(range_header.strip())
        if not match or match.group(0) == "bytes=-":
            raise HTTPException(
                status_code=416,
                detail="Invalid Range header",
                headers={"Content-Range": f"bytes */{file_size}"},
            )
        start_text, end_text = match.groups()
        if start_text == "":
            # Suffix range: the last N bytes of the file.
            start = max(file_size - int(end_text), 0)
            end = file_size - 1
        else:
            start = int(start_text)
            end = min(int(end_text), file_size - 1) if end_text else file_size - 1
        if start >= file_size or start > end:
            raise HTTPException(
                status_code=416,
                detail="Requested range not satisfiable",
                headers={"Content-Range": f"bytes */{file_size}"},
            )
        headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
        headers["Content-Length"] = str(end - start + 1)
        return StreamingResponse(
            _read_file_range(path, start, end),
            status_code=206,
            media_type="audio/mpeg",
            headers=headers,
        )

    headers["Content-Length"] = str(file_size)
    return StreamingResponse(
        _read_file_range(path, 0, file_size - 1),
        media_type="audio/mpeg",
        headers=headers,
    )


def _download_filename(song, path):
    """
    A friendly "Artist - Title.mp3" download name, falling back to the name
    of the file on disk.
    """
    if song.artist and song.title:
        name = f"{song.artist} - {song.title}.mp3"
    else:
        name = os.path.basename(path)
    # Strip characters that are unsafe in filenames or HTTP headers.
    return re.sub(r'[\\/:*?"<>|\r\n\x00]', "_", name)


@router.get("/songs/{song_id}/download")
async def download_song(
    song_id: int,
    format: str = Query("mp3", description=f"One of: {', '.join(DOWNLOAD_FORMATS)}"),
    current_user: UserOutSchema = Depends(get_current_user),
):
    """
    Downloads the song file (#13), records it in the user's download
    history, and enforces the monthly download quota (MOO-65). A song the
    user already downloaded before can be re-downloaded without spending
    quota (the history offers re-download).
    """
    if format not in DOWNLOAD_FORMATS:
        raise HTTPException(
            status_code=422,
            detail=f"format must be one of: {', '.join(DOWNLOAD_FORMATS)}",
        )
    song, path = await _get_song_file(song_id)
    await _ensure_song_visible(song, current_user)
    already_downloaded = await Downloads.filter(
        user_id=current_user.id, song_id=song.id
    ).exists()
    counted = not already_downloaded
    if counted:
        quota = library_crud.monthly_quota()
        if quota > 0:
            used = await library_crud.quota_used(current_user.id)
            if used >= quota:
                raise HTTPException(
                    status_code=429,
                    detail=f"Monthly download quota of {quota} exhausted",
                )
    await Downloads.create(
        user_id=current_user.id,
        song_id=song.id,
        format=format,
        counted_against_quota=counted,
    )
    # The doc's download_count changed (MOO-79); never blocks the response.
    await outbox.enqueue_song_upsert(song.id)
    await outbox.nudge_drain()
    events.download(current_user, song, format, counted)
    return FileResponse(
        path,
        media_type="audio/mpeg",
        filename=_download_filename(song, path),
    )
