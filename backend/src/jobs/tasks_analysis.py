"""
The ingestion-analyzer job bodies (MOO-87): analyze_track (pass 2, consumed
from orp:heavy by worker-heavy) and analyze_library (the throttled backfill
walker on orp:default). Same conventions as src/jobs/tasks.py: every task
takes (ctx, job_id), records its own lifecycle on the jobs row, and never
propagates exceptions to the transport.

The engine steps run in a thread executor (they block on subprocesses /
numpy) and are fault-isolated per D2: a failing step nulls its own fields
and records the error while the other steps still land.
"""
import asyncio
import hashlib
import json
import os
from datetime import datetime, timezone

from src.analysis import dispatch, engine
from src.analysis import technical as technical_mod
from src.analysis.versions import ANALYSIS_FIELDS, ANALYZER_VERSION, FIELD_VERSIONS
from src.database.models import Jobs, Songs, TrackAnalysis
from src.utils import storage
from src.utils.camelot import to_camelot

# D5: tag vs detected BPM disagreement beyond this flags a mismatch; exact
# half/double-time detections are deliberately NOT mismatches.
BPM_MISMATCH_TOLERANCE = 2.0

WAVEFORM_VERSION = 1
WAVEFORM_ALGORITHM = "ffmpeg-pcm-max"

# Fake-bitrate heuristic (D2): a declared >=256 kbps stream whose spectrum
# dies below 17 kHz is very likely a 128->320 upscale.
FAKE_BITRATE_MIN_KBPS = 256
FAKE_BITRATE_CUTOFF_HZ = 17000

_BATCH = 1000
_THROTTLE_POLL_SECONDS = 5


def _utcnow():
    return datetime.now(timezone.utc)


