"""
Match scoring for Beatport candidates (MOO-85).

Pure logic -- no network, no DB, no FastAPI -- so it is directly unit
testable. Computes a weighted composite score across title/mix/artist/
duration/bpm/key, gracefully degrading (renormalizing weights) when a
signal is missing on either side, then classifies the best candidate as
applied (auto-apply) / needs_review / no_match against env-overridable
thresholds.
"""
import os

from src.enrichment import normalize as norm
from src.utils.camelot import to_camelot

# Composite weights (sum to 1.0 when every signal is present).
WEIGHTS = {
    "title": 0.30,
    "mix": 0.10,
    "artist": 0.25,
    "duration": 0.20,
    "bpm": 0.075,
    "key": 0.075,
}

AUTO_APPLY_THRESHOLD = float(os.environ.get("BEATPORT_AUTO_APPLY_THRESHOLD", "0.85"))
REVIEW_THRESHOLD = float(os.environ.get("BEATPORT_REVIEW_THRESHOLD", "0.60"))

# Auto-apply gates beyond the composite score (D6): a high score alone is not
# enough -- title/artist must independently be strong, and the duration must
# be a tight match (never auto-apply an Extended Mix onto a Radio Edit row).
AUTO_APPLY_TITLE_MIN = 0.90
AUTO_APPLY_ARTIST_MIN = 0.85
AUTO_APPLY_DURATION_DELTA_MAX = 5.0

# Duration score curve constants: 1.0 up to a 2s delta, linear down to 0.0 at
# a 15s delta (an Extended Mix vs a Radio Edit is usually 60-120s apart).
_DURATION_FULL_SCORE_DELTA = 2.0
_DURATION_ZERO_SCORE_DELTA = 15.0
# BPM halving/doubling tolerant curve: 0 at a 6 BPM (post-fold) delta.
_BPM_ZERO_SCORE_DELTA = 6.0


def duration_score(local_seconds, candidate_seconds):
    if local_seconds is None or candidate_seconds is None:
        return None
    delta = abs(local_seconds - candidate_seconds)
    if delta <= _DURATION_FULL_SCORE_DELTA:
        return 1.0
    if delta >= _DURATION_ZERO_SCORE_DELTA:
        return 0.0
    span = _DURATION_ZERO_SCORE_DELTA - _DURATION_FULL_SCORE_DELTA
    return 1.0 - (delta - _DURATION_FULL_SCORE_DELTA) / span


def bpm_score(local_bpm, candidate_bpm):
    if not local_bpm or not candidate_bpm:
        return None
    # Tolerant to half/double-time tagging disagreements (MOO-87 does the
    # same for the tag-vs-analyzer mismatch flag).
    delta = min(
        abs(candidate_bpm - local_bpm),
        abs(2 * candidate_bpm - local_bpm),
        abs(candidate_bpm - 2 * local_bpm),
    )
    return max(0.0, 1.0 - delta / _BPM_ZERO_SCORE_DELTA)


def key_score(local_key, candidate_key):
    local_camelot = to_camelot(local_key)
    candidate_camelot = to_camelot(candidate_key)
    if not local_camelot or not candidate_camelot:
        return None
    if local_camelot == candidate_camelot:
        return 1.0
    try:
        local_num, local_letter = int(local_camelot[:-1]), local_camelot[-1]
        cand_num, cand_letter = int(candidate_camelot[:-1]), candidate_camelot[-1]
    except (ValueError, IndexError):
        return 0.0
    if local_num == cand_num and local_letter != cand_letter:
        return 0.6  # relative major/minor (e.g. 8A vs 8B)
    ring_distance = min((local_num - cand_num) % 12, (cand_num - local_num) % 12)
    if local_letter == cand_letter and ring_distance == 1:
        return 0.6  # neighboring wheel position, same mode
    return 0.0


