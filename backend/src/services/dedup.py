"""
Recording-level duplicate detection (MOO-90).

One recording (a specific mix/edit) keeps exactly one canonical version;
extended vs radio cuts are different recordings and are NEVER merged (the
duration guard is what tells them apart when fingerprints overlap). The
match cascade runs cheapest-first: byte hash, decoded-PCM hash (MOO-87's
pcm_sha256), indexed fingerprint similarity + duration guard, and metadata
corroboration that alone never triggers a merge. No file is ever moved or
deleted here -- losing versions become DB statuses (superseded/quarantined)
hidden from member surfaces and restorable from the admin UI.
"""
from datetime import datetime, timezone

from tortoise.exceptions import IntegrityError
from tortoise.expressions import Q

import src.crud.settings as settings_crud
from src.database.models import (
    DuplicateCandidates,
    FingerprintNgrams,
    Jobs,
    RecordingLinks,
    Recordings,
    Songs,
    TrackAnalysis,
)
from src.search import outbox
from src.security import audit
from src.services import quality
from src.utils import fingerprint as fp_util
from src.utils.normalize import normalize_artist, normalize_mix, normalize_title

# Candidate selection (D4): duration prefilter window is the guard tolerance
# plus one second of slack; the full comparison set is hard-capped.
DURATION_PREFILTER_SLACK = 1.0
CANDIDATE_CAP = 200
MIN_SHARED_NGRAMS = 2

# Pure-metadata matches are review-only by design (never auto): the reported
# confidence stays below the review threshold ceiling.
METADATA_CONFIDENCE = 0.65
METADATA_DURATION_TOLERANCE = 1.0

EXTERNAL_ID_FIELDS = ("isrc", "musicbrainz_id", "beatport_id", "spotify_id")

_BATCH = 1000

DEDUP_JOB_PREFIX = "dedup_song:"


def _utcnow():
    return datetime.now(timezone.utc)


def _chunks(values, size=_BATCH):
    for start in range(0, len(values), size):
        end = start + size
        yield values[start:end]


async def load_config():
    """The effective dedup settings (library group, coded defaults apply)."""
    return {
        "auto_resolve": bool(
            await settings_crud.get_value("library", "dedup_auto_resolve_fingerprint")
        ),
        "fp_threshold": float(
            await settings_crud.get_value("library", "dedup_fingerprint_threshold")
        ),
        "review_threshold": float(
            await settings_crud.get_value("library", "dedup_review_threshold")
        ),
        "duration_tolerance": float(
            await settings_crud.get_value("library", "dedup_duration_tolerance_seconds")
        ),
        "trust": quality.source_trust_map(
            await settings_crud.get_value("library", "dedup_source_trust")
        ),
    }


def derive_mix(song):
    """The mix designation of a song's raw title ("original" by default)."""
    return normalize_title(song.title)[1]


async def ensure_norms(song):
    """Populate artist_norm/title_norm on legacy rows that predate MOO-90."""
    if song.artist_norm is not None and song.title_norm is not None:
        return song
    song.artist_norm = normalize_artist(song.artist)
    song.title_norm = normalize_title(song.title)[0]
    await song.save(update_fields=["artist_norm", "title_norm", "modified_at"])
    return song


async def refresh_ngrams(song_id, fp_items):
    """Rebuild the fingerprint ngram index rows for one song (D4)."""
    grams = fp_util.ngrams(fp_items)
    await FingerprintNgrams.filter(song_id=song_id).delete()
    if not grams:
        return 0
    rows = [FingerprintNgrams(song_id=song_id, ngram=gram) for gram in sorted(grams)]
    for chunk in _chunks(rows):
        await FingerprintNgrams.bulk_create(chunk)
    return len(rows)


async def _analysis_map(song_ids):
    """{song_id: TrackAnalysis} for the given songs, chunked."""
    result = {}
    for chunk in _chunks(list(song_ids)):
        for row in await TrackAnalysis.filter(song_id__in=chunk):
            result[row.song_id] = row
    return result


