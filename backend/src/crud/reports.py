"""
Aggregates for the admin dashboard and reports (MOO-71).

Everything is computed live from the download history and the catalog. Ranges
are half-open [start, end) in UTC; the reports endpoint takes an explicit date
range, the dashboard uses fixed windows (today, last 14 days).
"""
import os
import shutil
from datetime import datetime, time, timedelta, timezone

from fastapi import HTTPException
from tortoise.functions import Count, Sum

import src.crud.settings as settings_crud
from src.database.models import Downloads, Songs, Users
from src.extract import musicfiles
from src.schemas.songs import song_to_schema


def _utc_now():
    return datetime.now(timezone.utc)


def _day_start(dt):
    return datetime.combine(dt.date(), time.min, tzinfo=timezone.utc)


def parse_date(value, default):
    """Parse a YYYY-MM-DD query param to a UTC midnight, or return default."""
    if not value:
        return default
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=422, detail="dates must be formatted as YYYY-MM-DD"
        )
    return parsed.replace(tzinfo=timezone.utc)


async def _per_song_counts(start, end):
    """[{song_id, count}] downloads grouped by song within [start, end)."""
    return (
        await Downloads.filter(downloaded_at__gte=start, downloaded_at__lt=end)
        .annotate(count=Count("id"))
        .group_by("song_id")
        .values("song_id", "count")
    )


async def _downloads_by_format(start, end):
    rows = (
        await Downloads.filter(downloaded_at__gte=start, downloaded_at__lt=end)
        .annotate(count=Count("id"))
        .group_by("format")
        .values("format", "count")
    )
    return [{"format": r["format"], "count": int(r["count"])} for r in rows]


async def _daily_series(start, end):
    """A per-day download count series covering every day in [start, end)."""
    stamps = await Downloads.filter(
        downloaded_at__gte=start, downloaded_at__lt=end
    ).values_list("downloaded_at", flat=True)
    buckets = {}
    for stamp in stamps:
        key = stamp.astimezone(timezone.utc).date().isoformat()
        buckets[key] = buckets.get(key, 0) + 1
    series = []
    day = start
    while day < end:
        key = day.date().isoformat()
        series.append({"date": key, "count": buckets.get(key, 0)})
        day += timedelta(days=1)
    return series


async def _top_tracks(start, end, limit):
    counts = await _per_song_counts(start, end)
    counts.sort(key=lambda r: (-int(r["count"]), r["song_id"]))
    top = counts[:limit]
    songs = {s.id: s for s in await Songs.filter(id__in=[r["song_id"] for r in top])}
    entries = []
    for rank, row in enumerate(top, start=1):
        song = songs.get(row["song_id"])
        if song is None:
            continue
        entries.append(
            {"rank": rank, "downloads": int(row["count"]), "song": song_to_schema(song)}
        )
    return entries


async def _top_genres(start, end, limit):
    """Top genres by downloads within the range."""
    counts = await _per_song_counts(start, end)
    genres = {
        s.id: s.genre
        for s in await Songs.filter(id__in=[r["song_id"] for r in counts]).only(
            "id", "genre"
        )
    }
    totals = {}
    for row in counts:
        genre = genres.get(row["song_id"])
        if not genre:
            continue
        totals[genre] = totals.get(genre, 0) + int(row["count"])
    ranked = sorted(totals.items(), key=lambda kv: (-kv[1], kv[0].lower()))
    return [{"genre": genre, "downloads": total} for genre, total in ranked[:limit]]


async def _storage():
    """Real disk usage of the media volume, plus the catalog's own footprint."""
    library_bytes = (
        await Songs.all()
        .annotate(total=Sum("file_size_bytes"))
        .values_list("total", flat=True)
    )
    library_bytes = int(library_bytes[0] or 0) if library_bytes else 0
    path = musicfiles.UPLOAD_PATH
    for candidate in (musicfiles.UPLOAD_PATH, musicfiles.MUSIC_PATH, os.getcwd()):
        if os.path.isdir(candidate):
            path = candidate
            break
    try:
        usage = shutil.disk_usage(path)
        total, used, free = usage.total, usage.used, usage.free
        percent = round(used / total * 100, 1) if total else 0.0
    except OSError:
        total = used = free = 0
        percent = 0.0
    return {
        "library_bytes": library_bytes,
        "disk_total_bytes": total,
        "disk_used_bytes": used,
        "disk_free_bytes": free,
        "percent_used": percent,
    }


async def _system_health():
    nas_readable = os.path.isdir(musicfiles.MUSIC_PATH) and os.access(
        musicfiles.MUSIC_PATH, os.R_OK
    )
    last_scan = await settings_crud.get_last_scan()
    duplicates = int(last_scan.get("duplicates_skipped", 0)) if last_scan else 0
    return {
        "search": await settings_crud.get_value("library", "search_status"),
        "nas_readable": bool(nas_readable),
        "duplicates": duplicates,
    }


async def dashboard():
    """The admin dashboard aggregates."""
    now = _utc_now()
    today_start = _day_start(now)
    tomorrow = today_start + timedelta(days=1)
    window_start = today_start - timedelta(days=13)  # 14-day inclusive window

    total_tracks = await Songs.all().count()
    published_tracks = await Songs.filter(status="published").count()
    active_members = await Users.filter(status="active").count()
    downloads_today = await Downloads.filter(
        downloaded_at__gte=today_start, downloaded_at__lt=tomorrow
    ).count()
    pending_count = await Songs.filter(status="pending").count()

    series = await _daily_series(window_start, tomorrow)
    total_window = sum(point["count"] for point in series)

    return {
        "total_tracks": total_tracks,
        "published_tracks": published_tracks,
        "active_members": active_members,
        "downloads_today": downloads_today,
        "storage": await _storage(),
        "downloads_14d": series,
        "top_genres": await _top_genres(window_start, tomorrow, 8),
        "top_tracks": await _top_tracks(window_start, tomorrow, 5),
        "downloads_by_format": await _downloads_by_format(window_start, tomorrow),
        "avg_per_member": round(total_window / active_members, 2)
        if active_members
        else 0.0,
        "needs_attention": {"pending": pending_count},
        "system_health": await _system_health(),
    }


async def reports(start, end, limit=10):
    """
    Range reports. [start, end] are inclusive calendar days; end is turned into
    an exclusive next-day bound internally.
    """
    now = _utc_now()
    start = start or (_day_start(now) - timedelta(days=13))
    end = end or _day_start(now)
    if end < start:
        raise HTTPException(status_code=422, detail="end must be on or after start")
    end_exclusive = end + timedelta(days=1)

    total_downloads = await Downloads.filter(
        downloaded_at__gte=start, downloaded_at__lt=end_exclusive
    ).count()
    active_members = await Users.filter(status="active").count()
    catalog = await Songs.all().count()

    return {
        "range": {"start": start.date().isoformat(), "end": end.date().isoformat()},
        "total_downloads": total_downloads,
        "active_members": active_members,
        "avg_per_member": round(total_downloads / active_members, 2)
        if active_members
        else 0.0,
        "catalog": catalog,
        "downloads_over_time": await _daily_series(start, end_exclusive),
        "top_tracks": await _top_tracks(start, end_exclusive, limit),
        "top_genres": await _top_genres(start, end_exclusive, limit),
        "downloads_by_format": await _downloads_by_format(start, end_exclusive),
    }
