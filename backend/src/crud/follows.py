"""
CRUD + business logic for artist follows / release tracking (MOO-80):
materializing artists from the library, the per-tick poll algorithm (D4),
release <-> library matching (D5), and grab/auto-grab (D6).

D6 adaptation note: the plan assumed a query-based `enqueue_download`. The
shipped MOO-78 engine only ever takes a resolved provider URL (confirmed by
reading src/downloads/service.py -- validate_provider_url is mandatory) and
has no search-by-query entry point; src/crud/song_requests.py's own
docstring says exactly this ("MOO-78 has no query-search entry point ...
free-text requests cannot be auto-fulfilled from an artist/title alone").
So here "grab" and "auto-grab" create a free-text SongRequests row (the
issue's own stated alternative -- "auto-create a song request") rather than
an instant download; a moderator supplies a source_url to fulfill it, same
as any other free-text request.
"""
import asyncio
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException
from tortoise.expressions import Q
from tortoise.functions import Count

from src.database.models import ArtistFollows, Artists, Releases, Songs
from src.security import audit
from src.services.dedup import check_library
from src.utils.normalize import normalize_artist

_RESOLVE_RETRY_DAYS = 7


def normalize_name(name):
    return normalize_artist(name)


def _utcnow():
    return datetime.now(timezone.utc)


def _env_int(name, default):
    import os

    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name, default):
    import os

    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _track_to_dict(track):
    return {
        "title": track.title,
        "mix": track.mix,
        "external_id": track.external_id,
        "duration_seconds": track.duration_seconds,
    }


def serialize_release(release, artist_id, artist_name):
    """A plain dict matching ReleaseOut -- callers pass the artist id/name
    explicitly since `release.artist` requires a prefetch (or a lazy await)
    the caller already controls."""
    return {
        "id": release.id,
        "artist": {"id": artist_id, "name": artist_name},
        "source": release.source,
        "external_id": release.external_id,
        "title": release.title,
        "release_date": release.release_date,
        "label": release.label,
        "artwork_url": release.artwork_url,
        "source_url": release.source_url,
        "track_count": release.track_count,
        "tracks": release.tracks or [],
        "status": release.status,
        "matched_count": release.matched_count,
        "matched_song_ids": release.matched_song_ids or [],
        "first_seen_at": release.first_seen_at,
    }


# --- D-materialize artists from the library --------------------------------


async def sync_artists_impl():
    """Upserts one artists row per distinct normalized library artist name
    (published tracks only), refreshing track_count. Never renames an
    already-known artist's display name from a later-seen spelling variant."""
    rows = (
        await Songs.filter(status="published")
        .exclude(artist__isnull=True)
        .exclude(artist="")
        .annotate(cnt=Count("id"))
        .group_by("artist")
        .values("artist", "cnt")
    )
    grouped = {}
    for row in rows:
        norm = normalize_name(row["artist"])
        if not norm:
            continue
        bucket = grouped.setdefault(norm, {"name": row["artist"], "track_count": 0})
        bucket["track_count"] += int(row["cnt"])

    artists_seen = 0
    for norm, data in grouped.items():
        artist, created = await Artists.get_or_create(
            name_norm=norm,
            defaults={"name": data["name"], "track_count": data["track_count"]},
        )
        if not created and artist.track_count != data["track_count"]:
            artist.track_count = data["track_count"]
            await artist.save(update_fields=["track_count", "modified_at"])
        artists_seen += 1
    return {"artists_seen": artists_seen}


# --- D5 release <-> library matching ---------------------------------------


async def _match_tracks(tracks, artist_name):
    results = []
    for track in tracks:
        result = await check_library(
            artist=artist_name,
            title=track.get("title"),
            mix=track.get("mix"),
            duration_seconds=track.get("duration_seconds"),
        )
        results.append(result)
    return results


async def match_release(release, artist_name):
    """Re-runs library matching for [release] and persists matched_song_ids/
    matched_count/status. Sticky states: `ignored` is never overwritten;
    `grabbed` only flips to `in_library` on a later full match. Returns
    (release, per_track_results) so callers can find unmatched tracks."""
    tracks = release.tracks or []
    results = await _match_tracks(tracks, artist_name)
    matched_ids = [r["canonical_song_id"] for r in results if r.get("found")]
    full_match = bool(tracks) and len(matched_ids) == len(tracks)

    release.matched_song_ids = matched_ids
    release.matched_count = len(matched_ids)
    if release.status == "ignored":
        pass
    elif release.status == "grabbed":
        if full_match:
            release.status = "in_library"
    else:
        release.status = "in_library" if full_match else "missing"
    await release.save(
        update_fields=["matched_song_ids", "matched_count", "status", "modified_at"]
    )
    return release, results


async def ensure_follower_or_403(release, user):
    is_follower = await ArtistFollows.filter(
        user_id=user.id, artist_id=release.artist_id
    ).exists()
    if not is_follower:
        raise HTTPException(status_code=403, detail="Not allowed.")


