"""
Enrichment service layer (MOO-85): search -> score -> classify -> persist,
apply/reject/un-apply, and the downstream contracts other stages read
(get_external_ids for MOO-90's dedup validator; the row itself for MOO-82's
ID3 editor via GET /admin/enrichment/songs/{song_id}).

Runs entirely inside worker jobs (src/jobs/tasks_enrichment.py) or admin
routes -- never opens an HTTP client itself (src/enrichment/*_client.py do
that) and never imports arq.

Precedence (D4, binding): manual > beatport > file tag. apply() only ever
writes a field that is not already locked "manual"; a fresh manual edit
(src/crud/content.py::edit_metadata) always outranks a previously-applied
enrichment. Auto-written fields are exactly genre/label/year (D4) -- bpm/key
are cross-check-only (payload carries bpm_mismatch/key_mismatch booleans,
never overwriting the analyzer's detected values).
"""
import logging
from datetime import datetime, timezone

from src.database.models import SongEnrichment, Songs
from src.enrichment import provider, scoring
from src.enrichment.normalize import split_mix
from src.security import audit
from src.telemetry import events as telemetry_events

logger = logging.getLogger("orp.enrichment")

APPLIED_FIELDS = ("genre", "label", "year")


def _utcnow():
    return datetime.now(timezone.utc)


def song_fields(song):
    """The local song's current signals, tag-then-detected coalesced (same
    D5 precedence /songs already serializes with)."""
    return {
        "artist": song.artist,
        "title": song.title,
        "duration_seconds": song.duration_seconds,
        "bpm": song.bpm if song.bpm is not None else song.bpm_detected,
        "musical_key": song.musical_key or song.key_detected,
    }


def _search_query(song):
    base_title, _mix = split_mix(song.title or "")
    return " ".join(part for part in (song.artist, base_title) if part).strip()


def _release_year(release_date):
    if not release_date:
        return None
    for chunk in str(release_date).replace("/", "-").split("-"):
        if len(chunk) == 4 and chunk.isdigit():
            return int(chunk)
    return None


def build_payload(candidate_payload, song):
    """
    The stored payload dict (the MOO-82 contract) from a candidate's raw
    Beatport fields, plus the bpm/key cross-check-only mismatch flags
    (D4: Beatport's bpm/key never overwrite the analyzer's).
    """
    payload = dict(candidate_payload or {})
    fields = song_fields(song)
    bpm_delta_score = scoring.bpm_score(fields.get("bpm"), payload.get("bpm"))
    key_delta_score = scoring.key_score(fields.get("musical_key"), payload.get("key"))
    payload["bpm_mismatch"] = bpm_delta_score is not None and bpm_delta_score < 1.0
    payload["key_mismatch"] = key_delta_score is not None and key_delta_score < 1.0
    return payload


async def get_or_create_row(song_id):
    row, _created = await SongEnrichment.get_or_create(
        song_id=song_id, provider="beatport"
    )
    return row


async def enrich_song(song_id, force=False, client=None):
    """
    The full pipeline for one song: search Beatport (mock or real), score
    and classify the candidates, persist the row, and auto-apply when the
    best candidate classifies "applied". A row already "applied" or
    "rejected" is left untouched unless force=True (a plain re-run of
    "pending"/"needs_review"/"no_match"/"error" always re-searches).
    """
    song = await Songs.get_or_none(id=song_id)
    if song is None:
        raise ValueError("song {} not found".format(song_id))
    row = await get_or_create_row(song_id)
    if row.status in ("applied", "rejected") and not force:
        return row

    if not song.artist and not song.title:
        row.status = "no_match"
        row.error = "missing_tags"
        row.candidates = []
        row.confidence = None
        row.matched_at = _utcnow()
        await row.save()
        return row

    try:
        if client is None:
            client = provider.get_client()
        raw_candidates = await client.search_tracks(_search_query(song))
    except Exception as error:
        row.status = "error"
        row.error = str(error)[:500]
        row.matched_at = _utcnow()
        await row.save()
        return row

    fields = song_fields(song)
    ranked = scoring.rank_candidates(fields, raw_candidates)
    best = ranked[0] if ranked else None
    status = scoring.classify(best)

    row.candidates = ranked
    row.confidence = best["score"] if best else None
    row.beatport_track_id = best["beatport_track_id"] if best else None
    row.matched_at = _utcnow()
    row.error = None

    if status == "applied":
        row.payload = build_payload(best["payload"], song)
        await row.save()
        await apply(row, fields=list(APPLIED_FIELDS), method="auto")
    else:
        row.status = status
        row.match_method = None
        row.payload = build_payload(best["payload"], song) if best else None
        await row.save()
    return await SongEnrichment.get(id=row.id)


