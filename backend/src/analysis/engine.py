"""
Pass-2 analysis primitives (MOO-87 D1/D2): the four subprocess steps of the
analyze_track job plus the streaming file hash. Each function is synchronous
(the task runs them in a thread executor), returns a plain dict, and raises
AnalysisStepError on failure so the task can fault-isolate per step.

These five module-level names -- decode_and_measure, loudness_and_silence,
bpm_and_key, fingerprint, file_sha256 -- are the BINDING mock seam for the
test harnesses: tasks call them via `engine.<name>(...)` attribute lookup so
monkeypatching this module covers inline end-to-end runs. Harness tests never
shell out to ffmpeg/fpcalc and never import numpy/librosa; accordingly every
heavy import here is lazy inside a function body (SECURITY.md 9: every
subprocess is an argv array, never a shell, with a hard timeout).
"""
import hashlib
import json
import os
import re
import subprocess
import time

FFMPEG_PATH = os.environ.get("FFMPEG_PATH", "ffmpeg")
FPCALC_PATH = os.environ.get("FPCALC_PATH", "fpcalc")

SUBPROCESS_TIMEOUT = 300  # seconds, per external process
PEAK_COUNT = 1000
FINGERPRINT_SECONDS = 120
BPM_SECONDS = 180
BPM_SAMPLE_RATE = 22050

_CHUNK = 1024 * 1024
_DECODE_RATE = 44100
_DECODE_CHANNELS = 2
_BYTES_PER_FRAME = 2 * _DECODE_CHANNELS  # s16le stereo
# 0.1 s of interleaved s16le stereo values per coarse peak window.
_WINDOW_VALUES = 4410 * _DECODE_CHANNELS
_SPECTRAL_SECONDS = 30
_SPECTRAL_FRAME = 8192
_SPECTRAL_FLOOR_DB = 60.0


class AnalysisStepError(Exception):
    """One analysis step failed; the other steps still run (D2)."""


def _ffmpeg_decode_argv(path, extra):
    return (
        [
            FFMPEG_PATH,
            "-nostdin",
            "-hide_banner",
            "-v",
            "error",
            "-threads",
            "1",
            "-i",
            str(path),
            "-map",
            "a:0",
        ]
        + extra
        + ["-"]
    )


