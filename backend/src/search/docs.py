"""
Song model -> ES document mapping (MOO-79).

Docs are ALWAYS built fresh from PostgreSQL (the source of truth), never from
outbox payloads, so indexing the same song twice is idempotent. The bulk
variant fetches the play/download counts in one grouped query per aggregate,
never per song (MOO-77 N+1 rule).
"""
from tortoise.functions import Count

from src.database.models import Downloads, PlayEvents, TrackAnalysis
from src.utils.camelot import to_camelot

_BATCH = 1000


def _chunks(values, size=_BATCH):
    for start in range(0, len(values), size):
        end = start + size
        yield values[start:end]


async def _counts(model, song_ids):
    """A {song_id: count} map for the given songs, chunked (__in <= 1000)."""
    result = {}
    for chunk in _chunks(list(song_ids)):
        rows = (
            await model.filter(song_id__in=chunk)
            .annotate(count=Count("id"))
            .group_by("song_id")
            .values("song_id", "count")
        )
        for row in rows:
            result[row["song_id"]] = int(row["count"])
    return result


def _doc(song, play_count, download_count, loudness_lufs=None):
    # bpm / musical_key / camelot_key are indexed COALESCEd (MOO-87 D5): the
    # curated tag wins, the analyzer-detected value fills gaps -- so the ES
    # filters behave exactly like the PG ones. The detected values are also
    # indexed verbatim for provenance-aware queries.
    effective_key = song.musical_key or song.key_detected
    return {
        "id": song.id,
        "title": song.title,
        "artist": song.artist,
        "album": song.album,
        "album_artist": song.album_artist,
        "composer": song.composer,
        "label": song.label,
        "genre": song.genre,
        "comment": song.comment,
        "musical_key": effective_key,
        "camelot_key": to_camelot(effective_key),
        "year": song.year,
        "track_number": song.track_number,
        "disc_number": song.disc_number,
        "bpm": song.bpm if song.bpm is not None else song.bpm_detected,
        "bpm_detected": song.bpm_detected,
        "key_detected": song.key_detected,
        "loudness_lufs": loudness_lufs,
        "duration_seconds": song.duration_seconds,
        "bitrate_kbps": song.bitrate_kbps,
        "file_size_bytes": song.file_size_bytes,
        "codec": song.codec,
        "has_artwork": bool(song.has_artwork),
        "txxx": song.txxx_frames or {},
        "status": song.status,
        "source": song.source,
        "version_status": song.version_status,
        "recording_id": song.recording_id,
        "checksum_sha256": song.checksum_sha256,
        "uploaded_by_id": song.uploaded_by_id,
        "added_at": song.created_at.isoformat() if song.created_at else None,
        "play_count": play_count,
        "download_count": download_count,
    }


async def _loudness(song_ids):
    """A {song_id: loudness_lufs} map from track_analysis, chunked (MOO-87)."""
    result = {}
    for chunk in _chunks(list(song_ids)):
        rows = await TrackAnalysis.filter(song_id__in=chunk).values(
            "song_id", "loudness_lufs"
        )
        for row in rows:
            result[row["song_id"]] = row["loudness_lufs"]
    return result


async def build_song_docs(songs):
    """ES documents for a batch of Songs rows (grouped count queries)."""
    ids = [song.id for song in songs]
    plays = await _counts(PlayEvents, ids)
    downloads = await _counts(Downloads, ids)
    loudness = await _loudness(ids)
    return [
        _doc(
            song,
            plays.get(song.id, 0),
            downloads.get(song.id, 0),
            loudness.get(song.id),
        )
        for song in songs
    ]


async def build_song_doc(song):
    """The ES document for one Songs row."""
    docs = await build_song_docs([song])
    return docs[0]
