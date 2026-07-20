"""
CRUD for admin content management and moderation (MOO-71).

Metadata edits are DB-side only: the files on the read-only /music volume are
never rewritten. Uploaded tracks are streamed onto the managed, sharded
/library volume (MOO-77) and parsed with the same extraction pipeline as the
library; legacy rows on the /uploads volume keep serving.
"""
import os

from fastapi import HTTPException
from tortoise.exceptions import IntegrityError
from tortoise.functions import Count

import src.crud.songs as songs_crud
from src.analysis import dispatch
from src.database.models import Downloads, Songs
from src.extract import musicfiles
from src.schemas.songs import song_to_schema
from src.search import outbox
from src.telemetry import events
from src.utils import storage
from src.utils.normalize import normalize_artist, normalize_title

CONTENT_STATUSES = ["published", "draft", "pending", "rejected"]


def _validate_status(value):
    if value not in CONTENT_STATUSES:
        raise HTTPException(
            status_code=422,
            detail="status must be one of: {}".format(", ".join(CONTENT_STATUSES)),
        )


async def _download_counts(song_ids):
    """A {song_id: download_count} map for the given songs, in one query."""
    if not song_ids:
        return {}
    rows = (
        await Downloads.filter(song_id__in=list(song_ids))
        .annotate(count=Count("id"))
        .group_by("song_id")
        .values("song_id", "count")
    )
    return {row["song_id"]: int(row["count"]) for row in rows}


async def _enrichment_statuses(song_ids):
    """A {song_id: status} map of Beatport enrichment rows (MOO-85), one
    grouped query per page -- same pattern as _download_counts."""
    if not song_ids:
        return {}
    from src.database.models import SongEnrichment

    rows = await SongEnrichment.filter(
        song_id__in=list(song_ids), provider="beatport"
    ).values("song_id", "status")
    return {row["song_id"]: row["status"] for row in rows}


def _admin_song_dict(song, download_count=0, enrichment_status=None):
    """An AdminSongSchema dict: the member song shape plus the admin fields."""
    data = song_to_schema(song).dict()
    data["status"] = song.status
    data["source"] = song.source
    data["version_status"] = song.version_status
    data["recording_id"] = song.recording_id
    data["uploaded_by_id"] = song.uploaded_by_id
    uploader = song.uploaded_by if song.uploaded_by_id else None
    data["uploaded_by_username"] = uploader.username if uploader else None
    data["download_count"] = download_count
    data["field_locks"] = song.field_locks
    data["beatport_track_id"] = song.beatport_track_id
    data["enrichment_status"] = enrichment_status
    # The custom ID3 frames are editable in the admin metadata editor (MOO-82)
    # but stay out of the member song shape.
    data["txxx_frames"] = song.txxx_frames
    return data


