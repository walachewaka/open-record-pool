"""
Version quality ranking (MOO-90 D5).

quality_tuple() scores one version of a recording as a lexicographic tuple
compared element by element -- never a weighted sum, so a lossless file can
never be outvoted by tiebreakers. The transcode-fake killer is rule 2: the
effective bitrate is capped by what the spectral cutoff (MOO-87 analyzer)
proves the audio actually contains, so an upscaled 128->320 file ranks as
its true quality. Declared bitrate is never trusted on its own.
"""
import json

LOSSLESS_FORMATS = ("flac", "wav", "aiff", "aif", "alac")

# spectral cutoff -> the bitrate class the audio actually supports (D5).
# Ordered highest first; a cutoff at/above the threshold implies the class.
SPECTRAL_BITRATE_STEPS = (
    (20000, None),  # full spectrum: trust the declared bitrate
    (19000, 320),
    (17500, 256),
    (16500, 192),
    (15500, 160),
    (0, 128),
)

# Default source-trust ranking (D5 rule 6), overridable via the
# library.dedup_source_trust setting (a JSON object string).
DEFAULT_SOURCE_TRUST = {
    "beatport": 100,
    "purchase": 100,
    "library": 70,
    "upload": 60,
    "spotdl": 50,
    "scdl": 40,
    "youtube": 30,
    "unknown": 20,
}

# A true peak above this (dBTP) counts as hard clipping (integrity rule 5).
CLIPPING_TRUE_PEAK_DB = 0.3

# "suspect transcode": declared lossless or >= this bitrate while the
# spectral map lands >= 2 steps below the declared class.
SUSPECT_MIN_DECLARED_KBPS = 256


def _format_class(codec):
    if codec and codec.lower() in LOSSLESS_FORMATS:
        return 2
    return 1


def _spectral_implied_kbps(cutoff_hz):
    """The bitrate class the spectrum supports, or None for full spectrum."""
    for threshold, implied in SPECTRAL_BITRATE_STEPS:
        if cutoff_hz >= threshold:
            return implied
    return 128


def source_trust_map(raw=None):
    """The effective source-trust map: defaults overlaid with the setting."""
    trust = dict(DEFAULT_SOURCE_TRUST)
    if raw:
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(parsed, dict):
                for key, value in parsed.items():
                    trust[str(key)] = int(value)
        except (ValueError, TypeError):
            pass
    return trust


def quality_breakdown(song, analysis=None, trust=None):
    """
    The full D5 score detail for one version as a dict (persisted to
    songs.quality_breakdown and shown in the admin drawer). [analysis] is
    the song's TrackAnalysis row or None when the analyzer has not run.
    """
    trust = trust or DEFAULT_SOURCE_TRUST
    codec = (analysis.codec if analysis else None) or song.codec or "mp3"
    format_class = _format_class(codec)
    declared = song.bitrate_kbps or 0
    cutoff = analysis.spectral_cutoff_hz if analysis else None

    suspect = False
    verified = cutoff is not None
    if cutoff is None:
        effective = declared
    else:
        implied = _spectral_implied_kbps(cutoff)
        if format_class == 2:
            # A lossless container whose spectrum dies below 19 kHz is an
            # upscaled fake: rank it at the lossy ceiling and flag it.
            if cutoff < 19000:
                effective = 320
                suspect = True
            else:
                effective = declared or 1411
        elif implied is None:
            effective = declared
        else:
            effective = min(declared, implied) if declared else implied
            if declared >= SUSPECT_MIN_DECLARED_KBPS and implied <= declared - 64:
                suspect = True

    decode_ok = analysis.decode_ok if analysis else None
    true_peak = analysis.true_peak_dbtp if analysis else None
    integrity = 1
    if decode_ok is False:
        integrity = 0
    if true_peak is not None and true_peak > CLIPPING_TRUE_PEAK_DB:
        integrity = 0

    sample_rate = (analysis.sample_rate_hz if analysis else None) or 44100
    return {
        "format_class": format_class,
        "codec": codec,
        "declared_bitrate_kbps": declared or None,
        "effective_bitrate_kbps": int(effective) if effective else 0,
        "spectral_cutoff_hz": cutoff,
        "verified": verified,
        "suspect_transcode": suspect,
        "sample_rate_hz": sample_rate,
        "integrity": integrity,
        "source": song.source or "unknown",
        "source_trust": int(trust.get(song.source or "unknown", trust["unknown"])),
        "file_size_bytes": song.file_size_bytes or 0,
    }


def tuple_from_breakdown(detail):
    """The comparable lexicographic tuple for a breakdown dict (D5 order)."""
    return (
        detail["format_class"],
        detail["effective_bitrate_kbps"],
        detail["sample_rate_hz"],
        0 if detail["suspect_transcode"] else 1,
        detail["integrity"],
        detail["source_trust"],
        detail["file_size_bytes"],
    )


def quality_tuple(song, analysis=None, trust=None):
    """The D5 quality tuple for one version. Strictly greater wins."""
    return tuple_from_breakdown(quality_breakdown(song, analysis, trust))


def hypothetical_tuple(source=None, declared_bitrate_kbps=None, format=None):
    """
    A pessimistic quality tuple from download-engine hints only (MOO-78
    pre-download check): no spectral proof yet, so nothing is verified and
    unknowns score low. Used to answer would_improve before any bytes move.
    """
    codec = (format or "").lower() or "mp3"
    format_class = _format_class(codec)
    effective = declared_bitrate_kbps or (1411 if format_class == 2 else 0)
    trust = DEFAULT_SOURCE_TRUST
    return (
        format_class,
        int(effective),
        44100,
        1,
        1,
        int(trust.get(source or "unknown", trust["unknown"])),
        0,
    )
