"""
API schemas for crates (playlists) (MOO-65, extended MOO-84).
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, validator

from src.export.naming import FORMATS
from src.schemas.songs import SongOutSchema


def _valid_dj_target(value):
    """MOO-86: the crate's default target DJ software, or null for none."""
    if value is not None and value not in FORMATS:
        raise ValueError("dj_target must be one of: {}".format(", ".join(FORMATS)))
    return value


class CrateInSchema(BaseModel):
    """
    Payload to create a crate.
    """

    name: str = Field(..., min_length=1, max_length=100)
    color: Optional[str] = Field(None, max_length=16)
    description: Optional[str] = Field(None, max_length=2000)
    dj_target: Optional[str] = None

    _check_dj_target = validator("dj_target", allow_reuse=True)(_valid_dj_target)


class CrateUpdateSchema(BaseModel):
    """
    Payload to update a crate: any subset of name, color, description,
    dj_target, and public. An explicit `null` for description or dj_target
    clears it.
    """

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    color: Optional[str] = Field(None, max_length=16)
    description: Optional[str] = Field(None, max_length=2000)
    dj_target: Optional[str] = None
    public: Optional[bool] = None

    _check_dj_target = validator("dj_target", allow_reuse=True)(_valid_dj_target)


class CrateTrackInSchema(BaseModel):
    """
    Payload to add one song to a crate.
    """

    song_id: int


class CrateReorderSchema(BaseModel):
    """
    Payload to reorder a crate: the full list of its song ids in the new
    order (a permutation of the current membership). Capped at 1000 tracks
    -- larger crates use the single-track move endpoint instead.
    """

    song_ids: List[int]


class CrateTrackMoveSchema(BaseModel):
    """
    Payload to move one track: place it immediately after [after_song_id],
    or at the very top when null.
    """

    after_song_id: Optional[int] = None


class CrateTrackMoveOutSchema(BaseModel):
    song_id: int
    position: int


class CrateDuplicateInSchema(BaseModel):
    """
    Payload for "duplicate to my crates". Defaults to "Copy of <name>".
    """

    name: Optional[str] = Field(None, min_length=1, max_length=100)


class CrateSummarySchema(BaseModel):
    """
    A crate as listed in the sidebar. share_token is only exposed to the
    crate's owner.
    """

    id: int
    name: str
    color: Optional[str] = None
    description: Optional[str] = None
    cover_url: Optional[str] = None
    public: bool
    share_token: Optional[str] = None
    dj_target: Optional[str] = None
    track_count: int
    created_at: datetime


class CrateTrackOutSchema(BaseModel):
    """
    One ordered track of a crate.
    """

    position: int
    song: SongOutSchema


class CrateTracksPageSchema(BaseModel):
    """
    One keyset page of a crate's ordered tracks.
    """

    items: List[CrateTrackOutSchema]
    next_cursor: Optional[str] = None


class CrateDetailSchema(CrateSummarySchema):
    """
    A crate with the first page of its ordered tracks (<=200; walk further
    pages via GET /crates/{id}/tracks).
    """

    owner_id: int
    owner_username: str
    total_duration_seconds: float
    tracks: List[CrateTrackOutSchema]
    tracks_next_cursor: Optional[str] = None


class PublicCrateItemSchema(BaseModel):
    """
    One row of the public crate discovery listing. Never carries share_token.
    """

    id: int
    name: str
    color: Optional[str] = None
    description: Optional[str] = None
    cover_url: Optional[str] = None
    owner_id: int
    owner_username: str
    track_count: int
    created_at: datetime


class PublicCratesResponseSchema(BaseModel):
    items: List[PublicCrateItemSchema]
    next_cursor: Optional[str] = None