# --- D6 grab / auto-grab (adapted to SongRequests, see module docstring) --


async def _create_song_request(user, artist_name, track, notes, request=None):
    """Best-effort: creates one free-text song request for an unmatched
    release track. Swallows the request system's own policy rejections
    (disabled, quota, rate limit, already-open) -- a grab that can't be
    submitted right now must never break the poll tick or the API call."""
    import src.crud.song_requests as song_requests_crud
    from src.schemas.song_requests import RequestCreateSchema

    payload = RequestCreateSchema(
        kind="free_text",
        artist=artist_name[:255],
        title=(track.get("title") or "")[:255],
        mix_name=(track.get("mix") or None),
        notes=notes[:500] if notes else None,
    )
    try:
        req = await song_requests_crud.create_request(user, payload, request=request)
        return req.id
    except HTTPException:
        return None


async def grab_release(release, artist, user, request=None):
    """Manual grab (POST /releases/{id}/grab): creates a song request for
    every currently-unmatched track. Returns (release, created_request_ids)."""
    release, results = await match_release(release, artist.name)
    unmatched = [t for t, r in zip(release.tracks or [], results) if not r.get("found")]
    created_ids = []
    for track in unmatched:
        req_id = await _create_song_request(
            user,
            artist.name,
            track,
            notes="Requested via Release Radar: {}".format(release.title),
            request=request,
        )
        if req_id is not None:
            created_ids.append(req_id)
    if created_ids:
        release.grab_request_ids = list(release.grab_request_ids or []) + created_ids
        release.status = "grabbed"
        await release.save(update_fields=["grab_request_ids", "status", "modified_at"])
        await audit.audit_event(
            "release.grabbed",
            request=request,
            actor=user,
            target_type="release",
            target_id=release.id,
            detail={"request_ids": created_ids},
        )
    return release, created_ids


async def ignore_release(release, user, request=None):
    release.status = "ignored"
    release.ignored_by_id = user.id
    release.ignored_at = _utcnow()
    await release.save(
        update_fields=["status", "ignored_by_id", "ignored_at", "modified_at"]
    )
    await audit.audit_event(
        "release.ignored",
        request=request,
        actor=user,
        target_type="release",
        target_id=release.id,
    )
    return release


async def unignore_release(release, artist, request=None, actor=None):
    release.ignored_by_id = None
    release.ignored_at = None
    release.status = (
        "missing"  # placeholder so match_release's sticky rule doesn't no-op
    )
    await release.save(
        update_fields=["ignored_by_id", "ignored_at", "status", "modified_at"]
    )
    release, _results = await match_release(release, artist.name)
    await audit.audit_event(
        "release.unignored",
        request=request,
        actor=actor,
        target_type="release",
        target_id=release.id,
    )
    return release


async def _maybe_auto_grab(release, artist, unmatched_tracks):
    """D6: when a NEW release lands `missing` and at least one follower has
    auto_grab on, create a song request per unmatched track, attributed to
    the first such follower (SongRequests always needs a real requester)."""
    if not unmatched_tracks:
        return 0
    candidates = await ArtistFollows.filter(artist_id=artist.id).prefetch_related(
        "user"
    )
    follow = next(
        (f for f in candidates if bool((f.settings or {}).get("auto_grab"))), None
    )
    if follow is None:
        return 0
    created_ids = []
    for track in unmatched_tracks:
        req_id = await _create_song_request(
            follow.user,
            artist.name,
            track,
            notes="Auto-grabbed from a followed release: {}".format(release.title),
        )
        if req_id is not None:
            created_ids.append(req_id)
    if created_ids:
        release.grab_request_ids = list(release.grab_request_ids or []) + created_ids
        release.status = "grabbed"
        await release.save(update_fields=["grab_request_ids", "status", "modified_at"])
        await audit.audit_event(
            "release.auto_grabbed",
            actor=follow.user,
            target_type="release",
            target_id=release.id,
            detail={"request_ids": created_ids},
        )
    return len(created_ids)


# --- D4 poll tick ------------------------------------------------------------


