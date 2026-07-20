"""
Read-side CRUD for the admin Beatport enrichment surface (MOO-85): the
keyset-paginated review queue with batched song embeds (never N+1 --
MOO-77 D6), and row serialization for the per-song detail route (the MOO-82
consumption contract).
"""
from fastapi import HTTPException
from tortoise.expressions import Q

from src.database.models import Songs, SongEnrichment
from src.utils.pagination import decode_cursor, encode_cursor

STATUSES = ("pending", "applied", "needs_review", "no_match", "rejected", "error")

_BATCH = 1000


def _chunks(values, size=_BATCH):
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _song_mini(song):
    if song is None:
        return None
    return {
        "id": song.id,
        "title": song.title,
        "artist": song.artist,
        "album": song.album,
        "genre": song.genre,
        "label": song.label,
        "year": song.year,
        "bpm": song.bpm,
        "musical_key": song.musical_key,
        "duration_seconds": song.duration_seconds,
        "field_locks": song.field_locks,
    }


def row_dict(row, song=None):
    return {
        "id": row.id,
        "song_id": row.song_id,
        "provider": row.provider,
        "status": row.status,
        "match_method": row.match_method,
        "confidence": row.confidence,
        "beatport_track_id": row.beatport_track_id,
        "beatport_release_id": row.beatport_release_id,
        "beatport_artist_ids": row.beatport_artist_ids,
        "payload": row.payload,
        "candidates": row.candidates,
        "fields_applied": row.fields_applied,
        "tag_snapshot": row.tag_snapshot,
        "error": row.error,
        "reviewed_by_id": row.reviewed_by_id,
        "matched_at": row.matched_at,
        "applied_at": row.applied_at,
        "created_at": row.created_at,
        "modified_at": row.modified_at,
        "song": _song_mini(song),
    }


async def _songs_map(song_ids):
    songs = {}
    for chunk in _chunks(list(song_ids)):
        for song in await Songs.filter(id__in=chunk):
            songs[song.id] = song
    return songs


def _validate_status(status):
    if status is not None and status not in STATUSES:
        raise HTTPException(
            status_code=422,
            detail="status must be one of: {}".format(", ".join(STATUSES)),
        )


def _cursor_last_id(cursor):
    token = decode_cursor(cursor)
    if token["s"] != "id" or token["o"] != "desc":
        raise HTTPException(status_code=422, detail="Invalid cursor")
    try:
        return int(token["k"][-1])
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Invalid cursor")


async def list_queue(status="needs_review", q=None, cursor=None, limit=50):
    """One keyset page (id DESC) of the review queue, optionally filtered by
    status and a free-text substring over the song's title/artist."""
    _validate_status(status)
    query = SongEnrichment.filter(provider="beatport")
    if status:
        query = query.filter(status=status)
    if q:
        matching_ids = await Songs.filter(
            Q(title__icontains=q) | Q(artist__icontains=q)
        ).values_list("id", flat=True)
        query = query.filter(song_id__in=list(matching_ids)[:_BATCH] or [-1])
    if cursor:
        query = query.filter(id__lt=_cursor_last_id(cursor))
    rows = await query.order_by("-id").limit(limit)
    songs = await _songs_map([row.song_id for row in rows])
    items = [row_dict(row, songs.get(row.song_id)) for row in rows]
    next_cursor = None
    if len(rows) == limit:
        next_cursor = encode_cursor("id", "desc", [rows[-1].id, rows[-1].id])
    return items, next_cursor


async def get_by_song(song_id):
    row = await SongEnrichment.get_or_none(song_id=song_id, provider="beatport")
    if row is None:
        raise HTTPException(status_code=404, detail="No enrichment for this song")
    song = await Songs.get_or_none(id=song_id)
    return row, row_dict(row, song)


async def get_by_id(enrichment_id):
    row = await SongEnrichment.get_or_none(id=enrichment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Enrichment row not found")
    song = await Songs.get_or_none(id=row.song_id)
    return row, row_dict(row, song)
