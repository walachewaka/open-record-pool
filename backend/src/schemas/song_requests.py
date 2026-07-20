"""
API schemas for the song request system (MOO-81).
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, validator

from src.utils.camelot import to_camelot

KINDS = ("free_text", "url")
STATUSES = (
    "pending",
    "approved",
    "downloading",
    "fulfilled",
    "failed",
    "rejected",
    "duplicate",
    "cancelled",
)


class RequestSongMini(BaseModel):
    id: int
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    musical_key: Optional[str] = None
    camelot_key: Optional[str] = None
    bpm: Optional[float] = None


def song_mini(song):
    """A compact RequestSongMini from a Songs row, or None."""
    if song is None:
        return None
    return RequestSongMini(
        id=song.id,
        title=song.title,
        artist=song.artist,
        album=song.album,
        musical_key=song.musical_key,
        camelot_key=to_camelot(song.musical_key),
        bpm=song.bpm,
    )


def _blank_to_none(value):
    if value is None:
        return None
    value = value.strip()
    return value or None


class RequestCreateSchema(BaseModel):
    kind: str
    artist: Optional[str] = Field(None, max_length=255)
    title: Optional[str] = Field(None, max_length=255)
    mix_name: Optional[str] = Field(None, max_length=120)
    source_url: Optional[str] = Field(None, max_length=2048)
    notes: Optional[str] = Field(None, max_length=500)

    @validator("kind")
    def _known_kind(cls, value):  # noqa: N805 - pydantic validator
        if value not in KINDS:
            raise ValueError("kind must be one of: {}".format(", ".join(KINDS)))
        return value

    @validator("artist", "title", "mix_name", "notes", "source_url")
    def _trim(cls, value):  # noqa: N805 - pydantic validator
        return _blank_to_none(value)

    @validator("title", always=True)
    def _free_text_requires_artist_and_title(cls, value, values):  # noqa: N805
        if values.get("kind") == "free_text":
            if not values.get("artist") or not value:
                raise ValueError("Free-text requests need both an artist and a title")
        return value

    @validator("source_url", always=True)
    def _url_kind_requires_source_url(cls, value, values):  # noqa: N805
        if values.get("kind") == "url" and not value:
            raise ValueError("URL requests need a source_url")
        return value


class RequestOut(BaseModel):
    id: int
    kind: str
    artist: Optional[str] = None
    title: Optional[str] = None
    mix_name: Optional[str] = None
    source_url: Optional[str] = None
    provider: Optional[str] = None
    notes: Optional[str] = None
    status: str
    reason: Optional[str] = None
    duplicate_of: Optional[RequestSongMini] = None
    possible_duplicate_of: Optional[RequestSongMini] = None
    fulfilled_song: Optional[RequestSongMini] = None
    download_id: Optional[int] = None
    resolved_seen: bool
    created_at: datetime
    decided_at: Optional[datetime] = None


class AdminRequestOut(RequestOut):
    requester_id: int
    requester_username: Optional[str] = None
    decided_by_username: Optional[str] = None


class RequestListResponse(BaseModel):
    items: List[RequestOut]
    next_cursor: Optional[str] = None


class AdminRequestListResponse(BaseModel):
    items: List[AdminRequestOut]
    next_cursor: Optional[str] = None


class RequestSummaryOut(BaseModel):
    open: int
    unseen_resolved: int


class MarkSeenOut(BaseModel):
    updated: int


class RequestStatsOut(BaseModel):
    pending: int


class RejectSchema(BaseModel):
    reason: Optional[str] = Field(None, max_length=500)

    @validator("reason")
    def _trim(cls, value):  # noqa: N805 - pydantic validator
        return _blank_to_none(value)


class ApproveSchema(BaseModel):
    # Free-text requests carry no provider URL; MOO-78's engine only fetches
    # from a URL (no query-search entry point), so the moderator supplies one
    # at approval time. Ignored for kind="url" requests (they already have
    # their own source_url).
    source_url: Optional[str] = Field(None, max_length=2048)

    @validator("source_url")
    def _trim(cls, value):  # noqa: N805 - pydantic validator
        return _blank_to_none(value)


class BulkActionSchema(BaseModel):
    ids: List[int] = Field(..., min_items=1, max_items=100)
    action: str
    reason: Optional[str] = Field(None, max_length=500)

    @validator("action")
    def _known_action(cls, value):  # noqa: N805 - pydantic validator
        if value not in ("approve", "reject"):
            raise ValueError('action must be "approve" or "reject"')
        return value

    @validator("reason")
    def _trim(cls, value):  # noqa: N805 - pydantic validator
        return _blank_to_none(value)


class BulkResultOut(BaseModel):
    updated: int
    skipped: List[int]
