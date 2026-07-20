"""
API schemas for the member library features: favorites, play events,
download history/quota, and charts (MOO-65).
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from src.schemas.songs import SongOutSchema


class FavoriteToggleResponse(BaseModel):
    """
    The state of a song's favorite flag after a toggle.
    """

    song_id: int
    is_favorite: bool


class PlayEventResponse(BaseModel):
    """
    Acknowledgement of a logged play event, with the song's new play count.
    """

    song_id: int
    play_count: int


class DownloadOutSchema(BaseModel):
    """
    One entry of the user's download history.
    """

    id: int
    format: str
    counted_against_quota: bool
    downloaded_at: datetime
    song: SongOutSchema


class DownloadListResponse(BaseModel):
    """
    One page of the user's download history, newest first.
    """

    items: List[DownloadOutSchema]
    total: int
    page: int
    page_size: int


class QuotaResponse(BaseModel):
    """
    The user's monthly download quota. limit <= 0 means unlimited, in which
    case remaining is null. Re-downloads never count against the quota.
    """

    limit: int
    used: int
    remaining: Optional[int] = None
    unlimited: bool
    month: str


class ChartEntry(BaseModel):
    """
    One ranked row of a chart. The metric depends on the mode: download
    count, play count, or days since the song was added.
    """

    rank: int
    metric: int
    song: SongOutSchema


class ChartsResponse(BaseModel):
    """
    A chart: Most downloaded / Most played / Added this month.
    """

    mode: str
    entries: List[ChartEntry]
