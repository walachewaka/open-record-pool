"""
API schemas for background jobs (MOO-77).
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class JobOut(BaseModel):
    """
    The job envelope returned everywhere a job is exposed. For scan_library,
    result on success is exactly the old ExtractionResult shape.
    """

    id: int
    kind: str
    status: str
    queue: str
    progress: float
    payload: Dict[str, Any]
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_by_id: Optional[int] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    class Config:
        orm_mode = True


class JobListResponse(BaseModel):
    """One keyset-paginated page of jobs (id DESC)."""

    items: List[JobOut]
    next_cursor: Optional[str] = None
