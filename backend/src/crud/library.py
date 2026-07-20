"""
CRUD helpers for favorites, play events, and the download history/quota
(MOO-65).
"""
import os
from datetime import datetime, timezone

from src.database.models import Downloads, Favorites

QUOTA_DEFAULT = 100


def monthly_quota():
    """
    The configured monthly download quota. Values <= 0 mean unlimited.
    """
    raw = os.environ.get("DOWNLOAD_QUOTA_MONTHLY", "")
    try:
        return int(raw)
    except ValueError:
        return QUOTA_DEFAULT


def current_month_start():
    """
    The first instant of the current month, in UTC.
    """
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, 1, tzinfo=timezone.utc)


async def quota_used(user_id):
    """
    How many quota-counted downloads the user made this month.
    """
    return await Downloads.filter(
        user_id=user_id,
        counted_against_quota=True,
        downloaded_at__gte=current_month_start(),
    ).count()


async def quota_status(user_id):
    """
    The user's quota as a dict matching QuotaResponse.
    """
    limit = monthly_quota()
    used = await quota_used(user_id)
    unlimited = limit <= 0
    return {
        "limit": limit,
        "used": used,
        "remaining": None if unlimited else max(limit - used, 0),
        "unlimited": unlimited,
        "month": current_month_start().strftime("%Y-%m"),
    }


async def favorite_song_ids(user_id, song_ids):
    """
    The subset of [song_ids] the user has favorited, as a set.
    """
    if not song_ids:
        return set()
    return set(
        await Favorites.filter(user_id=user_id, song_id__in=list(song_ids)).values_list(
            "song_id", flat=True
        )
    )