async def _page(query, page, page_size):
    """Serialize a page of the content query to admin song dicts, newest first."""
    total = await query.count()
    songs = (
        await query.order_by("-created_at", "-id")
        .offset((page - 1) * page_size)
        .limit(page_size)
        .prefetch_related("uploaded_by")
    )
    song_ids = [s.id for s in songs]
    counts = await _download_counts(song_ids)
    enrichment_statuses = await _enrichment_statuses(song_ids)
    items = [
        _admin_song_dict(s, counts.get(s.id, 0), enrichment_statuses.get(s.id))
        for s in songs
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


async def list_content(q=None, status=None, page=1, page_size=50):
    """Every song (any status) for the admin content table, with search/filter."""
    query = songs_crud.filter_songs(search=q, published_only=False)
    if status:
        _validate_status(status)
        query = query.filter(status=status)
    return await _page(query, page, page_size)


async def moderation_queue(page=1, page_size=50):
    """The pending submission queue."""
    query = Songs.filter(status="pending")
    return await _page(query, page, page_size)


async def _get_song(song_id):
    song = await Songs.get_or_none(id=song_id).prefetch_related("uploaded_by")
    if song is None:
        raise HTTPException(status_code=404, detail="Song not found")
    return song


async def set_status(song_id, status):
    """Set a song's moderation status (publish/draft/pending/rejected)."""
    _validate_status(status)
    song = await _get_song(song_id)
    song.status = status
    await song.save(update_fields=["status", "modified_at"])
    # Publish/unpublish changes what /search may surface (MOO-79).
    await outbox.enqueue_song_upsert(song.id)
    await outbox.nudge_drain()
    counts = await _download_counts([song.id])
    return _admin_song_dict(song, counts.get(song.id, 0))


async def approve(song_id):
    """Approve a submission: publish it."""
    return await set_status(song_id, "published")


async def reject(song_id):
    """Reject a submission: mark it rejected (removes it from the queue)."""
    return await set_status(song_id, "rejected")


async def write_metadata(song, changes):
    """
    The one place a song's tag fields are written (MOO-82): set the values,
    keep the normalized identity truthful, lock the touched fields, re-index.
    Callers come through src/crud/tags.py, which adds the history entry.
    """
    if not changes:
        return song
    for field, value in changes.items():
        setattr(song, field, value)
    # Keep the normalized recording identity truthful (MOO-90).
    if "artist" in changes or "title" in changes:
        song.artist_norm = normalize_artist(song.artist)
        song.title_norm = normalize_title(song.title)[0]
    # Field locks (MOO-85 D4): every field a manual edit changes is now
    # DB-owned "manual" -- outranks any prior/future Beatport enrichment
    # and, together with the sync_songs_from_disk skip, survives the
    # next /music rescan (the MOO-71/72 quirk this stage fixes).
    locks = dict(song.field_locks or {})
    for field in changes:
        locks[field] = "manual"
    song.field_locks = locks
    await song.save()
    await outbox.enqueue_song_upsert(song.id)
    await outbox.nudge_drain()
    return song


async def edit_metadata(song_id, payload, actor=None, request=None):
    """
    Update a song's tags in the database only; never touch the file. Since
    MOO-82 the edit also lands in the song's revision history (who/when/
    old->new) and can be rolled back.
    """
    import src.crud.tags as tags_crud

    changes = payload if isinstance(payload, dict) else payload.dict(exclude_unset=True)
    song, _revision_id = await tags_crud.edit_song(
        song_id, changes, actor=actor, request=request
    )
    counts = await _download_counts([song.id])
    statuses = await _enrichment_statuses([song.id])
    return _admin_song_dict(song, counts.get(song.id, 0), statuses.get(song.id))


async def upload_track(upload_file, overrides, require_approval, user_id):
    """
    Stream an uploaded track into the sharded /library tree (atomic,
    content-addressed — MOO-77), extract its tags with the existing pipeline,
    apply any admin-provided metadata overrides, and create the song. When
    approval is required the track enters as pending.
    """
    # Derive the extension from the basename only, and confine it to a safe
    # charset so a crafted filename can never influence the storage path
    # (MOO-89 path confinement; the sharded path is content-addressed anyway).
    raw_name = os.path.basename((upload_file.filename or "").replace("\\", "/"))
    raw_ext = os.path.splitext(raw_name)[1].lstrip(".").lower()
    ext = "".join(c for c in raw_ext if c.isalnum())[:8] or "mp3"
    dest, sha256_hex, _size = await storage.store_stream(upload_file, "." + ext)
    try:
        record = await musicfiles.extract_music_file_info(dest)
    except Exception as error:
        _safe_remove(dest)
        raise HTTPException(
            status_code=400, detail="Could not read the uploaded file: {}".format(error)
        )

    # Analyzer pass-1 facts (MOO-87): not a Songs column, handed to dispatch
    # after the row exists.
    technical = record.pop("technical", None)
    for field, value in overrides.items():
        if value is not None:
            record[field] = value
    # Recompute the dedup key in case the admin corrected artist/title.
    record["dedup_key"] = musicfiles.build_dedup_key(record)
    record["artist_norm"] = normalize_artist(record["artist"])
    record["title_norm"] = normalize_title(record["title"])[0]
    record["checksum_sha256"] = sha256_hex
    record["source"] = "upload"
    record["status"] = "pending" if require_approval else "published"
    record["uploaded_by_id"] = user_id

    try:
        song = await Songs.create(**record)
    except IntegrityError:
        # Content addressing means a re-upload of identical bytes landed on
        # the SAME sharded path: only remove the file when no existing row
        # still references it.
        if not await Songs.filter(file_path=dest).exists():
            _safe_remove(dest)
        raise HTTPException(
            status_code=409, detail="That track is already in the library."
        )
    song = await _get_song(song.id)
    await outbox.enqueue_song_upsert(song.id)
    await outbox.nudge_drain()
    events.import_track(song, events.SOURCE_UPLOAD)
    # Analyzer hooks (MOO-87): pass-1 facts land now, pass 2 goes to
    # orp:heavy -- a fresh upload jumps a running bulk backfill by at most
    # one throttle window (D3 backpressure).
    await dispatch.ensure_analysis_row(song.id, technical)
    await dispatch.enqueue_analysis(song.id, user_id=user_id)
    # Beatport enrichment (MOO-85 D7): best-effort, gated on the
    # integrations.beatport_auto_enrich instance setting (default off).
    try:
        from src.enrichment.service import maybe_auto_enqueue

        await maybe_auto_enqueue([song.id], user_id=user_id)
    except Exception:
        pass
    counts = await _download_counts([song.id])
    return _admin_song_dict(song, counts.get(song.id, 0))


def _safe_remove(path):
    try:
        os.remove(path)
    except OSError:
        pass
