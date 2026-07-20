"""
API schemas for the music download engine (MOO-78).
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class FetchSubmitIn(BaseModel):
    url: str


class DownloadRequestOut(BaseModel):
    id: int
    provider: str
    url: str
    external_id: Optional[str] = None
    status: str
    origin: str
    origin_ref: Optional[str] = None
    priority: str
    progress: float
    attempts: int
    error: Optional[str] = None
    error_kind: Optional[str] = None
    requested_by_id: Optional[int] = None
    requested_by_username: Optional[str] = None
    job_id: Optional[int] = None
    song_id: Optional[int] = None
    # Included on detail routes; omitted (null) in list items to keep pages light.
    source_metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class DownloadRequestList(BaseModel):
    items: List[DownloadRequestOut]
    next_cursor: Optional[str] = None


class ProvidersOut(BaseModel):
    enabled: bool
    providers: Dict[str, bool]
    daily_limit: int
    used_today: int
    tool_versions: Dict[str, Optional[str]]