async def poll_impl():
    from src.sources.registry import get_release_sources

    sources = get_release_sources()
    if not sources:
        return {"skipped": "no release source configured"}
    source = sources[0]

    totals = {
        "artists_resolved": 0,
        "artists_polled": 0,
        "releases_new": 0,
        "releases_matched": 0,
        "grabs_created": 0,
    }

    followed_ids = sorted(
        {row for row in await ArtistFollows.all().values_list("artist_id", flat=True)}
    )
    if not followed_ids:
        return totals

    now = _utcnow()

    # 1) Resolution pass: up to 10 followed artists with no beatport id yet.
    resolve_cutoff = now - timedelta(days=_RESOLVE_RETRY_DAYS)
    unresolved = (
        await Artists.filter(id__in=followed_ids, beatport_artist_id__isnull=True)
        .filter(
            Q(resolve_attempted_at__isnull=True)
            | Q(resolve_attempted_at__lt=resolve_cutoff)
        )
        .limit(10)
    )
    for artist in unresolved:
        candidates = await source.search_artists(artist.name)
        match = next(
            (c for c in candidates if normalize_name(c.name) == artist.name_norm), None
        )
        if match is not None:
            artist.beatport_artist_id = match.external_id
        artist.resolve_attempted_at = now
        await artist.save(update_fields=["beatport_artist_id", "resolve_attempted_at"])
        totals["artists_resolved"] += 1

    # 2) Due set: followed + resolved, ordered last_polled_at ASC NULLS FIRST,
    # with adaptive backoff for inactive artists.
    interval_minutes = _env_int("RELEASE_POLL_INTERVAL_MINUTES", 360)
    backoff_multiplier = _env_int("RELEASE_BACKOFF_MULTIPLIER", 4)
    stale_days = _env_int("RELEASE_BACKOFF_STALE_DAYS", 180)
    batch_size = _env_int("RELEASE_POLL_BATCH", 25)
    lookback_days = _env_int("RELEASE_LOOKBACK_DAYS", 120)
    poll_delay = _env_float("RELEASE_POLL_DELAY_SECONDS", 1.0)

    interval = timedelta(minutes=interval_minutes)
    resolved_artists = await Artists.filter(
        id__in=followed_ids, beatport_artist_id__isnull=False
    )
    due = []
    for artist in resolved_artists:
        if artist.last_polled_at is None:
            due.append(artist)
            continue
        effective_interval = interval
        if artist.last_release_seen_at is None or artist.last_release_seen_at < (
            now - timedelta(days=stale_days)
        ):
            effective_interval = interval * backoff_multiplier
        if artist.last_polled_at < now - effective_interval:
            due.append(artist)
    due.sort(key=lambda a: (a.last_polled_at is not None, a.last_polled_at or now))
    due = due[:batch_size]

    since = date.today() - timedelta(days=lookback_days)
    for artist in due:
        found_new = False
        external_releases = await source.get_artist_releases(
            artist.beatport_artist_id, since=since, artist_name=artist.name
        )
        for ext in external_releases:
            defaults = {
                "artist_id": artist.id,
                "title": ext.title,
                "release_date": ext.release_date,
                "label": ext.label,
                "artwork_url": ext.artwork_url,
                "source_url": ext.source_url,
                "track_count": len(ext.tracks),
                "tracks": [_track_to_dict(t) for t in ext.tracks],
            }
            row, created = await Releases.get_or_create(
                source=source.name, external_id=ext.external_id, defaults=defaults
            )
            if not created:
                for field, value in defaults.items():
                    if field != "artist_id":
                        setattr(row, field, value)
                await row.save(
                    update_fields=[
                        "title",
                        "release_date",
                        "label",
                        "artwork_url",
                        "source_url",
                        "track_count",
                        "tracks",
                        "modified_at",
                    ]
                )
            row, results = await match_release(row, artist.name)
            if created:
                totals["releases_new"] += 1
                found_new = True
                if row.status == "missing":
                    unmatched = [
                        t for t, r in zip(ext.tracks, results) if not r.get("found")
                    ]
                    grabbed = await _maybe_auto_grab(
                        row, artist, [_track_to_dict(t) for t in unmatched]
                    )
                    totals["grabs_created"] += grabbed
            if row.status == "in_library":
                totals["releases_matched"] += 1

        # Re-match sweep: this artist's still-missing past-due releases that
        # this poll's search didn't happen to return (D5).
        stale_missing = await Releases.filter(
            artist_id=artist.id, status="missing", release_date__lte=date.today()
        )
        for row in stale_missing:
            await match_release(row, artist.name)

        artist.last_polled_at = now
        if found_new:
            artist.last_release_seen_at = now
        await artist.save(update_fields=["last_polled_at", "last_release_seen_at"])
        totals["artists_polled"] += 1
        if poll_delay:
            await asyncio.sleep(poll_delay)

    return totals


# --- feed / badge ------------------------------------------------------------


async def unseen_count(user_id):
    from src.database.models import FollowFeedState

    state = await FollowFeedState.get_or_none(user_id=user_id)
    follows = await ArtistFollows.filter(user_id=user_id)
    artist_ids = [
        f.artist_id
        for f in follows
        if (f.settings or {}).get("notify", True) is not False
    ]
    if not artist_ids:
        return 0
    query = Releases.filter(artist_id__in=artist_ids)
    if state is not None:
        query = query.filter(first_seen_at__gt=state.seen_at)
    else:
        oldest_follow = (
            await ArtistFollows.filter(user_id=user_id).order_by("created_at").first()
        )
        if oldest_follow is None:
            return 0
        query = query.filter(first_seen_at__gt=oldest_follow.created_at)
    return await query.count()


async def mark_feed_seen(user_id):
    from src.database.models import FollowFeedState

    await FollowFeedState.update_or_create(
        user_id=user_id, defaults={"seen_at": _utcnow()}
    )
