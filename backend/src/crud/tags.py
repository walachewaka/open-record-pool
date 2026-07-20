"""
The metadata editor (MOO-82): tag edits with history, album-art management,
Beatport-backed per-field suggestions, and member edit proposals.

Everything is database-side. The /music mount is read-only, so an edit changes
the pool's metadata, not the file's bytes; writing tags back into the MP3s is
MOO-75 and is gated on the owner's writable-volume decision. What makes the
edit durable anyway is the MOO-85 field-lock mechanism: every field a curator
touches is locked "manual", and sync_songs_from_disk skips locked fields, so a
/music rescan can no longer clobber it (the old MOO-71/72 quirk).

Precedence, unchanged from MOO-85: manual > beatport > file tag.
"""
import uuid

from fastapi import HTTPException

from src.database.models import Songs, TagProposals, TagRevisions
from src.security import audit
from src.utils import artwork as art_utils

# Every field the editor may write. Anything outside this set is rejected --
# a proposal or a rollback can never reach status, source, file_path, ...
EDITABLE_FIELDS = (
    "title",
    "artist",
    "album",
    "album_artist",
    "composer",
    "genre",
    "label",
    "comment",
    "isrc",
    "year",
    "track_number",
    "disc_number",
    "bpm",
    "musical_key",
    "txxx_frames",
)

ART_FIELDS = ("artwork_path", "artwork_source", "artwork_width", "artwork_height")


async def get_song_or_404(song_id):
    song = await Songs.get_or_none(id=song_id).prefetch_related("uploaded_by")
    if song is None:
        raise HTTPException(status_code=404, detail="Song not found")
    return song


def _diff(song, changes):
    """{field: {"old": ..., "new": ...}} for the fields the edit really moves."""
    diff = {}
    for field, value in changes.items():
        old = getattr(song, field)
        if old != value:
            diff[field] = {"old": old, "new": value}
    return diff


async def record_revision(song, diff, actor=None, source="user", batch_id=None):
    """Append one history entry. No diff (a no-op edit) records nothing."""
    if not diff:
        return None
    return await TagRevisions.create(
        song_id=song.id,
        editor_id=getattr(actor, "id", None),
        editor_username=getattr(actor, "username", None),
        source=source,
        changes=diff,
        batch_id=batch_id,
    )


async def list_revisions(song_id, cursor=None, limit=50):
    """One keyset page of a song's edit history, newest first."""
    query = TagRevisions.filter(song_id=song_id)
    if cursor:
        query = query.filter(id__lt=int(cursor))
    rows = await query.order_by("-id").limit(limit + 1)
    next_cursor = str(rows[limit - 1].id) if len(rows) > limit else None
    return {
        "items": [_revision_dict(row) for row in rows[:limit]],
        "next_cursor": next_cursor,
    }


def _revision_dict(row):
    return {
        "id": row.id,
        "song_id": row.song_id,
        "editor_username": row.editor_username,
        "source": row.source,
        "changes": row.changes,
        "batch_id": row.batch_id,
        "created_at": row.created_at,
    }


async def apply_changes(song, changes, actor=None, source="user", batch_id=None):
    """
    The one write path every edit goes through (manual edit, batch, approved
    proposal, rollback): validate the field names, diff, write, lock, record a
    revision, and re-index. Returns the revision id (None for a no-op).
    """
    unknown = [f for f in changes if f not in EDITABLE_FIELDS]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail="Not an editable field: {}".format(", ".join(sorted(unknown))),
        )
    diff = _diff(song, changes)
    if not diff:
        return None
    # Delegate the actual write to the existing metadata path so the locking,
    # normalization (artist_norm/title_norm) and ES resync stay in ONE place.
    import src.crud.content as content_crud

    await content_crud.write_metadata(song, {f: c["new"] for f, c in diff.items()})
    revision = await record_revision(
        song, diff, actor=actor, source=source, batch_id=batch_id
    )
    return revision.id if revision else None


async def edit_song(song_id, changes, actor=None, source="user", request=None):
    """A single-song metadata edit: the admin PATCH and proposal-approval path."""
    song = await get_song_or_404(song_id)
    revision_id = await apply_changes(song, changes, actor=actor, source=source)
    if revision_id:
        await audit.audit_event(
            audit.CONTENT_METADATA_EDITED,
            request=request,
            actor=actor,
            target_type="song",
            target_id=song.id,
            detail={
                "fields": sorted(changes),
                "source": source,
                "revision": revision_id,
            },
        )
    return song, revision_id


