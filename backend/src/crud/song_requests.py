"""
CRUD + business logic for the song request system (MOO-81): submission
(open-duplicate guard, MOO-90 dedup check, quota, auto-approve), moderation
(approve/reject/retry/bulk), member reads (list/summary/seen/cancel), and the
download-status read-repair that flips a `downloading` row to
`fulfilled`/`failed` once its linked MOO-78 download reaches a terminal
state.

D3.4 (decided, no callback into MOO-78's code): `download_id` is a soft,
un-FK'd reference to `download_requests.id` so this table never breaks if
that one's shape moves under it. sync_requests_from_downloads() runs as
read-repair (top of every list/summary/detail read, batched, scoped to the
rows about to be shown) and as a 60s worker cron -- decoupled by design
across the multi-process deployment (api / worker / worker-heavy containers).

MOO-78 has no query-search entry point (only a provider URL, confirmed by
reading src/downloads/service.py) -- despite the original ask, free-text
requests cannot be auto-fulfilled from an artist/title alone. Auto-approve
therefore only ever applies to kind="url" requests; a free-text request
always lands `pending` and a moderator supplies a source_url at approval
time (ApproveSchema.source_url) to fulfill it.
"""

from datetime import datetime, timezone

from fastapi import HTTPException
from tortoise.expressions import Q

from src.auth.permissions import has_permission
from src.database.models import DownloadRequests, Songs, SongRequests
from src.downloads.service import DownloadPolicyError, enqueue_download
from src.schemas.song_requests import AdminRequestOut, RequestOut, song_mini
from src.security import audit
from src.security.ratelimit import rate_limit
from src.security.urlcheck import validate_provider_url
from src.telemetry import events
from src.utils.pagination import decode_cursor, encode_cursor, keyset_filter
import src.crud.settings as settings_crud

OPEN_STATUSES = ("pending", "approved", "downloading")
TERMINAL_STATUSES = ("fulfilled", "failed", "rejected", "duplicate", "cancelled")
STATUSES = OPEN_STATUSES + TERMINAL_STATUSES

# Mirrors src/downloads/service.py's ACTIVE_STATES/TERMINAL_STATES split.
_DOWNLOAD_ACTIVE = ("queued", "fetching", "postprocessing")
_DOWNLOAD_SUCCESS = ("imported", "duplicate_skipped")
_DOWNLOAD_FAILURE = ("failed", "cancelled")

_BATCH = 1000
_PREFETCH = (
    "user",
    "decided_by",
    "duplicate_of",
    "possible_duplicate_of",
    "fulfilled_song",
)


def _chunks(values, size=_BATCH):
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _utcnow():
    return datetime.now(timezone.utc)


def _start_of_utc_day():
    return _utcnow().replace(hour=0, minute=0, second=0, microsecond=0)


def _normalize_text(value):
    return " ".join((value or "").strip().lower().split())


def normalize_key(kind, artist=None, title=None, mix_name=None, source_url=None):
    if kind == "url":
        return (source_url or "").strip().lower()
    parts = [_normalize_text(artist), _normalize_text(title)]
    if mix_name:
        parts.append(_normalize_text(mix_name))
    return "|".join(parts)


def serialize(request, admin=False):
    """A RequestOut (or AdminRequestOut) from a row whose FKs are prefetched."""
    fields = dict(
        id=request.id,
        kind=request.kind,
        artist=request.artist,
        title=request.title,
        mix_name=request.mix_name,
        source_url=request.source_url,
        provider=request.provider,
        notes=request.notes,
        status=request.status,
        reason=request.reason,
        duplicate_of=song_mini(getattr(request, "duplicate_of", None)),
        possible_duplicate_of=song_mini(
            getattr(request, "possible_duplicate_of", None)
        ),
        fulfilled_song=song_mini(getattr(request, "fulfilled_song", None)),
        download_id=request.download_id,
        resolved_seen=request.resolved_seen,
        created_at=request.created_at,
        decided_at=request.decided_at,
    )
    if not admin:
        return RequestOut(**fields)
    requester = getattr(request, "user", None)
    decided_by = getattr(request, "decided_by", None)
    fields["requester_id"] = request.user_id
    fields["requester_username"] = getattr(requester, "username", None)
    fields["decided_by_username"] = getattr(decided_by, "username", None)
    return AdminRequestOut(**fields)


def _validate_status(status):
    if status is not None and status not in STATUSES:
        raise HTTPException(
            status_code=422,
            detail="status must be one of: {}".format(", ".join(STATUSES)),
        )


