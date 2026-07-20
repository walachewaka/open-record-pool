"""
Admin download oversight (MOO-78): all users' fetch requests, keyset paginated,
with status/provider/user filters. Cancel/retry reuse the member routes (an
admin passes the owner-or-approve_submissions object check there).
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query

from src.auth.permissions import require_permission
from src.crud import downloads as downloads_crud
from src.schemas.downloads import DownloadRequestList
from src.schemas.users import UserOutSchema

router = APIRouter(prefix="/admin/fetch", tags=["admin: downloads"])


@router.get("", response_model=DownloadRequestList)
async def list_all_requests(
    status: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
    user_id: Optional[int] = Query(None),
    cursor: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    current_user: UserOutSchema = Depends(require_permission("view_reports")),
) -> DownloadRequestList:
    """Every download request across all users, newest first."""
    items, next_cursor = await downloads_crud.list_all(
        status=status, provider=provider, user_id=user_id, cursor=cursor, limit=limit
    )
    return DownloadRequestList(items=items, next_cursor=next_cursor)