async def edit_batch(song_ids, changes, actor=None, request=None):
    """
    Apply one partial field set to many songs (the PuddleTag multi-select move:
    "set genre/year on these 200 tracks"). Songs are edited one row at a time --
    with a million-file library the alternative, a single mass UPDATE, would
    skip the per-song locks, history and re-index. All members of one batch
    share a batch_id, so the whole batch can be rolled back as a unit.
    """
    batch_id = uuid.uuid4().hex
    updated = 0
    songs = await Songs.filter(id__in=list(song_ids))
    for song in songs:
        revision_id = await apply_changes(
            song, dict(changes), actor=actor, source="batch", batch_id=batch_id
        )
        if revision_id:
            updated += 1
    await audit.audit_event(
        audit.CONTENT_METADATA_EDITED,
        request=request,
        actor=actor,
        target_type="song",
        detail={
            "fields": sorted(changes),
            "source": "batch",
            "batch_id": batch_id,
            "songs": len(songs),
            "updated": updated,
        },
    )
    return {
        "batch_id": batch_id,
        "requested": len(song_ids),
        "updated": updated,
        "missing": len(song_ids) - len(songs),
    }


def _inverse(changes):
    """The undo of a recorded diff: every field back to its "old" value."""
    return {field: change["old"] for field, change in changes.items()}


async def rollback_revision(revision_id, actor=None, request=None):
    """
    Undo one revision by applying its inverse as a NEW revision (history is
    never rewritten). Refuses when the song has moved on since -- an undo that
    silently discarded a newer edit would be worse than no undo at all.
    """
    revision = await TagRevisions.get_or_none(id=revision_id)
    if revision is None:
        raise HTTPException(status_code=404, detail="Revision not found")
    song = await get_song_or_404(revision.song_id)
    changes = dict(revision.changes or {})
    art_change = changes.pop("artwork_path", None)
    stale = [
        field
        for field, change in changes.items()
        if getattr(song, field) != change["new"]
    ]
    if stale:
        raise HTTPException(
            status_code=409,
            detail="This track changed since that revision ({})".format(
                ", ".join(sorted(stale))
            ),
        )
    if art_change is not None:
        await _set_artwork(
            song,
            path=art_change["old"],
            source=(revision.changes.get("artwork_source") or {}).get("old"),
            actor=actor,
            request=request,
            revision_source="rollback",
        )
    revision_id = await apply_changes(
        song, _inverse(changes), actor=actor, source="rollback"
    )
    await audit.audit_event(
        audit.CONTENT_METADATA_ROLLBACK,
        request=request,
        actor=actor,
        target_type="song",
        target_id=song.id,
        detail={"undid_revision": revision.id, "revision": revision_id},
    )
    return song, revision_id


async def rollback_batch(batch_id, actor=None, request=None):
    """Undo every revision of one batch (newest first, so overlaps unwind)."""
    revisions = await TagRevisions.filter(batch_id=batch_id).order_by("-id")
    if not revisions:
        raise HTTPException(status_code=404, detail="Batch not found")
    undone, skipped = 0, []
    for revision in revisions:
        try:
            await rollback_revision(revision.id, actor=actor, request=request)
            undone += 1
        except HTTPException as error:
            if error.status_code != 409:
                raise
            skipped.append(revision.song_id)
    return {"batch_id": batch_id, "undone": undone, "skipped": skipped}


# --- Album art ---------------------------------------------------------------


async def _set_artwork(
    song,
    path,
    source,
    actor=None,
    request=None,
    width=None,
    height=None,
    revision_source="artwork",
):
    """Point a song at a stored art file (or at nothing), with history."""
    diff = _diff(
        song,
        {
            "artwork_path": path,
            "artwork_source": source,
            "artwork_width": width,
            "artwork_height": height,
        },
    )
    if not diff:
        return None
    song.artwork_path = path
    song.artwork_source = source
    song.artwork_width = width
    song.artwork_height = height
    await song.save(update_fields=list(ART_FIELDS) + ["modified_at"])
    revision = await record_revision(song, diff, actor=actor, source=revision_source)
    await audit.audit_event(
        audit.CONTENT_ART_CHANGED,
        request=request,
        actor=actor,
        target_type="song",
        target_id=song.id,
        detail={"source": source, "removed": path is None},
    )
    return revision.id if revision else None


