"""
API schemas for artist follows / release tracking (MOO-80).
"""
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

STATUSES = ("missing", "in_library", "grabbed", "ignored")


class FollowSettingsIn(BaseModel):
    auto_grab: bool = False
    notify: bool = True

    class Config:
        extra = "forbid"


class FollowSettingsPatchIn(BaseModel):
    auto_grab: Optional[bool] = None
    notify: Optional[bool] = None

    class Config:
        extra = "forbid"


class FollowOut(BaseModel):
    artist_id: int
    followed: bool
    settings: Optional[Dict[str, Any]] = None


class ArtistOut(BaseModel):
    id: int
    name: str
    track_count: int
    beatport_artist_id: Optional[str] = None
    image_url: Optional[str] = None
    is_followed: bool = False
    follow_settings: Optional[Dict[str, Any]] = None
    latest_release_date: Optional[date] = None


class ArtistListResponse(BaseModel):
    items: List[ArtistOut]
    next_cursor: Optional[str] = None


class ExternalArtistOut(BaseModel):
    source: str
    external_id: str
    name: str
    image_url: Optional[str] = None
    artist_id: Optional[int] = None


class ArtistSearchResponse(BaseModel):
    local: List[ArtistOut]
    external: List[ExternalArtistOut]
    sources_configured: bool


class ArtistMiniOut(BaseModel):
    id: int
    name: str


class ReleaseTrackOut(BaseModel):
    title: Optional[str] = None
    mix: Optional[str] = None
    external_id: Optional[str] = None
    duration_seconds: Optional[float] = None


class ReleaseOut(BaseModel):
    id: int
    artist: ArtistMiniOut
    source: str
    external_id: str
    title: str
    release_date: date
    label: Optional[str] = None
    artwork_url: Optional[str] = None
    source_url: Optional[str] = None
    track_count: int
    tracks: List[ReleaseTrackOut]
    status: str
    matched_count: int
    matched_song_ids: List[int]
    first_seen_at: datetime


class ArtistDetailOut(ArtistOut):
    releases: List[ReleaseOut]


class ReleaseListResponse(BaseModel):
    items: List[ReleaseOut]
    next_cursor: Optional[str] = None


class CalendarDayOut(BaseModel):
    date: date
    releases: List[ReleaseOut]


class CalendarResponse(BaseModel):
    month: str
    days: List[CalendarDayOut]
    truncated: bool


class GrabResponseOut(BaseModel):
    release: ReleaseOut
    request_ids: List[int]


class FeedStateOut(BaseModel):
    unseen_count: int


class AdminFollowsOverviewOut(BaseModel):
    followed_artists: int
    resolved_artists: int
    releases_total: int
    releases_by_status: Dict[str, int]
    last_poll_at: Optional[datetime] = None
    sources_configured: List[str]