def _cursor_last_id(cursor):
    token = decode_cursor(cursor)
    if token["s"] != "id" or token["o"] != "desc":
        raise HTTPException(status_code=422, detail="Invalid cursor")
    try:
        return int(token["k"][-1])
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Invalid cursor")


async def _paginate(query, limit, cursor, admin=False):
    if cursor:
        last_id = _cursor_last_id(cursor)
        query = query.filter(keyset_filter("id", "desc", last_id, last_id))
    rows = await query.order_by("-id").limit(limit).prefetch_related(*_PREFETCH)
    await _repair_rows([row for row in rows if row.status == "downloading"])
    items = [serialize(row, admin=admin) for row in rows]
    next_cursor = None
    if len(items) == limit:
        next_cursor = encode_cursor("id", "desc", [rows[-1].id, rows[-1].id])
    return items, next_cursor


# --- MOO-90 dedup + MOO-78 fulfillment wrappers -----------------------------


async def _dedup_check(artist, title, mix_name):
    """
    MOO-90 pre-submission check (D3.2). Returns (confidence, song):
    confidence is "certain" (external-id or high-confidence fingerprint --
    blocks the request as a duplicate), "likely" (everything else
    check_library finds, including the review-only metadata layer --
    surfaces as a possible-duplicate warning without blocking), or None.
    """
    from src.services.dedup import check_library, load_config

    result = await check_library(artist=artist, title=title, mix=mix_name)
    if not result["found"]:
        return None, None
    song = await Songs.get_or_none(id=result["canonical_song_id"])
    if song is None:
        return None, None
    if result["match_layer"] == "external_id":
        return "certain", song
    if result["match_layer"] == "fingerprint":
        cfg = await load_config()
        if (result["confidence"] or 0) >= cfg["fp_threshold"]:
            return "certain", song
        return "likely", song
    return "likely", song


async def _enqueue_fulfillment(req, request=None, source_url=None):
    """
    D3.3: turn an approved/auto-approved request into a MOO-78 download.
    url-kind requests use their own source_url; free_text requests have none
    of their own (MOO-78 cannot search) so the caller must supply one. Any
    engine rejection lands the request `failed` with a sanitized reason,
    never the raw exception.
    """
    url = req.source_url if req.kind == "url" else source_url
    if not url:
        req.status = "failed"
        req.reason = "This is a free-text request; approve it with a source URL."
        await req.save(update_fields=["status", "reason", "modified_at"])
        return req

    try:
        download = await enqueue_download(
            url,
            requested_by_id=req.user_id,
            origin="request",
            origin_ref=str(req.id),
            enforce_user_policy=False,
            request=request,
        )
    except DownloadPolicyError as error:
        req.status = "failed"
        req.reason = str(error.detail)[:200]
        await req.save(update_fields=["status", "reason", "modified_at"])
        return req

    req.download_id = download.id
    req.provider = download.provider
    if req.kind == "url" and not req.source_url:
        req.source_url = download.url
    req.status = "downloading"
    await req.save(
        update_fields=["download_id", "provider", "source_url", "status", "modified_at"]
    )
    return req


# --- submission --------------------------------------------------------------