async def set_artwork_bytes(song, data, source, actor=None, request=None):
    """Normalize raw image bytes and make them the song's art."""
    path, width, height = await art_utils.store(data)
    return await _set_artwork(
        song,
        path=path,
        source=source,
        actor=actor,
        request=request,
        width=width,
        height=height,
    )


async def remove_artwork(song, actor=None, request=None):
    if not song.artwork_path:
        raise HTTPException(status_code=404, detail="This track has no album art")
    # The stored file itself stays: it is content-addressed and may be shared
    # by other songs. Only this song's pointer is cleared.
    return await _set_artwork(song, None, None, actor=actor, request=request)


async def artwork_candidates(song):
    """
    Every cover we could offer for this song, without touching the network:
    what is embedded in the file, what Beatport matched (MOO-85), and what is
    already selected.
    """
    items = []
    if song.artwork_path:
        items.append(
            {
                "origin": "current",
                "url": None,
                "width": song.artwork_width,
                "height": song.artwork_height,
            }
        )
    if song.has_artwork:
        from src.database.models import TrackAnalysis

        analysis = await TrackAnalysis.get_or_none(song_id=song.id)
        items.append(
            {
                "origin": "embedded",
                "url": None,
                "width": getattr(analysis, "art_width", None),
                "height": getattr(analysis, "art_height", None),
            }
        )
    for url in await _beatport_art_urls(song):
        items.append({"origin": "beatport", "url": url, "width": None, "height": None})
    return items


async def _beatport_art_urls(song):
    """The artwork URLs MOO-85 stored for this song -- the fetch allowlist."""
    from src.database.models import SongEnrichment

    row = await SongEnrichment.get_or_none(song_id=song.id, provider="beatport")
    if row is None:
        return []
    urls = []
    payload = row.payload or {}
    if payload.get("artwork_url"):
        urls.append(payload["artwork_url"])
    for candidate in row.candidates or []:
        url = (candidate.get("payload") or {}).get("artwork_url")
        if url and url not in urls:
            urls.append(url)
    return urls


async def select_artwork(song, origin, url=None, actor=None, request=None):
    """
    Adopt one of the candidates as the song's art. A URL is only fetched when
    it is one Beatport already gave us for THIS song -- an operator-supplied
    URL is never fetched (SSRF; SECURITY.md item 9).
    """
    if origin == "embedded":
        data = art_utils.embedded_art(song.file_path)
        if not data:
            raise HTTPException(
                status_code=404, detail="This file has no embedded album art"
            )
        return await set_artwork_bytes(
            song, data, "embedded", actor=actor, request=request
        )
    if origin == "beatport":
        if url not in await _beatport_art_urls(song):
            raise HTTPException(
                status_code=422, detail="Not an artwork candidate for this track"
            )
        data = await _fetch_art(url)
        return await set_artwork_bytes(
            song, data, "beatport", actor=actor, request=request
        )
    raise HTTPException(status_code=422, detail="Unknown artwork candidate")


async def _fetch_art(url):
    """
    Download a candidate cover. One small GET against an allowlisted Beatport
    URL, so it runs in the request rather than on a worker; the size cap is
    enforced on the stream, not on Content-Length (which a server may lie
    about).
    """
    import httpx

    from src.enrichment.beatport_client import artwork_url_ok

    if not artwork_url_ok(url):
        raise HTTPException(status_code=422, detail="Not an allowed artwork URL")
    data = b""
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    data += chunk
                    if len(data) > art_utils.MAX_UPLOAD_BYTES:
                        raise HTTPException(
                            status_code=422, detail="That cover is too large"
                        )
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=502, detail="Could not fetch that cover: {}".format(error)
        )
    return data


# --- Enrichment suggestions --------------------------------------------------

# Beatport payload key -> song field. MOO-85 auto-applies genre/label/year only;
# the editor offers the rest as one-click suggestions a human confirms.
_SUGGESTION_MAP = {
    "name": "title",
    "genre": "genre",
    "subgenre": "genre",
    "label": "label",
    "release_name": "album",
    "isrc": "isrc",
    "bpm": "bpm",
    "key": "musical_key",
}


