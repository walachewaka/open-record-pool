"""
Analyzer versioning (MOO-87 D3).

ANALYZER_VERSION stamps every track_analysis row for provenance. The
per-field versions make re-analysis surgical at millions-of-tracks scale:
bumping ONE constant here marks only that field stale, so the next backfill
recomputes just that pass (e.g. a new BPM algorithm re-runs only the BPM
step) instead of re-decoding the whole library.
"""

ANALYZER_VERSION = 1

FIELD_VERSIONS = {
    "technical": 1,
    "bpm": 1,
    "key": 1,
    "loudness": 1,
    "waveform": 1,
    "fingerprint": 1,
    "spectral": 1,
}

# The names accepted by the backfill request's "fields" list.
ANALYSIS_FIELDS = sorted(FIELD_VERSIONS.keys())