async def apply(
    row, fields=None, user_id=None, method="manual", request=None, actor=None
):
    """
    Write the chosen candidate's fields onto the song row, skipping any
    field locked "manual" (D4 precedence), lock the fields it does write
    "beatport", snapshot their pre-apply values (for un-apply), denormalize
    beatport_track_id, and best-effort resync ES + the MOO-90 external-id
    hook. row.payload must already hold the chosen candidate's normalized
    fields (enrich_song sets this on auto-apply; the accept route sets it
    from the stored candidate list before calling apply()).
    """
    wanted = [f for f in (fields or list(APPLIED_FIELDS)) if f in APPLIED_FIELDS]
    song = await Songs.get_or_none(id=row.song_id)
    if song is None:
        row.status = "error"
        row.error = "song deleted"
        await row.save()
        return row

    payload = row.payload or {}
    locks = dict(song.field_locks or {})
    snapshot = dict(row.tag_snapshot or {})
    applied_fields = []
    update_fields = []
    for field in wanted:
        if locks.get(field) == "manual":
            continue  # a manual edit always outranks enrichment (D4)
        if field == "genre":
            value = payload.get("subgenre") or payload.get("genre")
        elif field == "label":
            value = payload.get("label")
        elif field == "year":
            value = _release_year(payload.get("release_date"))
        else:
            value = None
        if value in (None, ""):
            continue
        if field not in snapshot:
            snapshot[field] = getattr(song, field)
        setattr(song, field, value)
        locks[field] = "beatport"
        applied_fields.append(field)
        update_fields.append(field)

    song.field_locks = locks
    song.beatport_track_id = row.beatport_track_id
    update_fields += ["field_locks", "beatport_track_id", "modified_at"]
    await song.save(update_fields=update_fields)

    row.status = "applied"
    row.match_method = method
    row.fields_applied = applied_fields
    row.tag_snapshot = snapshot
    row.reviewed_by_id = user_id
    row.applied_at = _utcnow()
    await row.save()

    telemetry_events.enrichment_applied(song, "beatport", applied_fields)

    await _es_resync(song.id)
    await _dedup_link(song, row)
    await audit.audit_event(
        "enrichment.applied",
        request=request,
        actor=actor,
        target_type="song",
        target_id=song.id,
        detail={
            "provider": row.provider,
            "beatport_track_id": row.beatport_track_id,
            "fields": applied_fields,
            "confidence": row.confidence,
            "method": method,
        },
    )
    return row


async def unapply(row, request=None, actor=None):
    """
    Revert an applied row: restore the pre-apply snapshot onto every field
    still locked "beatport" (a manual edit made since apply already outranks
    this and is left alone), clear those locks + songs.beatport_track_id,
    and drop the row back to needs_review (candidates are kept for
    re-review).
    """
    if row.status != "applied":
        return row
    song = await Songs.get_or_none(id=row.song_id)
    if song is None:
        row.status = "needs_review"
        await row.save()
        return row
    snapshot = row.tag_snapshot or {}
    locks = dict(song.field_locks or {})
    update_fields = []
    for field in row.fields_applied or []:
        if locks.get(field) != "beatport":
            continue
        if field in snapshot:
            setattr(song, field, snapshot[field])
            update_fields.append(field)
        locks.pop(field, None)
    song.field_locks = locks
    song.beatport_track_id = None
    update_fields += ["field_locks", "beatport_track_id", "modified_at"]
    await song.save(update_fields=update_fields)

    row.status = "needs_review" if row.candidates else "pending"
    row.fields_applied = []
    row.applied_at = None
    await row.save()
    await _es_resync(song.id)
    await audit.audit_event(
        "enrichment.unapplied",
        request=request,
        actor=actor,
        target_type="song",
        target_id=song.id,
        detail={"provider": row.provider},
    )
    return row


async def reject(row, user_id=None, request=None, actor=None):
    """Mark a row not-a-match. An already-applied row is un-applied first
    (a rejected match can never leave fields locked on the song)."""
    if row.status == "applied":
        await unapply(row, request=request, actor=actor)
    row.status = "rejected"
    row.reviewed_by_id = user_id
    await row.save()
    await audit.audit_event(
        "enrichment.rejected",
        request=request,
        actor=actor,
        target_type="song",
        target_id=row.song_id,
        detail={"provider": row.provider},
    )
    return row


async def get_external_ids(song_id):
    """MOO-90 downstream contract: the external identity this stage knows
    about a song, for the dedup cross-source validator."""
    row = await SongEnrichment.get_or_none(song_id=song_id, provider="beatport")
    if row is None:
        return {"beatport_track_id": None, "isrc": None}
    isrc = (row.payload or {}).get("isrc")
    return {"beatport_track_id": row.beatport_track_id, "isrc": isrc}


async def maybe_auto_enqueue(song_ids, user_id=None):
    """
    Best-effort auto-enrich-on-import hook (D7): enqueue enrich_song for
    each song id when the `integrations.beatport_auto_enrich` instance
    setting is on and the provider is enabled. Never raises -- a scan or
    upload must never fail because enrichment couldn't be scheduled.
    """
    if not song_ids:
        return
    try:
        import src.crud.settings as settings_crud

        if not bool(
            await settings_crud.get_value("integrations", "beatport_auto_enrich")
        ):
            return
        mode, _reason = provider.mode_and_reason()
        if mode == "disabled":
            return
        from src.jobs.queue import QUEUE_HEAVY, submit_job

        for song_id in song_ids:
            await submit_job(
                "enrich_song",
                payload={"song_id": song_id, "force": False},
                user_id=user_id,
                queue=QUEUE_HEAVY,
            )
    except Exception:
        logger.exception("auto-enrich-on-import enqueue failed")


async def _es_resync(song_id):
    try:
        from src.search import outbox

        await outbox.enqueue_song_upsert(song_id)
        await outbox.nudge_drain()
    except Exception:
        logger.exception("enrichment ES resync failed for song %s", song_id)


async def _dedup_link(song, row):
    """
    Best-effort MOO-90 hook: attach the beatport_track_id/isrc onto the
    song's recording row when one exists. Never raises; a conflicting id on
    a different recording is handled by attach_external_ids itself (it
    raises a pending review candidate instead of merging anything).
    """
    try:
        if not song.recording_id:
            return
        from src.services.dedup import attach_external_ids

        isrc = (row.payload or {}).get("isrc")
        await attach_external_ids(
            song.recording_id,
            beatport_id=str(row.beatport_track_id) if row.beatport_track_id else None,
            isrc=isrc,
        )
    except Exception:
        logger.exception("enrichment dedup link failed for song %s", song.id)