async def suggestions(song):
    """
    Per-field suggested values from the stored Beatport match (MOO-85), each
    with the current value beside it so the editor can show old -> new. Empty
    when the song was never enriched.
    """
    from src.database.models import SongEnrichment

    row = await SongEnrichment.get_or_none(song_id=song.id, provider="beatport")
    payload = (row.payload if row else None) or {}
    if not payload:
        return {
            "provider": "beatport",
            "status": row.status if row else None,
            "items": [],
        }
    values = {}
    for key, field in _SUGGESTION_MAP.items():
        value = payload.get(key)
        if value in (None, "", []):
            continue
        # subgenre is the more specific genre: it wins when both are present.
        if field == "genre" and key == "genre" and payload.get("subgenre"):
            continue
        values[field] = value
    artists = payload.get("artists") or []
    if artists:
        values["artist"] = ", ".join(artists)
    year = _release_year(payload.get("release_date"))
    if year:
        values["year"] = year

    locks = song.field_locks or {}
    items = [
        {
            "field": field,
            "current": getattr(song, field),
            "suggested": value,
            "locked": locks.get(field) == "manual",
        }
        for field, value in sorted(values.items())
        if getattr(song, field) != value
    ]
    return {
        "provider": "beatport",
        "status": row.status,
        "confidence": row.confidence,
        "items": items,
    }


def _release_year(release_date):
    try:
        return int(str(release_date)[:4])
    except (TypeError, ValueError):
        return None


# --- Member proposals --------------------------------------------------------


async def create_proposal(song_id, changes, note, proposer):
    """A member suggests an edit. Curators approve or reject it."""
    song = await get_song_or_404(song_id)
    if song.status != "published":
        raise HTTPException(status_code=404, detail="Song not found")
    unknown = [f for f in changes if f not in EDITABLE_FIELDS]
    if unknown or not changes:
        raise HTTPException(status_code=422, detail="Nothing editable was proposed")
    if await TagProposals.filter(
        song_id=song_id, proposer_id=proposer.id, status="pending"
    ).exists():
        raise HTTPException(
            status_code=409,
            detail="You already have a pending suggestion for this track",
        )
    return await TagProposals.create(
        song_id=song_id, proposer_id=proposer.id, changes=changes, note=note
    )


async def list_proposals(status=None, proposer_id=None, cursor=None, limit=50):
    query = TagProposals.all()
    if status:
        query = query.filter(status=status)
    if proposer_id:
        query = query.filter(proposer_id=proposer_id)
    if cursor:
        query = query.filter(id__lt=int(cursor))
    rows = (
        await query.order_by("-id")
        .limit(limit + 1)
        .prefetch_related("song", "proposer")
    )
    next_cursor = str(rows[limit - 1].id) if len(rows) > limit else None
    return {
        "items": [_proposal_dict(row) for row in rows[:limit]],
        "next_cursor": next_cursor,
    }


def _proposal_dict(row):
    song = row.song if row.song_id else None
    return {
        "id": row.id,
        "song_id": row.song_id,
        "song_title": song.title if song else None,
        "song_artist": song.artist if song else None,
        "proposer_username": row.proposer.username if row.proposer_id else None,
        "changes": row.changes,
        "note": row.note,
        "status": row.status,
        "created_at": row.created_at,
        "reviewed_at": row.reviewed_at,
    }


async def _get_pending_proposal(proposal_id):
    proposal = await TagProposals.get_or_none(id=proposal_id).prefetch_related(
        "song", "proposer"
    )
    if proposal is None:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    if proposal.status != "pending":
        raise HTTPException(
            status_code=409, detail="That suggestion was already reviewed"
        )
    return proposal


async def review_proposal(proposal_id, approve, reviewer, request=None):
    """Approve (apply through the normal edit path) or reject a suggestion."""
    from datetime import datetime, timezone

    proposal = await _get_pending_proposal(proposal_id)
    if approve:
        # The revision is credited to the member who proposed it; the audit
        # event records the curator who let it in.
        await edit_song(
            proposal.song_id,
            dict(proposal.changes or {}),
            actor=proposal.proposer,
            source="proposal",
            request=request,
        )
    proposal.status = "approved" if approve else "rejected"
    proposal.reviewed_by_id = reviewer.id
    proposal.reviewed_at = datetime.now(timezone.utc)
    await proposal.save(update_fields=["status", "reviewed_by_id", "reviewed_at"])
    await audit.audit_event(
        audit.TAG_PROPOSAL_APPROVED if approve else audit.TAG_PROPOSAL_REJECTED,
        request=request,
        actor=reviewer,
        target_type="song",
        target_id=proposal.song_id,
        detail={"proposal": proposal.id, "fields": sorted(proposal.changes or {})},
    )
    return _proposal_dict(proposal)


async def pending_proposal_count():
    return await TagProposals.filter(status="pending").count()