def file_sha256(path):
    """Streaming sha256 of the file bytes (1 MiB chunks, never whole-file)."""
    digest = hashlib.sha256()
    with open(str(path), "rb") as handle:
        while True:
            chunk = handle.read(_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _resample_max(values, count):
    """Bucket-max resample a list of floats to exactly [count] entries."""
    total = len(values)
    out = []
    for i in range(count):
        start = (i * total) // count
        end = max(start + 1, ((i + 1) * total) // count)
        out.append(max(values[start:end]))
    return out


def _spectral_cutoff(spec_bytes, numpy):
    """
    The highest frequency (Hz) whose mean-spectrum energy is within 60 dB of
    the peak bin, from the middle-of-track PCM snapshot. None when the
    snapshot is too short. Feeds the fake-bitrate heuristic (a true 320 kbps
    MP3 keeps content past ~19 kHz; a 128->320 upscale cuts near 16 kHz).
    """
    samples = numpy.frombuffer(spec_bytes, dtype=numpy.int16)
    usable = (len(samples) // _DECODE_CHANNELS) * _DECODE_CHANNELS
    if usable < _SPECTRAL_FRAME * _DECODE_CHANNELS:
        return None
    mono = (
        samples[:usable]
        .reshape(-1, _DECODE_CHANNELS)
        .astype(numpy.float32)
        .mean(axis=1)
    )
    frames = len(mono) // _SPECTRAL_FRAME
    spectrum = numpy.zeros(_SPECTRAL_FRAME // 2 + 1, dtype=numpy.float64)
    window = numpy.hanning(_SPECTRAL_FRAME)
    for i in range(frames):
        start = i * _SPECTRAL_FRAME
        end = start + _SPECTRAL_FRAME
        spectrum += numpy.abs(numpy.fft.rfft(mono[start:end] * window))
    spectrum /= max(frames, 1)
    peak = float(spectrum.max())
    if peak <= 0.0:
        return None
    threshold = peak / (10.0 ** (_SPECTRAL_FLOOR_DB / 20.0))
    above = numpy.nonzero(spectrum >= threshold)[0]
    if len(above) == 0:
        return None
    return int(round(int(above[-1]) * _DECODE_RATE / float(_SPECTRAL_FRAME)))


def decode_and_measure(path, duration_hint=None):
    """
    Step 1 (D2): ONE streamed s16le/44100/stereo ffmpeg decode pass producing
    simultaneously (a) pcm_sha256 -- sha256 of the raw decoded PCM, MOO-90's
    layer-2 hash, (b) the 1000-bucket normalized waveform peaks, (c) the
    middle-30s mean-spectrum cutoff for the fake-bitrate heuristic. Memory is
    O(chunk): the PCM is never held whole. Raises AnalysisStepError on decode
    failure (corrupt/truncated file detection).
    """
    import numpy

    argv = _ffmpeg_decode_argv(
        path,
        ["-f", "s16le", "-acodec", "pcm_s16le", "-ar", str(_DECODE_RATE), "-ac", "2"],
    )
    # Middle-30s snapshot bounds, from the tag duration when known (the
    # stream length is unknown until EOF); early-but-past-intro fallback.
    if duration_hint and duration_hint > _SPECTRAL_SECONDS:
        spec_start = ((duration_hint - _SPECTRAL_SECONDS) / 2.0) * (
            _DECODE_RATE * _BYTES_PER_FRAME
        )
    else:
        spec_start = 0.0
    spec_start = int(spec_start) - (int(spec_start) % _BYTES_PER_FRAME)
    spec_end = spec_start + _SPECTRAL_SECONDS * _DECODE_RATE * _BYTES_PER_FRAME

    digest = hashlib.sha256()
    window_maxima = []
    carry = numpy.empty(0, dtype=numpy.int16)
    spec_parts = []
    total_bytes = 0
    deadline = time.monotonic() + SUBPROCESS_TIMEOUT

    proc = subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        while True:
            if time.monotonic() > deadline:
                raise AnalysisStepError("decode timed out")
            chunk = proc.stdout.read(_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
            if spec_start < total_bytes + len(chunk) and total_bytes < spec_end:
                lo = max(spec_start - total_bytes, 0)
                hi = min(spec_end - total_bytes, len(chunk))
                spec_parts.append(chunk[lo:hi])
            total_bytes += len(chunk)
            samples = numpy.frombuffer(chunk, dtype=numpy.int16)
            if len(carry):
                samples = numpy.concatenate([carry, samples])
            full = (len(samples) // _WINDOW_VALUES) * _WINDOW_VALUES
            if full:
                windows = samples[:full].reshape(-1, _WINDOW_VALUES)
                maxima = numpy.abs(windows.astype(numpy.int32)).max(axis=1)
                window_maxima.extend(float(m) for m in maxima)
            carry = samples[full:].copy()
        stderr = proc.stderr.read()
        proc.wait(timeout=30)
    finally:
        try:
            proc.kill()
        except OSError:
            pass
    if len(carry):
        window_maxima.append(float(numpy.abs(carry.astype(numpy.int32)).max()))
    duration = total_bytes / float(_DECODE_RATE * _BYTES_PER_FRAME)
    # Decode check: fail hard on empty output or a truncated stream (< 90%
    # of the tag duration when known). A nonzero exit alone is NOT fatal --
    # real-world MP3s carry the odd corrupt frame or trailing junk that
    # ffmpeg reports (and exits nonzero for) while still decoding the whole
    # track; that becomes a quality warning, not a failed analysis.
    truncated = (
        duration_hint is not None
        and duration_hint > 1.0
        and duration < 0.9 * duration_hint
    )
    if total_bytes == 0 or (proc.returncode != 0 and truncated):
        tail = (stderr or b"").decode("utf-8", "replace")[-400:]
        raise AnalysisStepError(
            "ffmpeg decode failed (rc={}, decoded {:.1f}s of {}s): {}".format(
                proc.returncode, duration, duration_hint, tail
            )
        )
    warnings = None
    if proc.returncode != 0:
        warnings = (stderr or b"").decode("utf-8", "replace")[-300:].replace("\x00", "")

    peaks = _resample_max(window_maxima, PEAK_COUNT)
    peaks = [round(min(value / 32768.0, 1.0), 3) for value in peaks]
    return {
        "pcm_sha256": digest.hexdigest(),
        "peaks": peaks,
        "duration_seconds": round(duration, 3),
        "spectral_cutoff_hz": _spectral_cutoff(b"".join(spec_parts), numpy),
        "decode_warnings": warnings,
    }


def loudness_and_silence(path, duration_hint=None):
    """
    Step 2 (D2): one combined ffmpeg filter pass -- EBU R128 loudness
    (integrated LUFS, LRA, true peak) and leading/trailing silence offsets
    for clean cue-in/cue-out points. Parses the filters' stderr output; the
    running ebur128 lines are superseded by taking the LAST match (the
    summary block prints last).
    """
    argv = [
        FFMPEG_PATH,
        "-nostdin",
        "-hide_banner",
        "-nostats",
        "-threads",
        "1",
        "-i",
        str(path),
        "-map",
        "a:0",
        "-af",
        "silencedetect=noise=-45dB:d=1.0,ebur128=peak=true",
        "-f",
        "null",
        "-",
    ]
    try:
        result = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=SUBPROCESS_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise AnalysisStepError("loudness pass timed out")
    stderr = (result.stderr or b"").decode("utf-8", "replace")
    integrated = re.findall(r"\bI:\s*(-?[\d.]+)\s*LUFS", stderr)
    # Same tolerance as the decode pass: corrupt frames make ffmpeg exit
    # nonzero while the filters still processed the track -- only fail when
    # no loudness summary was produced at all.
    if result.returncode != 0 and not integrated:
        raise AnalysisStepError(
            "ffmpeg loudness pass failed (rc={}): {}".format(
                result.returncode, stderr[-400:]
            )
        )

    lra = re.findall(r"\bLRA:\s*(-?[\d.]+)\s*LU\b", stderr)
    # ffmpeg's ebur128 summary labels the true-peak value in dBFS (a true
    # peak in dBFS IS the dBTP figure); older builds said dBTP -- accept both.
    peak = re.findall(r"\bPeak:\s*(-?[\d.]+)\s*dB(?:TP|FS)", stderr)
    starts = [float(v) for v in re.findall(r"silence_start:\s*(-?[\d.]+)", stderr)]
    ends = [float(v) for v in re.findall(r"silence_end:\s*(-?[\d.]+)", stderr)]

    cue_in = 0.0
    cue_out = duration_hint
    if starts:
        if starts[0] <= 0.5 and ends:
            cue_in = ends[0]
        if len(ends) < len(starts):
            # The last silence ran to EOF (no matching silence_end).
            cue_out = starts[-1]
        elif duration_hint is not None and abs(ends[-1] - duration_hint) < 0.5:
            cue_out = starts[-1]
    return {
        "loudness_lufs": float(integrated[-1]) if integrated else None,
        "loudness_range": float(lra[-1]) if lra else None,
        "true_peak_dbtp": float(peak[-1]) if peak else None,
        "cue_in_s": cue_in,
        "cue_out_s": cue_out,
    }


def _mem_capped_seconds():
    """
    The BPM/key analysis window under the ANALYZER_MAX_MEM_MB ceiling (D4):
    the decoded buffer costs ~6 bytes per sample at peak (s16le + float32
    copy), so the default 512 MB never truncates the 180 s window -- only
    deliberately tiny ceilings do. No rlimit games (they corrupt numba).
    """
    mem_mb = int(os.environ.get("ANALYZER_MAX_MEM_MB", "512"))
    cap = int((mem_mb * 1024 * 1024) / (BPM_SAMPLE_RATE * 6))
    return max(10, min(BPM_SECONDS, cap))


def bpm_and_key(path, max_seconds=None):
    """
    Step 3 (D2): BPM + musical key on the first [max_seconds] of the track,
    decoded mono/22050 (enough for DJ material, bounds memory to ~16 MB).
    librosa/numpy are imported lazily -- worker-only heavy dependencies.
    """
    import numpy

    from src.analysis import keydetect

    if max_seconds is None:
        max_seconds = _mem_capped_seconds()

    argv = _ffmpeg_decode_argv(
        path,
        [
            "-t",
            str(int(max_seconds)),
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            "-ar",
            str(BPM_SAMPLE_RATE),
            "-ac",
            "1",
        ],
    )
    proc = subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        out, err = proc.communicate(timeout=SUBPROCESS_TIMEOUT)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise AnalysisStepError("bpm/key decode timed out")
    # Ten decoded seconds are enough signal for tempo/key; only a (near-)empty
    # stream is fatal (nonzero exits happen on merely-scuffed files, see
    # decode_and_measure).
    if not out or (proc.returncode != 0 and len(out) < 10 * BPM_SAMPLE_RATE * 2):
        tail = (err or b"").decode("utf-8", "replace")[-400:]
        raise AnalysisStepError(
            "ffmpeg bpm/key decode failed (rc={}): {}".format(proc.returncode, tail)
        )

    samples = numpy.frombuffer(out, dtype=numpy.int16)
    y = samples.astype(numpy.float32) / 32768.0

    import librosa

    rhythm = getattr(librosa.feature, "rhythm", None)
    tempo_fn = getattr(rhythm, "tempo", None) if rhythm else None
    if tempo_fn is None:  # pre-0.10 fallback
        tempo_fn = librosa.beat.tempo
    tempo = tempo_fn(y=y, sr=BPM_SAMPLE_RATE)
    bpm = round(float(numpy.atleast_1d(tempo)[0]), 1)

    chroma = librosa.feature.chroma_cqt(y=y, sr=BPM_SAMPLE_RATE)
    key, confidence = keydetect.detect_key(chroma.mean(axis=1))
    return {
        "bpm": bpm,
        "key": key,
        "key_confidence": None if confidence is None else round(confidence, 4),
        "window_seconds": max_seconds,
    }


def fingerprint(path, length_seconds=FINGERPRINT_SECONDS):
    """
    Step 4 (D2): the Chromaprint acoustic fingerprint via fpcalc -json --
    base64-compressed, AcoustID-submittable, survives re-encodes and tag
    edits (MOO-90's layer-3 dedup evidence).
    """
    argv = [FPCALC_PATH, "-json", "-length", str(int(length_seconds)), str(path)]
    try:
        result = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=SUBPROCESS_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise AnalysisStepError("fpcalc timed out")
    # fpcalc exits non-zero on decode warnings (e.g. a truncated final MP3
    # frame) while still printing a complete fingerprint to stdout -- accept
    # any output that parses, and only report rc/stderr when nothing usable
    # was produced.
    try:
        data = json.loads(result.stdout.decode("utf-8", "replace"))
        value = data["fingerprint"]
        if not str(value):
            raise KeyError("fingerprint")
    except (ValueError, KeyError) as error:
        if result.returncode != 0:
            tail = (result.stderr or b"").decode("utf-8", "replace")[-400:]
            raise AnalysisStepError(
                "fpcalc failed (rc={}): {}".format(result.returncode, tail)
            )
        raise AnalysisStepError("fpcalc returned unparseable output: {}".format(error))
    return {
        "fingerprint": str(value),
        "fingerprint_algo": "chromaprint",
        "duration_seconds": float(data.get("duration") or 0.0),
    }