def score_candidate(song_fields, candidate):
    """
    song_fields: a dict with "artist", "title", and optionally
    "duration_seconds", "bpm", "musical_key" (the local song's current
    values -- tag/analyzer-coalesced, whatever the caller has on hand).

    candidate: a normalized Beatport track dict (see
    beatport_client.py/mock_client.py `_normalize_track` for the exact
    shape): "name", "mix_name", "artists" (list[str]), "duration_seconds",
    "bpm", "key" (raw notation, mapped through camelot here).

    Returns {"score": float 0-1, "components": {signal: score|None},
    "duration_delta": float|None}. A missing signal on either side is
    dropped from the weighted average entirely (renormalized over the
    remaining weights) rather than penalized -- title and artist are always
    computable (empty vs empty scores 1.0, so an untitled local song simply
    contributes no information there either, by design of similarity()).
    """
    local_base, local_mix = norm.split_mix(song_fields.get("title") or "")
    cand_base = norm.normalize(candidate.get("name") or "")
    cand_mix = norm.normalize(candidate.get("mix_name") or "") or norm.DEFAULT_MIX_NAME

    local_artist = song_fields.get("artist") or ""
    candidate_artists = candidate.get("artists") or []
    s_artist = norm.similarity(local_artist, ", ".join(candidate_artists))
    for one in candidate_artists:
        s_artist = max(s_artist, norm.similarity(local_artist, one))

    local_duration = song_fields.get("duration_seconds")
    cand_duration = candidate.get("duration_seconds")
    duration_delta = (
        abs(local_duration - cand_duration)
        if local_duration is not None and cand_duration is not None
        else None
    )

    components = {
        "title": norm.similarity(local_base, cand_base),
        "mix": norm.similarity(local_mix, cand_mix),
        "artist": s_artist,
        "duration": duration_score(local_duration, cand_duration),
        "bpm": bpm_score(song_fields.get("bpm"), candidate.get("bpm")),
        "key": key_score(song_fields.get("musical_key"), candidate.get("key")),
    }

    total_weight = 0.0
    total_score = 0.0
    for signal, value in components.items():
        if value is None:
            continue
        weight = WEIGHTS[signal]
        total_weight += weight
        total_score += weight * value
    score = (total_score / total_weight) if total_weight else 0.0
    return {"score": score, "components": components, "duration_delta": duration_delta}


def rank_candidates(song_fields, candidates, top_n=5):
    """
    Score every candidate and return the top [top_n] as review-queue-ready
    dicts (candidate summary + score + components + duration_delta + the
    full normalized payload, so accepting a match never needs a second
    Beatport call). Sorted best-first.
    """
    scored = []
    for candidate in candidates:
        result = score_candidate(song_fields, candidate)
        scored.append(
            {
                "beatport_track_id": candidate.get("beatport_track_id"),
                "name": candidate.get("name"),
                "mix_name": candidate.get("mix_name"),
                "artists": candidate.get("artists"),
                "label": candidate.get("label"),
                "duration_seconds": candidate.get("duration_seconds"),
                "bpm": candidate.get("bpm"),
                "key": candidate.get("key"),
                "artwork_url": candidate.get("artwork_url"),
                "score": result["score"],
                "components": result["components"],
                "duration_delta": result["duration_delta"],
                "payload": candidate,
            }
        )
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:top_n]


def classify(best):
    """
    "applied" | "needs_review" | "no_match" for the best-scoring candidate
    dict (as produced by rank_candidates), or None when there were no
    candidates at all.
    """
    if best is None:
        return "no_match"
    score = best["score"]
    components = best["components"]
    duration_delta = best.get("duration_delta")
    if (
        score >= AUTO_APPLY_THRESHOLD
        and (components.get("title") or 0.0) >= AUTO_APPLY_TITLE_MIN
        and (components.get("artist") or 0.0) >= AUTO_APPLY_ARTIST_MIN
        and duration_delta is not None
        and duration_delta <= AUTO_APPLY_DURATION_DELTA_MAX
    ):
        return "applied"
    if score >= REVIEW_THRESHOLD:
        return "needs_review"
    return "no_match"