async def _candidate_ids(song, analysis, fp_items, tolerance):
    """
    The D4 candidate set for one song: indexed prefilters only, never a full
    scan. Hash-equality legs, the duration+norm metadata leg, and the
    fingerprint ngram leg, unioned and capped.
    """
    ids = set()
    if song.checksum_sha256:
        ids.update(
            await Songs.filter(checksum_sha256=song.checksum_sha256)
            .exclude(id=song.id)
            .values_list("id", flat=True)
        )
    elif song.checksum_md5:
        ids.update(
            await Songs.filter(
                checksum_md5=song.checksum_md5, checksum_sha256__isnull=True
            )
            .exclude(id=song.id)
            .values_list("id", flat=True)
        )
    if analysis is not None and analysis.pcm_sha256:
        ids.update(
            await TrackAnalysis.filter(pcm_sha256=analysis.pcm_sha256)
            .exclude(song_id=song.id)
            .values_list("song_id", flat=True)
        )
    if song.duration_seconds is not None and (song.artist_norm or song.title_norm):
        window = tolerance + DURATION_PREFILTER_SLACK
        norm_filter = None
        if song.artist_norm:
            norm_filter = Q(artist_norm=song.artist_norm)
        if song.title_norm:
            title_q = Q(title_norm=song.title_norm)
            norm_filter = title_q if norm_filter is None else (norm_filter | title_q)
        ids.update(
            await Songs.filter(
                duration_seconds__gte=song.duration_seconds - window,
                duration_seconds__lte=song.duration_seconds + window,
            )
            .filter(norm_filter)
            .exclude(id=song.id)
            .limit(CANDIDATE_CAP)
            .values_list("id", flat=True)
        )
    if fp_items:
        grams = list(fp_util.ngrams(fp_items))
        shared = {}
        for chunk in _chunks(grams):
            rows = await FingerprintNgrams.filter(ngram__in=chunk).values_list(
                "song_id", "ngram"
            )
            for song_id, gram in rows:
                if song_id == song.id:
                    continue
                shared.setdefault(song_id, set()).add(gram)
        ids.update(
            sid
            for sid, grams_hit in shared.items()
            if len(grams_hit) >= MIN_SHARED_NGRAMS
        )
    return sorted(ids)[:CANDIDATE_CAP]


def _external_id_relation(rec_a, rec_b):
    """("shared"|"conflict"|None) between two recordings' external IDs."""
    if rec_a is None or rec_b is None:
        return None
    relation = None
    for field in EXTERNAL_ID_FIELDS:
        a = getattr(rec_a, field)
        b = getattr(rec_b, field)
        if a and b:
            if a == b:
                relation = relation or "shared"
            else:
                return "conflict"
    return relation


