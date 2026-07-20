"""
Admin dashboard and reports routes (MOO-71). All require the view_reports
permission.
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query

import src.crud.reports as crud
from src.auth.permissions import require_permission

router = APIRouter(prefix="/admin/stats", tags=["admin: reports"])

_reports = Depends(require_permission("view_reports"))


@router.get("/dashboard", response_model=Dict[str, Any], dependencies=[_reports])
async def dashboard() -> Dict[str, Any]:
    """The dashboard stat cards, 14-day series, top genres/tracks, and health."""
    return await crud.dashboard()


@router.get("/reports", response_model=Dict[str, Any], dependencies=[_reports])
async def reports(
    start: Optional[str] = Query(None, description="Range start, YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="Range end (inclusive), YYYY-MM-DD"),
    limit: int = Query(10, ge=1, le=50),
) -> Dict[str, Any]:
    """Date-range reports: totals, downloads over time, top tracks/genres, formats."""
    start_dt = crud.parse_date(start, None)
    end_dt = crud.parse_date(end, None)
    return await crud.reports(start_dt, end_dt, limit=limit)
