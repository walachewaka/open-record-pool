"""
API schemas for the ingestion analyzer (MOO-87).
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, validator

from src.analysis.versions import ANALYSIS_FIELDS


class TrackAnalysisOut(BaseModel):
    """
    The full track_analysis serialization for GET /songs/{id}/analysis.
    Before any analysis ran the endpoint returns this shape with both
    statuses "pending" and everything else null -- pollable from the moment
    a song exists. tags_json is only populated for callers holding
    edit_metadata (raw tag dumps can carry private comment frames).
    """

    song_id: int
    analyzer_version: Optional[int] = None
    field_versions: Optional[Dict[str, int]] = None
    pass1_status: str = "pending"
    pass2_status: str = "pending"
    pass1_at: Optional[datetime] = None
    pass2_at: Optional[datetime] = None
    error: Optional[str] = None
    codec: Optional[str] = None
    container: Optional[str] = None
    sample_rate_hz: Optional[int] = None
    channels: Optional[int] = None
    bitrate_mode: Optional[str] = None
    encoder: Optional[str] = None
    art_present: Optional[bool] = None
    art_format: Optional[str] = None
    art_width: Optional[int] = None
    art_height: Optional[int] = None
    art_bytes: Optional[int] = None
    tags_json: Optional[Dict[str, Any]] = None
    decode_ok: Optional[bool] = None
    bpm_detected: Optional[float] = None
    key_detected: Optional[str] = None
    key_confidence: Optional[float] = None
    bpm_mismatch: Optional[bool] = None
    key_mismatch: Optional[bool] = None
    loudness_lufs: Optional[float] = None
    loudness_range: Optional[float] = None
    true_peak_dbtp: Optional[float] = None
    cue_in_s: Optional[float] = None
    cue_out_s: Optional[float] = None
    waveform_peaks_count: Optional[int] = None
    fingerprint: Optional[str] = None
    fingerprint_algo: Optional[str] = None
    fingerprint_sha256: Optional[str] = None
    pcm_sha256: Optional[str] = None
    spectral_cutoff_hz: Optional[int] = None
    quality_flags: Optional[Dict[str, Any]] = None


class WaveformOut(BaseModel):
    """
    The waveform artifact (MOO-87 D6) plus the song id: exactly what the
    frontend feeds into peaksToBars. peaks are 0..1 floats, count entries.
    """

    song_id: int
    version: int
    algorithm: Optional[str] = None
    count: int
    duration_seconds: Optional[float] = None
    peaks: List[float]


class BackfillRequest(BaseModel):
    """
    POST /admin/analysis/backfill body: force re-analysis and/or restrict
    the run to specific analyzer fields (per-field versioning, D3).
    """

    force: bool = False
    fields: Optional[List[str]] = None

    @validator("fields")
    def _known_fields(cls, value):  # noqa: N805 - pydantic validator
        if value is None:
            return value
        unknown = sorted(set(value) - set(ANALYSIS_FIELDS))
        if unknown:
            raise ValueError(
                "unknown analysis fields: {} (known: {})".format(
                    ", ".join(unknown), ", ".join(ANALYSIS_FIELDS)
                )
            )
        return value


class AnalysisStatsOut(BaseModel):
    """GET /admin/analysis/stats: queue depth + throughput (feeds MOO-83)."""

    tracks_total: int
    analyzed: int
    pending: int
    running: int
    failed: int
    waveforms: int
    fingerprints: int
    heavy_jobs_queued: int
    heavy_jobs_running: int
    succeeded_last_hour: int
    throughput_per_min: float
    analyzer_version: int