def _match_pair(song, other, analysis, other_analysis, fp_items, cfg, id_relation):
    """
    Run the D3 cascade on one pair. Returns a match dict
    {layer, similarity, confidence, tier, duration_delta} where tier is
    certain | confident | borderline | related_cut, or None for no match.
    """
    # L1 -- byte hash.
    if song.checksum_sha256 and song.checksum_sha256 == other.checksum_sha256:
        return {
            "layer": "checksum",
            "similarity": None,
            "confidence": 1.0,
            "tier": "certain",
            "duration_delta": _duration_delta(song, other),
        }
    if (
        not song.checksum_sha256
        and not other.checksum_sha256
        and song.checksum_md5
        and song.checksum_md5 == other.checksum_md5
    ):
        return {
            "layer": "checksum",
            "similarity": None,
            "confidence": 1.0,
            "tier": "certain",
            "duration_delta": _duration_delta(song, other),
        }

    # L2 -- decoded-PCM hash (MOO-87 pcm_sha256): same encode, different
    # container/tags.
    pcm_a = analysis.pcm_sha256 if analysis else None
    pcm_b = other_analysis.pcm_sha256 if other_analysis else None
    if pcm_a and pcm_a == pcm_b:
        return {
            "layer": "pcm_hash",
            "similarity": None,
            "confidence": 1.0,
            "tier": "certain",
            "duration_delta": _duration_delta(song, other),
        }

    # L3 -- fingerprint similarity, gated by the L4 duration guard.
    other_fp = fp_util.decode_fp(other_analysis.fingerprint) if other_analysis else []
    if fp_items and other_fp:
        similarity = fp_util.similarity(fp_items, other_fp)
        if similarity >= cfg["review_threshold"]:
            delta = _duration_delta(song, other)
            if delta is not None and delta > cfg["duration_tolerance"]:
                # L4: overlapping audio, different length -- a different cut
                # of the same track (extended vs radio). NOT a duplicate.
                return {
                    "layer": "fingerprint",
                    "similarity": similarity,
                    "confidence": similarity,
                    "tier": "related_cut",
                    "duration_delta": delta,
                }
            # L5 -- metadata corroboration adjusts confidence, never decides.
            confidence = similarity
            mix_a = derive_mix(song)
            mix_b = derive_mix(other)
            triple_equal = (
                song.artist_norm
                and song.title_norm
                and song.artist_norm == other.artist_norm
                and song.title_norm == other.title_norm
                and mix_a == mix_b
            )
            if triple_equal:
                confidence += 0.03
            if id_relation == "shared":
                confidence += 0.05
            if mix_a != mix_b:
                confidence -= 0.10
            if song.artist_norm != other.artist_norm:
                confidence -= 0.05
            confidence = min(max(confidence, 0.0), 1.0)
            if confidence < cfg["review_threshold"]:
                return None
            tier = "confident" if confidence >= cfg["fp_threshold"] else "borderline"
            # Conflicting signals never auto-resolve (D3): a mix-name
            # disagreement, an external-ID conflict, or an unverifiable
            # duration all force the review queue.
            if mix_a != mix_b or id_relation == "conflict" or delta is None:
                tier = "borderline"
            return {
                "layer": "fingerprint",
                "similarity": similarity,
                "confidence": confidence,
                "tier": tier,
                "duration_delta": delta,
            }

    # L5 standalone -- pure metadata is review-queue evidence at most, and
    # only on an exact non-empty triple with near-equal durations.
    if (
        song.artist_norm
        and song.title_norm
        and song.artist_norm == other.artist_norm
        and song.title_norm == other.title_norm
        and derive_mix(song) == derive_mix(other)
    ):
        delta = _duration_delta(song, other)
        if delta is not None and delta <= METADATA_DURATION_TOLERANCE:
            return {
                "layer": "metadata",
                "similarity": None,
                "confidence": METADATA_CONFIDENCE,
                "tier": "borderline",
                "duration_delta": delta,
            }
    return None


def _duration_delta(song, other):
    if song.duration_seconds is None or other.duration_seconds is None:
        return None
    return abs(song.duration_seconds - other.duration_seconds)


async def match_song(song, cfg=None):
    """
    The full D3/D4 cascade for one song against the library. Returns a list
    of match dicts, each carrying the candidate row in "other".
    """
    cfg = cfg or await load_config()
    await ensure_norms(song)
    analysis = await TrackAnalysis.get_or_none(song_id=song.id)
    fp_items = fp_util.decode_fp(analysis.fingerprint) if analysis else []
    if fp_items:
        await refresh_ngrams(song.id, fp_items)
    candidate_ids = await _candidate_ids(
        song, analysis, fp_items, cfg["duration_tolerance"]
    )
    if not candidate_ids:
        return []
    candidates = []
    for chunk in _chunks(candidate_ids):
        candidates.extend(await Songs.filter(id__in=chunk))
    analyses = await _analysis_map([c.id for c in candidates])
    recordings = {}
    rec_ids = {c.recording_id for c in candidates if c.recording_id}
    if song.recording_id:
        rec_ids.add(song.recording_id)
    for chunk in _chunks(list(rec_ids)):
        for rec in await Recordings.filter(id__in=chunk):
            recordings[rec.id] = rec
    own_rec = recordings.get(song.recording_id)
    matches = []
    for other in candidates:
        await ensure_norms(other)
        id_relation = _external_id_relation(own_rec, recordings.get(other.recording_id))
        match = _match_pair(
            song, other, analysis, analyses.get(other.id), fp_items, cfg, id_relation
        )
        if match is not None:
            match["other"] = other
            matches.append(match)
    return matches


