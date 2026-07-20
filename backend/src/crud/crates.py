"""
CRUD operations for crates (playlists) (MOO-65, extended MOO-84: description,
cover, gap-based ordering, paginated contents, public discovery, duplicate).
"""
import secrets

from fastapi import HTTPException
from tortoise.functions import Count
from tortoise.transactions import in_transaction

from src.crud.library import favorite_song_ids
from src.database.models import CrateTracks, Crates, Songs
from src.schemas.songs import song_to_schema
from src.security.authz import ensure_owner_or_403
from src.utils.pagination import decode_cursor, encode_cursor, keyset_filter

POSITION_STEP = 1000
# The legacy full-permutation reorder is O(n) writes; above this size clients
# must use the single-track move endpoint instead (D4).
MAX_PERMUTATION_REORDER = 1000
TRACKS_PAGE_SIZE = 200


def new_share_token():
    """
    An unguessable URL-safe token identifying a crate's share link.
    """
    return secrets.token_urlsafe(24)


async def get_crate_or_404(crate_id):
    crate = await Crates.get_or_none(id=crate_id)
    if crate is None:
        raise HTTPException(status_code=404, detail="Crate not found")
    return crate


def check_can_read(crate, user):
    """
    Read access: the owner, anyone logged in when the crate is public, or a
    platform owner/admin (spec: "invisible to everyone but owner (and
    admin)").
    """
    if (
        crate.owner_id != user.id
        and not crate.public
        and getattr(user, "role", None) not in ("owner", "admin")
    ):
        raise HTTPException(status_code=403, detail="This crate is not public")


def check_is_owner(crate, user):
    """
    Write access: the crate's owner, or a platform Owner.
    """
    ensure_owner_or_403(
        crate.owner_id, user, detail="Only the crate's owner can do that"
    )


def cover_url(crate):
    return "crates/{}/cover".format(crate.id) if crate.cover_path else None


def summary_dict(crate, track_count, for_owner):
    """
    A dict matching CrateSummarySchema. The share token stays private to
    the owner.
    """
    return {
        "id": crate.id,
        "name": crate.name,
        "color": crate.color,
        "description": crate.description,
        "cover_url": cover_url(crate),
        "public": crate.public,
        "share_token": crate.share_token if for_owner else None,
        "dj_target": crate.dj_target,
        "track_count": track_count,
        "created_at": crate.created_at,
    }


async def crate_tracks(crate, chunk_size=1000):
    """
    Generator yielding the crate's membership in playlist order, in
    [chunk_size]-row pages (with songs prefetched) -- for callers that must
    walk the WHOLE crate (M3U export, duration sum) without holding a
    million-track query result in memory at once.
    """
    last_position = None
    last_id = None
    while True:
        query = CrateTracks.filter(crate_id=crate.id)
        if last_id is not None:
            query = query.filter(
                keyset_filter("position", "asc", last_position, last_id)
            )
        page = (
            await query.order_by("position", "id")
            .limit(chunk_size)
            .prefetch_related("song")
        )
        if not page:
            return
        for membership in page:
            yield membership
        last_position, last_id = page[-1].position, page[-1].id
        if len(page) < chunk_size:
            return


async def tracks_page(crate, user, cursor=None, limit=50):
    """
    One keyset page of the crate's ordered tracks, (position, id) ascending.
    """
    query = CrateTracks.filter(crate_id=crate.id)
    if cursor:
        token = decode_cursor(cursor)
        if token["s"] != "position" or token["o"] != "asc":
            raise HTTPException(status_code=422, detail="Invalid cursor")
        try:
            key_value, last_id = token["k"][0], int(token["k"][-1])
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="Invalid cursor")
        query = query.filter(keyset_filter("position", "asc", key_value, last_id))
    memberships = (
        await query.order_by("position", "id").limit(limit + 1).prefetch_related("song")
    )
    has_more = len(memberships) > limit
    memberships = memberships[:limit]
    songs = [m.song for m in memberships]
    favorites = await favorite_song_ids(user.id, [s.id for s in songs])
    items = [
        {"position": m.position, "song": song_to_schema(m.song, favorites)}
        for m in memberships
    ]
    next_cursor = None
    if has_more and memberships:
        last = memberships[-1]
        next_cursor = encode_cursor("position", "asc", [last.position, last.id])
    return items, next_cursor


async def total_duration_seconds(crate):
    # A single narrow column fetch, summed in Python: Tortoise's annotate()
    # bakes its GROUP BY from every column of the base queryset at call time,
    # so annotate(Sum(...)).values_list(...) here would silently group by
    # every song column and return each row's own duration instead of the
    # crate-wide total.
    durations = await Songs.filter(crate_tracks__crate_id=crate.id).values_list(
        "duration_seconds", flat=True
    )
    return float(sum(d or 0.0 for d in durations))


async def detail_dict(crate, user):
    """
    A dict matching CrateDetailSchema: the first page (<=200) of tracks plus
    a cursor for the rest, the full-crate track count and total duration
    (aggregated, never loading the whole membership into memory).
    """
    for_owner = crate.owner_id == user.id
    track_count = await CrateTracks.filter(crate_id=crate.id).count()
    items, next_cursor = await tracks_page(crate, user, limit=TRACKS_PAGE_SIZE)
    owner = await crate.owner
    detail = summary_dict(crate, track_count, for_owner=for_owner)
    detail["owner_id"] = crate.owner_id
    detail["owner_username"] = owner.username
    detail["total_duration_seconds"] = await total_duration_seconds(crate)
    detail["tracks"] = items
    detail["tracks_next_cursor"] = next_cursor
    return detail