async def create_request(user, payload, request=None):
    if not bool(await settings_crud.get_value("song_requests", "enabled")):
        raise HTTPException(
            status_code=403, detail="Song requests are disabled on this pool."
        )

    await rate_limit("request_submit", str(user.id), 5, 60)

    quota = await settings_crud.get_value("song_requests", "daily_quota")
    try:
        quota = int(quota)
    except (TypeError, ValueError):
        quota = 0
    if quota:
        used_today = await SongRequests.filter(
            user_id=user.id, created_at__gte=_start_of_utc_day()
        ).count()
        if used_today >= quota:
            raise HTTPException(status_code=429, detail="Daily request quota reached.")

    provider = None
    source_url = None
    if payload.kind == "url":
        validated = validate_provider_url(payload.source_url)  # raises 422
        provider = validated.provider
        source_url = validated.canonical_url

    normalized = normalize_key(
        payload.kind,
        artist=payload.artist,
        title=payload.title,
        mix_name=payload.mix_name,
        source_url=source_url,
    )
    existing_open = await SongRequests.filter(
        normalized_key=normalized, status__in=list(OPEN_STATUSES)
    ).first()
    if existing_open is not None:
        raise HTTPException(
            status_code=409, detail="This track has already been requested."
        )

    # The dedup check needs artist/title; url-kind requests carry no parsed
    # metadata pre-fetch, so it only runs for free-text submissions.
    confidence, match = (None, None)
    if payload.kind == "free_text":
        confidence, match = await _dedup_check(
            payload.artist, payload.title, payload.mix_name
        )

    req = await SongRequests.create(
        user_id=user.id,
        kind=payload.kind,
        artist=payload.artist,
        title=payload.title,
        mix_name=payload.mix_name,
        source_url=source_url,
        provider=provider,
        notes=payload.notes,
        normalized_key=normalized,
        status="duplicate" if confidence == "certain" else "pending",
        duplicate_of=match if confidence == "certain" else None,
        possible_duplicate_of=match if confidence == "likely" else None,
    )
    await audit.audit_event(
        audit.SONG_REQUEST_CREATED,
        request=request,
        actor=user,
        target_type="song_request",
        target_id=req.id,
        detail={"kind": payload.kind, "status": req.status},
    )
    events.request_event("created", req.id, req.provider, user.id)

    if req.status == "pending" and payload.kind == "url":
        roles = await settings_crud.get_value("song_requests", "auto_approve_roles")
        if not isinstance(roles, list):
            roles = []
        if user.role == "owner" or user.role in roles:
            req.decided_by_id = user.id
            req.decided_at = _utcnow()
            await req.save(update_fields=["decided_by_id", "decided_at", "modified_at"])
            req = await _enqueue_fulfillment(req, request=request)
            await audit.audit_event(
                audit.SONG_REQUEST_AUTO_APPROVED,
                request=request,
                actor=user,
                target_type="song_request",
                target_id=req.id,
                detail={"status": req.status},
            )

    return await get_request(req.id)


# --- member reads --------------------------------------------------------------


async def get_request(request_id):
    return await SongRequests.filter(id=request_id).prefetch_related(*_PREFETCH).first()