# --- recording lifecycle ----------------------------------------------------


async def _ensure_recording(song):
    """The song's Recordings row, created lazily from its identity."""
    if song.recording_id:
        rec = await Recordings.get_or_none(id=song.recording_id)
        if rec is not None:
            return rec
    await ensure_norms(song)
    artist_norm = song.artist_norm or ""
    title_norm = song.title_norm or ""
    mix_norm = derive_mix(song)
    # One recordings row per identity: a second song of the same mix/edit must
    # join the existing row, not fork a duplicate. idx_recordings_identity is
    # not unique, so the reuse has to happen here.
    rec = (
        await Recordings.filter(
            artist_norm=artist_norm, title_norm=title_norm, mix_norm=mix_norm
        )
        .order_by("id")
        .first()
    )
    if rec is None:
        rec = await Recordings.create(
            artist_norm=artist_norm,
            title_norm=title_norm,
            mix_norm=mix_norm,
            duration_seconds=song.duration_seconds,
            canonical_song_id=song.id if song.version_status == "canonical" else None,
        )
    song.recording_id = rec.id
    await song.save(update_fields=["recording_id", "modified_at"])
    return rec


async def _merge_recordings(keep, absorb):
    """Fold recording [absorb] into [keep]: move versions, merge IDs."""
    if absorb is None or keep.id == absorb.id:
        return keep
    await Songs.filter(recording_id=absorb.id).update(recording_id=keep.id)
    changed = []
    for field in EXTERNAL_ID_FIELDS:
        if getattr(keep, field) is None and getattr(absorb, field) is not None:
            setattr(keep, field, getattr(absorb, field))
            changed.append(field)
    if changed:
        await keep.save(update_fields=changed + ["modified_at"])
    await absorb.delete()
    return keep


async def link_related(song_a, song_b, similarity=None):
    """Record two songs as different cuts of the same track (L4)."""
    rec_a = await _ensure_recording(song_a)
    rec_b = await _ensure_recording(song_b)
    if rec_a.id == rec_b.id:
        return None
    first, second = sorted((rec_a.id, rec_b.id))
    try:
        return await RecordingLinks.create(
            recording_a_id=first,
            recording_b_id=second,
            kind="related_cut",
            similarity=similarity,
        )
    except IntegrityError:
        return await RecordingLinks.get_or_none(
            recording_a_id=first, recording_b_id=second
        )


async def upsert_candidate(song_a, song_b, defaults):
    """
    Get-or-create the ordered (song_a_id < song_b_id) candidate row.
    Returns (row, created). An existing row is never downgraded: rejected
    pairs stay rejected forever, resolved pairs are not re-raised.
    """
    first, second = sorted((song_a.id, song_b.id))
    row = await DuplicateCandidates.get_or_none(song_a_id=first, song_b_id=second)
    if row is not None:
        return row, False
    try:
        row = await DuplicateCandidates.create(
            song_a_id=first, song_b_id=second, **defaults
        )
        return row, True
    except IntegrityError:
        return (
            await DuplicateCandidates.get(song_a_id=first, song_b_id=second),
            False,
        )


async def sync_search(song_ids):
    """Version-status transitions change what /search may surface (MOO-79)."""
    await outbox.enqueue_many(list(song_ids), "upsert")
    await outbox.nudge_drain()


async def apply_quality(song, analysis=None, trust=None):
    """Persist the D5 breakdown on the song row; returns the tuple."""
    if analysis is None:
        analysis = await TrackAnalysis.get_or_none(song_id=song.id)
    detail = quality.quality_breakdown(song, analysis, trust)
    song.quality_breakdown = detail
    await song.save(update_fields=["quality_breakdown", "modified_at"])
    return quality.tuple_from_breakdown(detail)


async def pick_winner(song_a, song_b, trust=None):
    """
    The best-quality version of a confirmed pair (D5). Equal tuples keep the
    incumbent: the older row (stability).
    """
    analyses = await _analysis_map([song_a.id, song_b.id])
    older, newer = (song_a, song_b) if song_a.id <= song_b.id else (song_b, song_a)
    tuple_older = await apply_quality(older, analyses.get(older.id), trust)
    tuple_newer = await apply_quality(newer, analyses.get(newer.id), trust)
    return newer if tuple_newer > tuple_older else older


