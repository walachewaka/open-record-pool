"""
API schemas for the recording dedup surface (MOO-90): the library check the
download engine calls before fetching, the admin duplicates review queue,
and the per-recording version history.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class LibraryCheckIn(BaseModel):
    """POST /library/check body: at least one identity signal is required."""

    artist: Optional[str] = None
    title: Optional[str] = None
    mix: Optional[str] = None
    duration_seconds: Optional[float] = None
    isrc: Optional[str] = None
    musicbrainz_id: Optional[str] = None
    beatport_id: Optional[str] = None
    spotify_id: Optional[str] = None
    fingerprint_b64: Optional[str] = None
    source: Optional[str] = None
    declared_bitrate_kbps: Optional[int] = None
    format: Optional[str] = None


class SongVersionOut(BaseModel):
    """One version of a recording as the admin compare surfaces need it."""

    id: int
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    mix_norm: str = "original"
    duration_seconds: Optional[float] = None
    bitrate_kbps: Optional[int] = None
    effective_bitrate_kbps: Optional[int] = None
    format_class: Optional[int] = None
    sample_rate_hz: Optional[int] = None
    spectral_cutoff_hz: Optional[int] = None
    suspect_transcode: bool = False
    source: Optional[str] = None
    file_path: Optional[str] = None
    file_size_bytes: Optional[int] = None
    version_status: str = "canonical"
    quality_breakdown: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None


class LibraryCheckOut(BaseModel):
    """
    Whether the library already holds this recording, through which layer it
    matched, and whether the offered source would beat the canonical.
    """

    found: bool = False
    recording_id: Optional[int] = None
    canonical_song_id: Optional[int] = None
    canonical: Optional[SongVersionOut] = None
    match_layer: Optional[str] = None
    confidence: Optional[float] = None
    would_improve: Optional[bool] = None


class DuplicateCandidateOut(BaseModel):
    """One row of the admin duplicates queue."""

    id: int
    layer: str
    similarity: Optional[float] = None
    confidence: float
    duration_delta: Optional[float] = None
    status: str
    suggested_winner_id: Optional[int] = None
    recording_id: Optional[int] = None
    created_at: datetime
    song_a: SongVersionOut
    song_b: SongVersionOut


class DuplicateCandidateDetailOut(DuplicateCandidateOut):
    """The drawer payload: the list row plus the resolution record."""

    resolution: Optional[Dict[str, Any]] = None
    resolved_by_id: Optional[int] = None
    resolved_at: Optional[datetime] = None


class DuplicateListResponse(BaseModel):
    items: List[DuplicateCandidateOut]
    next_cursor: Optional[str] = None


class ResolveIn(BaseModel):
    """Resolve one candidate: merge (keep winner) or not_duplicate."""

    action: str
    winner_song_id: Optional[int] = None


class BulkResolveIn(BaseModel):
    ids: List[int]
    action: str


class BulkResolveOut(BaseModel):
    resolved: int
    skipped: List[Dict[str, Any]] = []


class RelatedRecordingOut(BaseModel):
    recording_id: int
    kind: str
    similarity: Optional[float] = None
    title_norm: Optional[str] = None
    mix_norm: Optional[str] = None


class RecordingOut(BaseModel):
    """A recording with its full version history (admin surface)."""

    id: int
    artist_norm: str
    title_norm: str
    mix_norm: str
    duration_seconds: Optional[float] = None
    canonical_song_id: Optional[int] = None
    isrc: Optional[str] = None
    musicbrainz_id: Optional[str] = None
    beatport_id: Optional[str] = None
    spotify_id: Optional[str] = None
    versions: List[SongVersionOut] = []
    related: List[RelatedRecordingOut] = []


class PromoteIn(BaseModel):
    song_id: int


class BackfillIn(BaseModel):
    """POST /admin/duplicates/backfill body. Dry-run is the safe default."""

    dry_run: bool = True