async def get_for_user_or_404(request_id, current_user, allow_permission=None):
    """IDOR-safe fetch: owner, or a caller with allow_permission; else 404."""
    req = await get_request(request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.user_id != current_user.id:
        if not allow_permission or not await has_permission(
            current_user, allow_permission
        ):
            raise HTTPException(status_code=404, detail="Request not found")
    if req.status == "downloading":
        await _repair_rows([req])
        req = await get_request(request_id)
    return req


async def list_mine(user_id, status=None, cursor=None, limit=50):
    _validate_status(status)
    query = SongRequests.filter(user_id=user_id)
    if status:
        query = query.filter(status=status)
    return await _paginate(query, limit, cursor)


async def summary(user_id):
    await _repair_rows(await SongRequests.filter(user_id=user_id, status="downloading"))
    open_count = await SongRequests.filter(
        user_id=user_id, status__in=list(OPEN_STATUSES)
    ).count()
    unseen = await SongRequests.filter(
        user_id=user_id, status__in=list(TERMINAL_STATUSES), resolved_seen=False
    ).count()
    return {"open": open_count, "unseen_resolved": unseen}


async def mark_seen(user_id):
    rows = await SongRequests.filter(
        user_id=user_id, status__in=list(TERMINAL_STATUSES), resolved_seen=False
    )
    for chunk in _chunks([row.id for row in rows]):
        await SongRequests.filter(id__in=chunk).update(resolved_seen=True)
    return len(rows)


async def cancel(req, current_user, request=None):
    if req.status != "pending":
        raise HTTPException(
            status_code=409, detail="Only pending requests can be cancelled."
        )
    req.status = "cancelled"
    # Self-initiated: nothing to notify the requester about, so this never
    # lights up their own "unseen" badge.
    req.resolved_seen = True
    await req.save(update_fields=["status", "resolved_seen", "modified_at"])
    await audit.audit_event(
        audit.SONG_REQUEST_CANCELLED,
        request=request,
        actor=current_user,
        target_type="song_request",
        target_id=req.id,
    )
    return await get_request(req.id)


# --- admin ---------------------------------------------------------------------


async def admin_list(status="pending", q=None, cursor=None, limit=50):
    if status and status != "all":
        _validate_status(status)
    query = SongRequests.all()
    if status and status != "all":
        query = query.filter(status=status)
    if q:
        query = query.filter(
            Q(artist__icontains=q)
            | Q(title__icontains=q)
            | Q(source_url__icontains=q)
            | Q(user__username__icontains=q)
        )
    return await _paginate(query, limit, cursor, admin=True)


async def admin_stats():
    return {"pending": await SongRequests.filter(status="pending").count()}


async def approve(req, current_user, source_url=None, request=None):
    if req.status != "pending":
        raise HTTPException(status_code=409, detail="Request is not pending.")
    req.decided_by_id = current_user.id
    req.decided_at = _utcnow()
    await req.save(update_fields=["decided_by_id", "decided_at", "modified_at"])
    req = await _enqueue_fulfillment(req, request=request, source_url=source_url)
    await audit.audit_event(
        audit.SONG_REQUEST_APPROVED,
        request=request,
        actor=current_user,
        target_type="song_request",
        target_id=req.id,
        detail={"status": req.status},
    )
    events.request_event("approved", req.id, req.provider, req.user_id)
    return await get_request(req.id)


async def reject(req, current_user, reason=None, request=None):
    if req.status not in ("pending", "approved", "failed"):
        raise HTTPException(status_code=409, detail="Request cannot be rejected.")
    req.status = "rejected"
    req.reason = reason
    req.decided_by_id = current_user.id
    req.decided_at = _utcnow()
    req.resolved_seen = False
    await req.save(
        update_fields=[
            "status",
            "reason",
            "decided_by_id",
            "decided_at",
            "resolved_seen",
            "modified_at",
        ]
    )
    await audit.audit_event(
        audit.SONG_REQUEST_REJECTED,
        request=request,
        actor=current_user,
        target_type="song_request",
        target_id=req.id,
        detail={"reason": reason},
    )
    events.request_event("rejected", req.id, req.provider, req.user_id)
    return await get_request(req.id)


async def retry(req, current_user, request=None):
    if req.status != "failed":
        raise HTTPException(
            status_code=409, detail="Only failed requests can be retried."
        )
    req.reason = None
    await req.save(update_fields=["reason", "modified_at"])
    req = await _enqueue_fulfillment(req, request=request, source_url=req.source_url)
    await audit.audit_event(
        audit.SONG_REQUEST_RETRIED,
        request=request,
        actor=current_user,
        target_type="song_request",
        target_id=req.id,
        detail={"status": req.status},
    )
    return await get_request(req.id)


async def bulk(ids, action, current_user, reason=None, request=None):
    rows = await SongRequests.filter(id__in=ids[:_BATCH])
    by_id = {row.id: row for row in rows}
    updated = 0
    skipped = []
    for request_id in ids:
        row = by_id.get(request_id)
        if row is None:
            skipped.append(request_id)
            continue
        try:
            if action == "approve":
                await approve(row, current_user, request=request)
            else:
                await reject(row, current_user, reason=reason, request=request)
            updated += 1
        except HTTPException:
            skipped.append(request_id)
    return {"updated": updated, "skipped": skipped}


# --- download-status read-repair (D3.4) -----------------------------------


async def _repair_rows(rows):
    """Sync the given (already-`downloading`) rows against their linked
    download_requests row. Cheap no-op when nothing has landed yet."""
    download_ids = [row.download_id for row in rows if row.download_id]
    if not download_ids:
        return
    downloads_by_id = {}
    for chunk in _chunks(download_ids):
        for dl in await DownloadRequests.filter(id__in=chunk):
            downloads_by_id[dl.id] = dl
    for row in rows:
        dl = downloads_by_id.get(row.download_id)
        if dl is None or dl.status in _DOWNLOAD_ACTIVE:
            continue
        if dl.status in _DOWNLOAD_SUCCESS:
            row.status = "fulfilled"
            row.fulfilled_song_id = dl.song_id
            row.reason = None
            row.resolved_seen = False
            await row.save(
                update_fields=[
                    "status",
                    "fulfilled_song_id",
                    "reason",
                    "resolved_seen",
                    "modified_at",
                ]
            )
            await audit.audit_event(
                audit.SONG_REQUEST_FULFILLED,
                target_type="song_request",
                target_id=row.id,
                detail={"song_id": dl.song_id},
            )
            events.request_event("fulfilled", row.id, row.provider, row.user_id)
        elif dl.status in _DOWNLOAD_FAILURE:
            row.status = "failed"
            row.reason = "Download failed ({}).".format(row.provider or "provider")
            row.resolved_seen = False
            await row.save(
                update_fields=["status", "reason", "resolved_seen", "modified_at"]
            )
            await audit.audit_event(
                audit.SONG_REQUEST_FAILED,
                target_type="song_request",
                target_id=row.id,
                detail={"download_status": dl.status},
            )


async def sync_requests_from_downloads(request_ids=None):
    """The worker-cron entry point (D3.4): repair every `downloading` row,
    or only `request_ids` when called as targeted read-repair."""
    query = SongRequests.filter(status="downloading")
    if request_ids is not None:
        if not request_ids:
            return
        query = query.filter(id__in=list(request_ids))
    await _repair_rows(await query)