async def resolve_pair(
    song_a,
    song_b,
    winner,
    actor=None,
    auto=False,
    request=None,
    candidate=None,
    detail=None,
):
    """
    Merge a confirmed duplicate pair into one recording: winner canonical,
    loser superseded, canonical pointer repointed, both docs re-synced, the
    decision audited. Pure DB -- no file IO whatsoever (D6).
    """
    loser = song_b if winner.id == song_a.id else song_a
    rec = await _ensure_recording(winner)
    other_rec = None
    if loser.recording_id and loser.recording_id != rec.id:
        other_rec = await Recordings.get_or_none(id=loser.recording_id)
    rec = await _merge_recordings(rec, other_rec)
    if loser.recording_id != rec.id:
        loser.recording_id = rec.id
    winner.version_status = "canonical"
    loser.version_status = "superseded"
    await winner.save(update_fields=["version_status", "recording_id", "modified_at"])
    await loser.save(update_fields=["version_status", "recording_id", "modified_at"])
    rec.canonical_song_id = winner.id
    rec.duration_seconds = winner.duration_seconds
    await rec.save(
        update_fields=["canonical_song_id", "duration_seconds", "modified_at"]
    )
    resolution = {
        "action": "merge",
        "winner_song_id": winner.id,
        "loser_song_id": loser.id,
        "winner_quality": winner.quality_breakdown,
        "loser_quality": loser.quality_breakdown,
    }
    if candidate is not None:
        candidate.recording_id = rec.id
        candidate.status = "auto_resolved" if auto else "confirmed"
        candidate.resolution = resolution
        candidate.resolved_by_id = getattr(actor, "id", None)
        candidate.resolved_at = _utcnow()
        await candidate.save()
    await sync_search([winner.id, loser.id])
    event = audit.DEDUP_AUTO_MERGED if auto else audit.DEDUP_REVIEWED
    await audit.audit_event(
        event,
        request=request,
        actor=actor,
        target_type="recording",
        target_id=rec.id,
        detail=dict(detail or {}, **resolution),
    )
    return rec


async def process_song(song, cfg=None, dry_run=False, actor=None):
    """
    The dedup pipeline stage for one song (D3): match, then act per tier.
    Dry-run records proposed candidates and related-cut counts but changes
    nothing else. Returns a summary dict for the jobs row.
    """
    cfg = cfg or await load_config()
    summary = {
        "song_id": song.id,
        "certain": 0,
        "confident": 0,
        "borderline": 0,
        "related_cuts": 0,
        "auto_resolved": 0,
        "proposed": 0,
        "pending": 0,
    }
    for match in await match_song(song, cfg):
        other = match["other"]
        tier = match["tier"]
        if tier == "related_cut":
            summary["related_cuts"] += 1
            if not dry_run:
                await link_related(song, other, match["similarity"])
            continue
        summary[tier] += 1
        defaults = {
            "layer": match["layer"],
            "similarity": match["similarity"],
            "confidence": match["confidence"],
            "duration_delta": match["duration_delta"],
        }
        if dry_run:
            winner = await pick_winner(song, other, cfg["trust"])
            _, created = await upsert_candidate(
                song,
                other,
                dict(defaults, status="proposed", suggested_winner_id=winner.id),
            )
            if created:
                summary["proposed"] += 1
            continue
        auto = tier == "certain" or (tier == "confident" and cfg["auto_resolve"])
        winner = await pick_winner(song, other, cfg["trust"])
        row = await DuplicateCandidates.get_or_none(
            song_a_id=min(song.id, other.id), song_b_id=max(song.id, other.id)
        )
        if row is not None and row.status not in ("proposed",):
            # Already decided (or already queued): never re-raise (D3).
            continue
        if auto:
            if row is None:
                row, _ = await upsert_candidate(
                    song,
                    other,
                    dict(defaults, status="pending", suggested_winner_id=winner.id),
                )
            await resolve_pair(
                song,
                other,
                winner,
                auto=True,
                candidate=row,
                detail={"layer": match["layer"], "confidence": match["confidence"]},
            )
            summary["auto_resolved"] += 1
        else:
            if row is None:
                _, created = await upsert_candidate(
                    song,
                    other,
                    dict(defaults, status="pending", suggested_winner_id=winner.id),
                )
                if created:
                    summary["pending"] += 1
            else:
                row.status = "pending"
                row.suggested_winner_id = winner.id
                for field, value in defaults.items():
                    setattr(row, field, value)
                await row.save()
                summary["pending"] += 1
    return summary


