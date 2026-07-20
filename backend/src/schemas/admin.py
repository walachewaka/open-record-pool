"""
API schemas for the admin console (MOO-71): roles/permissions, user
administration, content/moderation, settings, and reports.
"""
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, validator

from src.schemas.songs import SongOutSchema


# --- Roles & permissions matrix ---------------------------------------------


class PermissionMeta(BaseModel):
    key: str
    label: str


class RoleMatrixRole(BaseModel):
    key: str
    name: str
    description: str
    locked: bool
    permissions: Dict[str, bool]


class RoleMatrixResponse(BaseModel):
    permissions: List[PermissionMeta]
    roles: List[RoleMatrixRole]


class RoleUpdateSchema(BaseModel):
    """A new permission map for one role. Omitted keys keep the role default."""

    permissions: Dict[str, bool]


# --- Users administration ---------------------------------------------------


class AdminUserSchema(BaseModel):
    """One row of the admin users table."""

    id: int
    username: str
    full_name: Optional[str] = None
    email: Optional[str] = None
    role: str
    plan: str
    status: str
    downloads: int = 0
    joined: datetime


class AdminUserListResponse(BaseModel):
    items: List[AdminUserSchema]
    total: int
    page: int
    page_size: int


class AdminUserCreateSchema(BaseModel):
    """Invite/create a user from the admin surface."""

    username: str
    password: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None
    role: str = "member"
    plan: str = "free"
    status: str = "active"


class AdminUserUpdateSchema(BaseModel):
    """Change role/plan/status or profile fields of a user."""

    full_name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    plan: Optional[str] = None
    status: Optional[str] = None
    password: Optional[str] = None


# --- Content & moderation ---------------------------------------------------


class AdminSongSchema(SongOutSchema):
    """A song as seen by the admin content/moderation views: adds the internal
    fields hidden from members (status, source, uploader, download count)."""

    status: str = "published"
    source: str = "library"
    # Recording dedup (MOO-90): admins see every version; members only ever
    # see canonical ones, so these stay out of the member shape.
    version_status: str = "canonical"
    recording_id: Optional[int] = None
    uploaded_by_id: Optional[int] = None
    uploaded_by_username: Optional[str] = None
    download_count: int = 0
    # Beatport enrichment (MOO-85): field ownership map and the row's status
    # ("pending"/"applied"/"needs_review"/"no_match"/"rejected"/"error", or
    # null when no enrichment row exists yet) for the admin content table's
    # Beatport pill column.
    field_locks: Optional[Dict[str, str]] = None
    beatport_track_id: Optional[int] = None
    enrichment_status: Optional[str] = None
    # Custom ID3 frames (MOO-82): editable in the admin metadata editor, kept
    # out of the member song shape.
    txxx_frames: Optional[Dict[str, str]] = None


class AdminContentListResponse(BaseModel):
    items: List[AdminSongSchema]
    total: int
    page: int
    page_size: int


class ContentStatusUpdateSchema(BaseModel):
    status: str


class ContentMetadataUpdateSchema(BaseModel):
    """
    Editable song metadata: the full ID3 field set (MOO-82), including the
    custom TXXX frames. DB-side only -- the files on the read-only /music
    volume are never rewritten (writing tags back is MOO-75).

    Every field is optional; only the ones actually sent are changed
    (exclude_unset), and each one sent becomes "manual"-locked so the next
    /music rescan cannot clobber it.
    """

    title: Optional[str] = Field(None, max_length=255)
    artist: Optional[str] = Field(None, max_length=255)
    album: Optional[str] = Field(None, max_length=255)
    album_artist: Optional[str] = Field(None, max_length=255)
    composer: Optional[str] = Field(None, max_length=255)
    genre: Optional[str] = Field(None, max_length=100)
    label: Optional[str] = Field(None, max_length=255)
    comment: Optional[str] = Field(None, max_length=1000)
    isrc: Optional[str] = Field(None, max_length=15)
    year: Optional[int] = Field(None, ge=1000, le=2100)
    track_number: Optional[int] = Field(None, ge=0, le=9999)
    disc_number: Optional[int] = Field(None, ge=0, le=999)
    bpm: Optional[float] = Field(None, ge=20, le=999)
    musical_key: Optional[str] = Field(None, max_length=20)
    txxx_frames: Optional[Dict[str, str]] = None

    @validator("isrc")
    def _check_isrc(cls, value):
        if value and not re.match(r"^[A-Za-z]{2}[A-Za-z0-9]{3}[0-9]{7}$", value):
            raise ValueError("isrc must look like CCXXXYYNNNNN (e.g. GBAHS1700001)")
        return value.upper() if value else value

    @validator("txxx_frames")
    def _check_txxx(cls, value):
        # Same caps the extractor applies when it reads TXXX frames off a file
        # (src/extract/musicfiles.py), so a hand-edited frame set stays within
        # what a rescan would ever produce.
        if value is None:
            return value
        if len(value) > 32:
            raise ValueError("at most 32 custom tags")
        for desc, text in value.items():
            if not desc.strip() or len(desc) > 64:
                raise ValueError("custom tag names must be 1-64 characters")
            if len(text) > 512:
                raise ValueError("custom tag values must be at most 512 characters")
        return value


# --- Settings ---------------------------------------------------------------


class SettingsUpdateSchema(BaseModel):
    """A partial, grouped settings update, e.g. {"general": {"pool_name": ...}}."""

    __root__: Dict[str, Dict[str, Any]]