async def next_position(crate):
    """
    The position for a track appended at the end of the crate: gap-based
    (D4), stepping by POSITION_STEP so most single-track moves need only
    rewrite the moved row.
    """
    last = await CrateTracks.filter(crate_id=crate.id).order_by("-position").first()
    return last.position + POSITION_STEP if last else 0


async def _rebalance(crate):
    """
    Re-spreads every membership row of [crate] to 0, STEP, 2*STEP, ... inside
    one transaction. Called when a move's midpoint gap has collapsed.
    """
    memberships = await CrateTracks.filter(crate_id=crate.id).order_by("position", "id")
    for i, membership in enumerate(memberships):
        membership.position = i * POSITION_STEP
    async with in_transaction():
        for start in range(0, len(memberships), 1000):
            end = start + 1000
            chunk = memberships[start:end]
            await CrateTracks.bulk_update(chunk, fields=["position"])


async def move_track(crate, song_id, after_song_id, _retried=False):
    """
    Moves [song_id] to sit immediately after [after_song_id] (top of the
    crate when None). New position = midpoint of its new neighbors; when the
    gap has collapsed the whole crate is rebalanced and the move retried
    once (D4).
    """
    if after_song_id is not None and after_song_id == song_id:
        raise HTTPException(
            status_code=422, detail="A track cannot be moved after itself"
        )
    memberships = await CrateTracks.filter(crate_id=crate.id).order_by("position", "id")
    by_song = {m.song_id: m for m in memberships}
    moving = by_song.get(song_id)
    if moving is None:
        raise HTTPException(status_code=404, detail="Song is not in this crate")
    if after_song_id is not None and after_song_id not in by_song:
        raise HTTPException(status_code=404, detail="Song is not in this crate")

    rest = [m for m in memberships if m.id != moving.id]
    if after_song_id is None:
        lo = None
        hi = rest[0].position if rest else None
    else:
        idx = next(i for i, m in enumerate(rest) if m.song_id == after_song_id)
        lo = rest[idx].position
        hi = rest[idx + 1].position if idx + 1 < len(rest) else None

    if lo is None:
        new_position = (hi - POSITION_STEP) if hi is not None else 0
    elif hi is None:
        new_position = lo + POSITION_STEP
    else:
        new_position = (lo + hi) // 2
        if new_position in (lo, hi):
            if _retried:
                # Should not happen (rebalance always yields room), but never
                # loop forever.
                raise HTTPException(status_code=409, detail="Could not reorder")
            await _rebalance(crate)
            return await move_track(crate, song_id, after_song_id, _retried=True)

    moving.position = new_position
    await moving.save(update_fields=["position"])
    return new_position


async def duplicate_crate(crate, new_owner, name=None):
    """
    "Duplicate to my crates": a fresh private crate owned by [new_owner],
    same name (or [name]), same description and track order, a fresh share
    token, no cover, no public flag.
    """
    copy_name = (name or "Copy of {}".format(crate.name))[:100]
    new_crate = await Crates.create(
        name=copy_name,
        color=crate.color,
        description=crate.description,
        owner_id=new_owner.id,
        share_token=new_share_token(),
    )
    memberships = await CrateTracks.filter(crate_id=crate.id).order_by("position", "id")
    new_rows = [
        CrateTracks(
            crate_id=new_crate.id, song_id=m.song_id, position=i * POSITION_STEP
        )
        for i, m in enumerate(memberships)
    ]
    for start in range(0, len(new_rows), 1000):
        end = start + 1000
        await CrateTracks.bulk_create(new_rows[start:end])
    return new_crate


async def public_crates_page(q, cursor=None, limit=50):
    """
    Public crate discovery: name/description/owner-username search over
    Postgres (trigram-indexed), newest first. Never returns a private crate
    or a share_token.
    """
    from tortoise.expressions import Q

    query = Crates.filter(public=True)
    q = (q or "").strip()
    if q:
        query = query.filter(
            Q(name__icontains=q)
            | Q(description__icontains=q)
            | Q(owner__username__icontains=q)
        )
    if cursor:
        token = decode_cursor(cursor)
        if token["s"] != "id" or token["o"] != "desc":
            raise HTTPException(status_code=422, detail="Invalid cursor")
        try:
            last_id = int(token["k"][-1])
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="Invalid cursor")
        query = query.filter(keyset_filter("id", "desc", last_id, last_id))
    crates = (
        await query.annotate(track_count=Count("tracks"))
        .order_by("-id")
        .limit(limit + 1)
        .prefetch_related("owner")
    )
    has_more = len(crates) > limit
    crates = crates[:limit]
    items = [
        {
            "id": crate.id,
            "name": crate.name,
            "color": crate.color,
            "description": crate.description,
            "cover_url": cover_url(crate),
            "owner_id": crate.owner_id,
            "owner_username": crate.owner.username,
            "track_count": int(crate.track_count),
            "created_at": crate.created_at,
        }
        for crate in crates
    ]
    next_cursor = None
    if has_more and crates:
        next_cursor = encode_cursor("id", "desc", [crates[-1].id, crates[-1].id])
    return items, next_cursor