# --- downstream contracts (MOO-78 / MOO-81 / MOO-85) -------------------------


async def attach_external_ids(recording_id, **ids):
    """
    Record external platform IDs on a recording (MOO-85). A conflicting ID
    (already on a different recording) raises a pending review flag instead
    of merging anything.
    """
    rec = await Recordings.get_or_none(id=recording_id)
    if rec is None:
        return None
    changed = []
    for field in EXTERNAL_ID_FIELDS:
        value = ids.get(field)
        if not value:
            continue
        holder = await _recording_holding(field, value)
        if holder is not None and holder.id != rec.id:
            # Same external ID on two recordings: surface for review, never
            # auto-merge (D7).
            a = await Songs.get_or_none(id=holder.canonical_song_id)
            b = await Songs.get_or_none(id=rec.canonical_song_id)
            if a is not None and b is not None:
                await upsert_candidate(
                    a,
                    b,
                    {
                        "layer": "metadata",
                        "confidence": METADATA_CONFIDENCE,
                        "status": "pending",
                        "recording_id": rec.id,
                    },
                )
            continue
        if getattr(rec, field) != value:
            setattr(rec, field, value)
            changed.append(field)
    if changed:
        await rec.save(update_fields=changed + ["modified_at"])
    return rec


async def _recording_holding(field, value):
    """The oldest recording carrying this external ID.

    Only isrc is uniquely indexed; the other platform IDs can legitimately sit
    on two recordings (attach_external_ids raises a review flag for exactly
    that), so this must not assume at most one row.
    """
    return await Recordings.filter(**{field: value}).order_by("id").first()


async def _recording_by_external_ids(**ids):
    for field in EXTERNAL_ID_FIELDS:
        value = ids.get(field)
        if value:
            rec = await _recording_holding(field, value)
            if rec is not None:
                return rec, field
    return None, None


async def _canonical_of(rec):
    if rec is None:
        return None
    if rec.canonical_song_id:
        song = await Songs.get_or_none(id=rec.canonical_song_id)
        if song is not None:
            return song
    return await Songs.filter(recording_id=rec.id, version_status="canonical").first()