async def _run_blocking(func, *args):
    """Run one synchronous engine step off the event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func, *args)


def _bpm_mismatch(tag_bpm, detected_bpm):
    """D5: None unless both exist; half/double-time is not a mismatch."""
    if tag_bpm is None or detected_bpm is None:
        return None
    candidates = (detected_bpm, detected_bpm * 2.0, detected_bpm / 2.0)
    for candidate in candidates:
        if abs(tag_bpm - candidate) <= BPM_MISMATCH_TOLERANCE:
            return False
    return True


def _key_mismatch(tag_key, detected_key):
    """D5: compared in Camelot space so "Am" vs "A minor" never flags."""
    if not tag_key or not detected_key:
        return None
    tag_camelot = to_camelot(tag_key)
    detected_camelot = to_camelot(detected_key)
    if tag_camelot is None or detected_camelot is None:
        return None
    return tag_camelot != detected_camelot


def _requested_fields(payload):
    fields = payload.get("fields") or None
    if not fields:
        return list(ANALYSIS_FIELDS)
    return [field for field in ANALYSIS_FIELDS if field in fields]


def _stale_fields(row, checksum, requested, force):
    """Which requested fields need (re)computation (D3 idempotency)."""
    if force:
        return list(requested)
    versions = row.field_versions or {}
    if row.checksum_sha256 != checksum:
        return list(requested)
    return [
        field for field in requested if versions.get(field) != FIELD_VERSIONS[field]
    ]


async def _write_waveform(song, peaks, duration_seconds):
    """The binding waveform artifact (D6), content-addressed by file sha."""
    body = {
        "version": WAVEFORM_VERSION,
        "algorithm": WAVEFORM_ALGORITHM,
        "count": len(peaks),
        "duration_seconds": duration_seconds,
        "peaks": peaks,
    }
    data = json.dumps(body, separators=(",", ":")).encode("utf-8")
    await storage.store_artifact_bytes(
        data, song.checksum_sha256, kind="waveform", ext="json"
    )
    return len(peaks)


async def _analyze_song(song, force, requested):
    """
    Run the stale steps for one song and persist everything. Returns the
    result summary dict for the jobs row.
    """
    if not song.checksum_sha256:
        # Lazy legacy backfill (MOO-77 assigned it to this stage): rows that
        # predate the sharded storage get their content hash here.
        song.checksum_sha256 = await _run_blocking(engine.file_sha256, song.file_path)
        await song.save(update_fields=["checksum_sha256", "modified_at"])

    row = await dispatch.ensure_analysis_row(song.id)
    checksum = song.checksum_sha256
    stale = _stale_fields(row, checksum, requested, force)
    if not stale:
        return {
            "song_id": song.id,
            "skipped": "fresh",
            "pass2_status": row.pass2_status,
        }

    row.pass2_status = "running"
    await row.save(update_fields=["pass2_status", "modified_at"])

    errors = []
    versions = dict(row.field_versions or {})
    duration_hint = song.duration_seconds
    song_updates = set()

    # Pass-1 refresh rides along when requested (cheap, mutagen-only).
    if "technical" in stale:
        try:
            technical = await _run_blocking(
                technical_mod.extract_technical, song.file_path
            )
            for field, value in technical.items():
                setattr(row, field, value)
            row.pass1_status = "succeeded"
            row.pass1_at = _utcnow()
            versions["technical"] = FIELD_VERSIONS["technical"]
        except Exception as error:
            row.pass1_status = "failed"
            errors.append("technical: {}".format(error))

    # Step 1 -- streamed decode: pcm hash + waveform peaks + spectral cutoff.
    decode_failed = False
    if "waveform" in stale or "spectral" in stale:
        try:
            measured = await _run_blocking(
                engine.decode_and_measure, song.file_path, duration_hint
            )
            row.decode_ok = True
            if measured.get("decode_warnings"):
                flags = dict(row.quality_flags or {})
                flags["decode_warnings"] = measured["decode_warnings"]
                row.quality_flags = flags
            row.pcm_sha256 = measured["pcm_sha256"]
            if "waveform" in stale:
                row.waveform_peaks_count = await _write_waveform(
                    song, measured["peaks"], measured["duration_seconds"]
                )
                song.waveform_ready = True
                song_updates.add("waveform_ready")
                versions["waveform"] = FIELD_VERSIONS["waveform"]
            if "spectral" in stale:
                row.spectral_cutoff_hz = measured["spectral_cutoff_hz"]
                flags = dict(row.quality_flags or {})
                flags["fake_bitrate_suspect"] = bool(
                    song.bitrate_kbps
                    and measured["spectral_cutoff_hz"] is not None
                    and song.bitrate_kbps >= FAKE_BITRATE_MIN_KBPS
                    and measured["spectral_cutoff_hz"] < FAKE_BITRATE_CUTOFF_HZ
                )
                row.quality_flags = flags
                versions["spectral"] = FIELD_VERSIONS["spectral"]
        except Exception as error:
            decode_failed = True
            row.decode_ok = False
            errors.append("decode: {}".format(error))

    # Steps 2-4 are skipped only when the decode check proved the file
    # unreadable (D2); each is otherwise independently fault-isolated.
    if not decode_failed:
        if "loudness" in stale:
            try:
                loudness = await _run_blocking(
                    engine.loudness_and_silence, song.file_path, duration_hint
                )
                row.loudness_lufs = loudness["loudness_lufs"]
                row.loudness_range = loudness["loudness_range"]
                row.true_peak_dbtp = loudness["true_peak_dbtp"]
                row.cue_in_s = loudness["cue_in_s"]
                row.cue_out_s = loudness["cue_out_s"]
                versions["loudness"] = FIELD_VERSIONS["loudness"]
            except Exception as error:
                errors.append("loudness: {}".format(error))

        if "bpm" in stale or "key" in stale:
            try:
                detected = await _run_blocking(engine.bpm_and_key, song.file_path)
                window = detected.get("window_seconds")
                if (
                    window is not None
                    and duration_hint is not None
                    and window < duration_hint
                    and window < engine.BPM_SECONDS
                ):
                    # ANALYZER_MAX_MEM_MB shrank the analysis window (D4).
                    flags = dict(row.quality_flags or {})
                    flags["analysis_truncated"] = True
                    row.quality_flags = flags
                if "bpm" in stale:
                    row.bpm_detected = detected["bpm"]
                    row.bpm_mismatch = _bpm_mismatch(song.bpm, detected["bpm"])
                    song.bpm_detected = detected["bpm"]
                    song_updates.add("bpm_detected")
                    versions["bpm"] = FIELD_VERSIONS["bpm"]
                if "key" in stale:
                    row.key_detected = detected["key"]
                    row.key_confidence = detected["key_confidence"]
                    row.key_mismatch = _key_mismatch(song.musical_key, detected["key"])
                    song.key_detected = detected["key"]
                    song_updates.add("key_detected")
                    versions["key"] = FIELD_VERSIONS["key"]
            except Exception as error:
                errors.append("bpm/key: {}".format(error))

        if "fingerprint" in stale:
            try:
                printed = await _run_blocking(engine.fingerprint, song.file_path)
                row.fingerprint = printed["fingerprint"]
                row.fingerprint_algo = printed["fingerprint_algo"]
                row.fingerprint_sha256 = hashlib.sha256(
                    printed["fingerprint"].encode("utf-8")
                ).hexdigest()
                versions["fingerprint"] = FIELD_VERSIONS["fingerprint"]
            except Exception as error:
                errors.append("fingerprint: {}".format(error))

    row.checksum_sha256 = checksum
    row.analyzer_version = ANALYZER_VERSION
    row.field_versions = versions
    row.pass2_status = "failed" if errors else "succeeded"
    row.pass2_at = _utcnow()
    # NUL-strip: subprocess stderr can carry \x00 and PG TEXT rejects it.
    row.error = "; ".join(errors).replace("\x00", "") if errors else None
    await row.save()
    if song_updates:
        song_updates.add("modified_at")
        await song.save(update_fields=sorted(song_updates))

    # MOO-79 reindex hook (D6): detected bpm/key/loudness become searchable.
    # outbox never raises, but analysis results must land even if it did.
    try:
        from src.search import outbox

        await outbox.enqueue_song_upsert(song.id)
        await outbox.nudge_drain()
    except Exception:
        pass

    # MOO-90 dedup hook: the fingerprint/pcm hash this pass produced feeds
    # the recording dedup stage, queued next on the same heavy tier. Never
    # blocks or fails the analysis result.
    try:
        from src.services.dedup import enqueue_dedup

        await enqueue_dedup(song.id)
    except Exception:
        pass

    return {
        "song_id": song.id,
        "pass2_status": row.pass2_status,
        "fields": stale,
        "errors": [text.replace("\x00", "") for text in errors] or None,
    }


async def analyze_track(ctx, job_id):
    """
    Pass 2 for one track (MOO-87): decode check, waveform peaks, spectral
    cutoff, loudness/silence, BPM/key, acoustic fingerprint. Idempotent and
    resumable: keyed by the file checksum + per-field analyzer versions, so
    an arq redelivery after a mid-batch kill overwrites its own partial
    output and a fresh re-enqueue of an unchanged file is a cheap skip.
    """
    job = await Jobs.get(id=job_id)
    if job.status == "cancelled":
        return
    job.status = "running"
    job.started_at = _utcnow()
    await job.save(update_fields=["status", "started_at"])

    payload = job.payload or {}
    try:
        song = await Songs.get_or_none(id=payload.get("song_id"))
        if song is None:
            result = {"song_id": payload.get("song_id"), "skipped": "song deleted"}
        else:
            result = await _analyze_song(
                song, bool(payload.get("force")), _requested_fields(payload)
            )
    except Exception as error:
        job.status = "failed"
        job.error = str(error).replace("\x00", "")
        job.finished_at = _utcnow()
        await job.save(update_fields=["status", "error", "finished_at"])
        # Never leave the analysis row stuck on "running": a crash between
        # the running-mark and the final save must stay visible + retryable.
        try:
            await TrackAnalysis.filter(
                song_id=payload.get("song_id"), pass2_status="running"
            ).update(pass2_status="failed", error=job.error)
        except Exception:
            pass
        return

    failed = result.get("pass2_status") == "failed"
    job.status = "failed" if failed else "succeeded"
    job.error = (
        "; ".join(result.get("errors") or []).replace("\x00", "") if failed else None
    )
    job.result = result
    job.progress = 1.0
    job.finished_at = _utcnow()
    await job.save(
        update_fields=["status", "error", "result", "progress", "finished_at"]
    )


async def backfill_pending():
    """Whether a library backfill is already queued or running (409 guard)."""
    return await Jobs.filter(
        kind="analyze_library", status__in=["queued", "running"]
    ).exists()


def _backfill_window():
    return max(1, int(os.environ.get("ANALYZE_BACKFILL_WINDOW", "200")))


def _is_fresh(analysis, checksum, requested):
    """Backfill-side staleness mirror of _stale_fields, on values() dicts."""
    if analysis is None:
        return False
    if not checksum or analysis["checksum_sha256"] != checksum:
        return False
    versions = analysis["field_versions"] or {}
    for field in requested:
        if versions.get(field) != FIELD_VERSIONS[field]:
            return False
    return True


async def analyze_library(ctx, job_id):
    """
    The backfill walker (MOO-87 D3): keyset-iterate every song, select the
    stale ones, and enqueue analyze_track jobs in throttled waves -- never
    more than ANALYZE_BACKFILL_WINDOW queued-or-running at once, so freshly
    ingested tracks entering the same orp:heavy queue wait at most one
    window while a millions-track backfill trickles behind them.
    """
    from src.jobs.queue import workers_enabled

    job = await Jobs.get(id=job_id)
    if job.status == "cancelled":
        return
    job.status = "running"
    job.started_at = _utcnow()
    await job.save(update_fields=["status", "started_at"])

    payload = job.payload or {}
    force = bool(payload.get("force"))
    fields = payload.get("fields") or None
    requested = _requested_fields(payload)
    window = _backfill_window()

    seen = 0
    enqueued = 0
    skipped = 0
    failed = 0
    total = await Songs.all().count()
    last_id = 0
    try:
        while True:
            batch = (
                await Songs.filter(id__gt=last_id)
                .order_by("id")
                .limit(_BATCH)
                .values_list("id", "checksum_sha256")
            )
            if not batch:
                break
            ids = [pair[0] for pair in batch]
            analyses = {
                item["song_id"]: item
                for item in await TrackAnalysis.filter(song_id__in=ids).values(
                    "song_id", "checksum_sha256", "field_versions"
                )
            }
            for song_id, checksum in batch:
                seen += 1
                if not force and _is_fresh(analyses.get(song_id), checksum, requested):
                    skipped += 1
                    continue
                while (
                    workers_enabled()
                    and await Jobs.filter(
                        kind="analyze_track", status__in=["queued", "running"]
                    ).count()
                    >= window
                ):
                    await asyncio.sleep(_THROTTLE_POLL_SECONDS)
                try:
                    created = await dispatch.enqueue_analysis(
                        song_id,
                        force=force,
                        fields=fields,
                        user_id=job.created_by_id,
                    )
                except Exception as error:
                    failed += 1
                    print(
                        "[analysis] backfill enqueue failed for song {}: {}".format(
                            song_id, error
                        )
                    )
                    continue
                if created is not None:
                    enqueued += 1
                else:
                    skipped += 1  # already queued/running
            last_id = ids[-1]
            if total:
                job.progress = min(seen / total, 1.0)
                await job.save(update_fields=["progress"])
    except Exception as error:
        job.status = "failed"
        job.error = str(error)
        job.finished_at = _utcnow()
        await job.save(update_fields=["status", "error", "finished_at"])
        return

    job.status = "succeeded"
    job.result = {
        "tracks_seen": seen,
        "enqueued": enqueued,
        "skipped_fresh": skipped,
        "failed": failed,
    }
    job.progress = 1.0
    job.finished_at = _utcnow()
    await job.save(update_fields=["status", "result", "progress", "finished_at"])
