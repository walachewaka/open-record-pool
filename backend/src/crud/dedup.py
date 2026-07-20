"""
Read-side CRUD for the admin duplicates surface (MOO-90): keyset-paginated
candidate pages with batched song/analysis embeds (never N+1 -- MOO-77 D6),
candidate detail, and the per-recording version history.
"""
from fastapi import HTTPException

from src.database.models import (
    DuplicateCandidates,
    RecordingLinks,
    Recordings,
    Songs,
    TrackAnalysis,
)
from src.services import quality
from src.utils.normalize import normalize_title

CANDIDATE_STATUSES = (
    "pending",
    "proposed",
    "auto_resolved",
    "confirmed",
    "rejected",
)

_BATCH = 1000


def _chunks(values, size=_BATCH):
    for start in range(0, len(values), size):
        end = start + size
        yield values[start:end]


async def _analysis_map(song_ids):
    result = {}
    for chunk in _chunks(list(song_ids)):
        for row in await TrackAnalysis.filter(song_id__in=chunk):
            result[row.song_id] = row
    return result


def song_version_dict(song, analysis=None, trust=None):
    """The SongVersionOut payload for one version (quality computed live)."""
    detail = quality.quality_breakdown(song, analysis, trust)
    return {
        "id": song.id,
        "title": song.title,
        "artist": song.artist,
        "album": song.album,
        "mix_norm": normalize_title(song.title)[1],
        "duration_seconds": song.duration_seconds,
        "bitrate_kbps": song.bitrate_kbps,
        "effective_bitrate_kbps": detail["effective_bitrate_kbps"] or None,
        "format_class": detail["format_class"],
        "sample_rate_hz": detail["sample_rate_hz"],
        "spectral_cutoff_hz": detail["spectral_cutoff_hz"],
        "suspect_transcode": detail["suspect_transcode"],
        "source": song.source,
        "file_path": song.file_path,
        "file_size_bytes": song.file_size_bytes,
        "version_status": song.version_status,
        "quality_breakdown": song.quality_breakdown or detail,
        "created_at": song.created_at,
    }


def _candidate_dict(row, songs, analyses):
    song_a = songs[row.song_a_id]
    song_b = songs[row.song_b_id]
    return {
        "id": row.id,
        "layer": row.layer,
        "similarity": row.similarity,
        "confidence": row.confidence,
        "duration_delta": row.duration_delta,
        "status": row.status,
        "suggested_winner_id": row.suggested_winner_id,
        "recording_id": row.recording_id,
        "created_at": row.created_at,
        "song_a": song_version_dict(song_a, analyses.get(song_a.id)),
        "song_b": song_version_dict(song_b, analyses.get(song_b.id)),
    }


async def _embed_maps(rows):
    song_ids = set()
    for row in rows:
        song_ids.add(row.song_a_id)
        song_ids.add(row.song_b_id)
    songs = {}
    for chunk in _chunks(list(song_ids)):
        for song in await Songs.filter(id__in=chunk):
            songs[song.id] = song
    return songs, await _analysis_map(song_ids)


async def list_candidates(status="pending", last_id=None, limit=50):
    """One keyset page (id DESC) of the duplicates queue."""
    if status not in CANDIDATE_STATUSES:
        raise HTTPException(
            status_code=422,
            detail="status must be one of: {}".format(", ".join(CANDIDATE_STATUSES)),
        )
    query = DuplicateCandidates.filter(status=status)
    if last_id is not None:
        query = query.filter(id__lt=last_id)
    rows = await query.order_by("-id").limit(limit)
    songs, analyses = await _embed_maps(rows)
    items = [_candidate_dict(row, songs, analyses) for row in rows]
    return rows, items


async def get_candidate(candidate_id):
    """The full candidate row + embedded pair, 404 on unknown ids."""
    row = await DuplicateCandidates.get_or_none(id=candidate_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Duplicate candidate not found")
    songs, analyses = await _embed_maps([row])
    data = _candidate_dict(row, songs, analyses)
    data["resolution"] = row.resolution
    data["resolved_by_id"] = row.resolved_by_id
    data["resolved_at"] = row.resolved_at
    return row, data


async def get_recording(recording_id):
    """A recording with its version history and related cuts, or 404."""
    rec = await Recordings.get_or_none(id=recording_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    versions = await Songs.filter(recording_id=rec.id).order_by("id")
    analyses = await _analysis_map([song.id for song in versions])
    links = list(await RecordingLinks.filter(recording_a_id=rec.id)) + list(
        await RecordingLinks.filter(recording_b_id=rec.id)
    )
    other_ids = [
        link.recording_b_id if link.recording_a_id == rec.id else link.recording_a_id
        for link in links
    ]
    others = {}
    for chunk in _chunks(other_ids):
        for other in await Recordings.filter(id__in=chunk):
            others[other.id] = other
    related = []
    for link in links:
        other_id = (
            link.recording_b_id
            if link.recording_a_id == rec.id
            else link.recording_a_id
        )
        other = others.get(other_id)
        related.append(
            {
                "recording_id": other_id,
                "kind": link.kind,
                "similarity": link.similarity,
                "title_norm": other.title_norm if other else None,
                "mix_norm": other.mix_norm if other else None,
            }
        )
    return rec, {
        "id": rec.id,
        "artist_norm": rec.artist_norm,
        "title_norm": rec.title_norm,
        "mix_norm": rec.mix_norm,
        "duration_seconds": rec.duration_seconds,
        "canonical_song_id": rec.canonical_song_id,
        "isrc": rec.isrc,
        "musicbrainz_id": rec.musicbrainz_id,
        "beatport_id": rec.beatport_id,
        "spotify_id": rec.spotify_id,
        "versions": [
            song_version_dict(song, analyses.get(song.id)) for song in versions
        ],
        "related": related,
    }