async def check_library(
    artist=None,
    title=None,
    mix=None,
    duration_seconds=None,
    isrc=None,
    musicbrainz_id=None,
    beatport_id=None,
    spotify_id=None,
    fingerprint_b64=None,
    source=None,
    declared_bitrate_kbps=None,
    format=None,
):
    """
    The pre-download library check (MOO-78/MOO-81 contract): does the
    library already hold a version of this recording, and would the offered
    source improve on the canonical? Resolution order: external IDs (the
    strongest cross-platform identity), local fingerprint index, exact
    metadata (reported at review-only confidence).
    """
    cfg = await load_config()
    result = {
        "found": False,
        "recording_id": None,
        "canonical_song_id": None,
        "canonical": None,
        "match_layer": None,
        "confidence": None,
        "would_improve": None,
    }
    rec, _field = await _recording_by_external_ids(
        isrc=isrc,
        musicbrainz_id=musicbrainz_id,
        beatport_id=beatport_id,
        spotify_id=spotify_id,
    )
    canonical = await _canonical_of(rec)
    if canonical is not None:
        result.update(match_layer="external_id", confidence=1.0)
    if canonical is None and fingerprint_b64:
        fp_items = fp_util.decode_fp(fingerprint_b64)
        if fp_items:
            grams = list(fp_util.ngrams(fp_items))
            shared = {}
            for chunk in _chunks(grams):
                rows = await FingerprintNgrams.filter(ngram__in=chunk).values_list(
                    "song_id", "ngram"
                )
                for song_id, gram in rows:
                    shared.setdefault(song_id, set()).add(gram)
            candidate_ids = sorted(
                sid for sid, hit in shared.items() if len(hit) >= MIN_SHARED_NGRAMS
            )[:CANDIDATE_CAP]
            best = None
            best_similarity = 0.0
            analyses = await _analysis_map(candidate_ids)
            for chunk in _chunks(candidate_ids):
                for other in await Songs.filter(id__in=chunk):
                    other_analysis = analyses.get(other.id)
                    other_fp = (
                        fp_util.decode_fp(other_analysis.fingerprint)
                        if other_analysis
                        else []
                    )
                    if not other_fp:
                        continue
                    similarity = fp_util.similarity(fp_items, other_fp)
                    if similarity < cfg["review_threshold"]:
                        continue
                    if (
                        duration_seconds is not None
                        and other.duration_seconds is not None
                        and abs(duration_seconds - other.duration_seconds)
                        > cfg["duration_tolerance"]
                    ):
                        continue  # different cut, not this recording
                    if similarity > best_similarity:
                        best, best_similarity = other, similarity
            if best is not None:
                rec = await _ensure_recording(best)
                canonical = await _canonical_of(rec) or best
                result.update(
                    match_layer="fingerprint", confidence=round(best_similarity, 4)
                )
    if canonical is None and artist and title:
        artist_norm = normalize_artist(artist)
        title_norm, title_mix = normalize_title(title)
        mix_norm = (normalize_mix(mix) or title_mix) if mix else title_mix
        rec_row = (
            await Recordings.filter(
                artist_norm=artist_norm, title_norm=title_norm, mix_norm=mix_norm
            )
            .order_by("id")
            .first()
        )
        canonical = await _canonical_of(rec_row)
        if canonical is None:
            query = Songs.filter(
                artist_norm=artist_norm,
                title_norm=title_norm,
                version_status="canonical",
            )
            if duration_seconds is not None:
                query = query.filter(
                    duration_seconds__gte=duration_seconds
                    - METADATA_DURATION_TOLERANCE,
                    duration_seconds__lte=duration_seconds
                    + METADATA_DURATION_TOLERANCE,
                )
            for other in await query.limit(20):
                if derive_mix(other) == mix_norm:
                    canonical = other
                    break
        else:
            rec = rec_row
        if canonical is not None:
            if duration_seconds is not None and canonical.duration_seconds is not None:
                if (
                    abs(duration_seconds - canonical.duration_seconds)
                    > METADATA_DURATION_TOLERANCE
                ):
                    canonical = None
        if canonical is not None:
            result.update(match_layer="metadata", confidence=METADATA_CONFIDENCE)
    if canonical is None:
        return result
    if rec is None or (canonical.recording_id and rec.id != canonical.recording_id):
        rec = await _ensure_recording(canonical)
    analysis = await TrackAnalysis.get_or_none(song_id=canonical.id)
    result["found"] = True
    result["recording_id"] = rec.id
    result["canonical_song_id"] = canonical.id
    result["canonical"] = canonical
    if source or declared_bitrate_kbps or format:
        offered = quality.hypothetical_tuple(source, declared_bitrate_kbps, format)
        current = quality.quality_tuple(canonical, analysis, cfg["trust"])
        result["would_improve"] = offered > current
    return result


