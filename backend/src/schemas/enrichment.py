"""
API schemas for Beatport metadata enrichment (MOO-85). EnrichmentOut is the
GET /admin/enrichment/songs/{song_id} contract MOO-82's ID3 editor consumes
for its suggested-values panel and artwork candidates -- keep this shape
stable across changes.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, constr


class EnrichmentSongOut(BaseModel):
    """The embedded song summary on an enrichment row."""

    id: int
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    genre: Optional[str] = None
    label: Optional[str] = None
    year: Optional[int] = None
    bpm: Optional[float] = None
    musical_key: Optional[str] = None
    duration_seconds: Optional[float] = None
    field_locks: Optional[Dict[str, str]] = None


class EnrichmentOut(BaseModel):
    id: int
    song_id: int
    provider: str
    status: str
    match_method: Optional[str] = None
    confidence: Optional[float] = None
    beatport_track_id: Optional[int] = None
    beatport_release_id: Optional[int] = None
    beatport_artist_ids: Optional[List[int]] = None
    payload: Optional[Dict[str, Any]] = None
    candidates: Optional[List[Dict[str, Any]]] = None
    fields_applied: Optional[List[str]] = None
    tag_snapshot: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    reviewed_by_id: Optional[int] = None
    matched_at: Optional[datetime] = None
    applied_at: Optional[datetime] = None
    created_at: datetime
    modified_at: datetime
    song: Optional[EnrichmentSongOut] = None


class EnrichmentListResponse(BaseModel):
    """One keyset-paginated page of the review queue (id DESC)."""

    items: List[EnrichmentOut]
    next_cursor: Optional[str] = None


class ProviderStatusOut(BaseModel):
    """GET /admin/enrichment/status -- never triggers a Beatport call."""

    provider: str
    enabled: bool
    mode: str  # "mock" | "live" | "disabled"
    reason: Optional[str] = None  # "credentials_not_configured" | "disabled_by_env"
    auto_enrich_on_import: bool
    rate_limit_rps: float
    cache_entries: int
    counts: Dict[str, int]


class EnrichTriggerIn(BaseModel):
    force: bool = False


class BackfillTriggerIn(BaseModel):
    cursor: Optional[int] = None
    force: bool = False
    statuses: Optional[List[str]] = None


class AcceptIn(BaseModel):
    """Accept a match: default is the top-scored stored candidate and all
    three auto-writable fields."""

    beatport_track_id: Optional[int] = None
    fields: Optional[List[str]] = None


class ManualSearchIn(BaseModel):
    query: constr(min_length=2, max_length=200)
