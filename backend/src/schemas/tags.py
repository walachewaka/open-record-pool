"""
API schemas for the metadata editor (MOO-82): edit history, batch edits,
album-art candidates, enrichment suggestions, and member edit proposals.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from src.schemas.admin import ContentMetadataUpdateSchema

# The fields a batch edit may set: the ones that describe a RELEASE, not a
# single track. Setting one title (or track number) on 200 tracks is never what
# a multi-select means.
BATCH_FIELDS = (
    "artist",
    "album",
    "album_artist",
    "genre",
    "label",
    "year",
    "comment",
)


class RevisionSchema(BaseModel):
    id: int
    song_id: int
    editor_username: Optional[str] = None
    source: str
    changes: Dict[str, Any]
    batch_id: Optional[str] = None
    created_at: datetime


class RevisionListResponse(BaseModel):
    items: List[RevisionSchema]
    next_cursor: Optional[str] = None


class BatchEditSchema(BaseModel):
    """One partial field set applied to a multi-selection of tracks."""

    song_ids: List[int] = Field(..., min_items=1, max_items=1000)
    fields: ContentMetadataUpdateSchema


class BatchEditResponse(BaseModel):
    batch_id: str
    requested: int
    updated: int
    missing: int


class BatchRollbackResponse(BaseModel):
    batch_id: str
    undone: int
    skipped: List[int] = []


class ArtCandidateSchema(BaseModel):
    origin: str  # current | embedded | beatport
    url: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None


class ArtCandidateListResponse(BaseModel):
    items: List[ArtCandidateSchema]


class ArtSelectSchema(BaseModel):
    origin: str
    url: Optional[str] = None


class SuggestionSchema(BaseModel):
    field: str
    current: Optional[Any] = None
    suggested: Any
    locked: bool = False  # a manual edit already owns this field


class SuggestionListResponse(BaseModel):
    provider: str = "beatport"
    status: Optional[str] = None
    confidence: Optional[float] = None
    items: List[SuggestionSchema] = []


class ProposalCreateSchema(BaseModel):
    changes: ContentMetadataUpdateSchema
    note: Optional[str] = Field(None, max_length=500)


class ProposalSchema(BaseModel):
    id: int
    song_id: int
    song_title: Optional[str] = None
    song_artist: Optional[str] = None
    proposer_username: Optional[str] = None
    changes: Dict[str, Any]
    note: Optional[str] = None
    status: str
    created_at: datetime
    reviewed_at: Optional[datetime] = None


class ProposalListResponse(BaseModel):
    items: List[ProposalSchema]
    next_cursor: Optional[str] = None