async def evaluate_incoming(song_id, claimed=None):
    """
    The post-download decision for one ingested song (MOO-78 contract).
    Cross-source counter-validation happens here: when the source's claimed
    identity (external IDs / duration) contradicts what the audio actually
    matches, the file is quarantined and flagged -- never merged. Returns
    one of: new_recording | duplicate_kept_worse | duplicate_promoted |
    needs_review | mismatch_quarantined.
    """
    song = await Songs.get_or_none(id=song_id)
    if song is None:
        return "new_recording"
    cfg = await load_config()
    claimed = claimed or {}

    # Claimed duration vs the actual audio: a provider that says 3:20 for a
    # file that decodes to 6:30 is describing a different cut.
    claimed_duration = claimed.get("duration_seconds")
    if (
        claimed_duration is not None
        and song.duration_seconds is not None
        and abs(claimed_duration - song.duration_seconds) > cfg["duration_tolerance"]
    ):
        return await _quarantine_mismatch(
            song, reason="duration disagrees with the provider metadata"
        )

    claimed_rec, claimed_field = await _recording_by_external_ids(
        **{field: claimed.get(field) for field in EXTERNAL_ID_FIELDS}
    )

    matches = [
        match for match in await match_song(song, cfg) if match["tier"] != "related_cut"
    ]
    matches.sort(key=lambda match: match["confidence"], reverse=True)
    best = matches[0] if matches else None

    if best is not None and claimed_rec is not None:
        other_rec_id = best["other"].recording_id
        if other_rec_id and other_rec_id != claimed_rec.id:
            # The audio matches recording Y while the source claims
            # recording X: a mislabeled file.
            return await _quarantine_mismatch(
                song,
                reason="fingerprint matches a different recording than the "
                "claimed {}".format(claimed_field),
                other=best["other"],
            )

    if best is None:
        rec = await _ensure_recording(song)
        await attach_external_ids(
            rec.id, **{field: claimed.get(field) for field in EXTERNAL_ID_FIELDS}
        )
        await apply_quality(song, trust=cfg["trust"])
        return "new_recording"

    other = best["other"]
    tier = best["tier"]
    auto = tier == "certain" or (tier == "confident" and cfg["auto_resolve"])
    winner = await pick_winner(song, other, cfg["trust"])
    if not auto:
        await upsert_candidate(
            song,
            other,
            {
                "layer": best["layer"],
                "similarity": best["similarity"],
                "confidence": best["confidence"],
                "duration_delta": best["duration_delta"],
                "status": "pending",
                "suggested_winner_id": winner.id,
            },
        )
        return "needs_review"
    row, _ = await upsert_candidate(
        song,
        other,
        {
            "layer": best["layer"],
            "similarity": best["similarity"],
            "confidence": best["confidence"],
            "duration_delta": best["duration_delta"],
            "status": "pending",
            "suggested_winner_id": winner.id,
        },
    )
    rec = await resolve_pair(
        song,
        other,
        winner,
        auto=True,
        candidate=row if row.status in ("pending", "proposed") else None,
        detail={"layer": best["layer"], "confidence": best["confidence"]},
    )
    await attach_external_ids(
        rec.id, **{field: claimed.get(field) for field in EXTERNAL_ID_FIELDS}
    )
    if winner.id == song.id:
        await audit.audit_event(
            audit.DEDUP_PROMOTED,
            target_type="recording",
            target_id=rec.id,
            detail={"song_id": song.id, "over_song_id": other.id},
        )
        return "duplicate_promoted"
    return "duplicate_kept_worse"


async def _quarantine_mismatch(song, reason, other=None):
    song.version_status = "quarantined"
    await song.save(update_fields=["version_status", "modified_at"])
    if other is not None:
        await upsert_candidate(
            song,
            other,
            {
                "layer": "fingerprint",
                "confidence": METADATA_CONFIDENCE,
                "status": "pending",
            },
        )
    await sync_search([song.id])
    await audit.audit_event(
        audit.DEDUP_MISMATCH_FLAGGED,
        target_type="song",
        target_id=song.id,
        detail={"reason": reason},
    )
    return "mismatch_quarantined"


async def enqueue_dedup(song_id, user_id=None):
    """
    Queue the dedup pipeline stage for one song on orp:heavy (same dedup
    semantics as the analyzer dispatch: one pending job per song).
    """
    from src.jobs.queue import QUEUE_HEAVY, submit_job

    arq_job_id = DEDUP_JOB_PREFIX + str(song_id)
    already = await Jobs.filter(
        kind="dedup_song",
        arq_job_id=arq_job_id,
        status__in=["queued", "running"],
    ).exists()
    if already:
        return None
    return await submit_job(
        "dedup_song",
        payload={"song_id": song_id},
        user_id=user_id,
        queue=QUEUE_HEAVY,
        arq_job_id=arq_job_id,
    )
