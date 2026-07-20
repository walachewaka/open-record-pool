"""
Download engine service layer (MOO-78 D7): the submission policy + the internal
enqueue contract consumed by the member routes and by later stages (MOO-81 song
requests via origin "request", MOO-80 artist-follow via "artist_follow").

Public surface:
    enqueue_download(url, requested_by_id, origin, origin_ref, priority,
                     enforce_user_policy) -> DownloadRequests
    DownloadPolicyError / DuplicateActiveRequest
    register_completion_hook(origin, async_callback) / fire_completion_hooks
    providers_status() for the /fetch/providers UI gate
"""
import asyncio
import os
from datetime import datetime, timezone

from src.database.models import DownloadRequests
from src.jobs.queue import QUEUE_HEAVY, submit_job, workers_enabled
from src.security import audit
from src.security.ratelimit import rate_limit
from src.security.urlcheck import validate_provider_url
import src.crud.settings as settings_crud

ACTIVE_STATES = ("queued", "fetching", "postprocessing")
TERMINAL_STATES = ("imported", "duplicate_skipped", "failed", "cancelled")

# provider name -> the integrations.* per-provider enable key
_PROVIDER_FLAG = {
    "youtube": "downloads_youtube",
    "soundcloud": "downloads_soundcloud",
    "spotify": "downloads_spotify",
}

_TOOL_BINS = {
    "yt-dlp": os.environ.get("YTDLP_BIN", "/opt/tools/yt-dlp/bin/yt-dlp"),
    "scdl": os.environ.get("SCDL_BIN", "/opt/tools/scdl/bin/scdl"),
    "spotdl": os.environ.get("SPOTDL_BIN", "/opt/tools/spotdl/bin/spotdl"),
}


class DownloadPolicyError(Exception):
    """A submission was rejected by policy. Carries an HTTP status + detail."""

    def __init__(self, status_code, detail):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class DuplicateActiveRequest(DownloadPolicyError):
    """The same (provider, external_id) already has an active request."""

    def __init__(self, existing):
        super().__init__(409, "This track is already queued")
        self.existing = existing


# --- completion hooks (MOO-81/MOO-80 fan-out) -----------------------------

_COMPLETION_HOOKS = {}  # origin -> [async callback(request)]


def register_completion_hook(origin, callback):
    """Register an async callback fired on every terminal transition of a
    request with this origin. Idempotent per (origin, callback)."""
    hooks = _COMPLETION_HOOKS.setdefault(origin, [])
    if callback not in hooks:
        hooks.append(callback)


async def fire_completion_hooks(request):
    """Best-effort dispatch to hooks registered for request.origin."""
    for callback in _COMPLETION_HOOKS.get(request.origin, []):
        try:
            await callback(request)
        except Exception:  # pragma: no cover - a hook must never break ingest
            pass


# --- settings readers ------------------------------------------------------


async def downloads_enabled():
    return bool(await settings_crud.get_value("integrations", "downloads_enabled"))


async def provider_enabled(provider):
    flag = _PROVIDER_FLAG.get(provider)
    if not flag:
        return False
    return bool(await settings_crud.get_value("integrations", flag))


async def require_approval():
    return bool(
        await settings_crud.get_value("integrations", "downloads_require_approval")
    )


async def daily_limit():
    try:
        return int(
            await settings_crud.get_value("integrations", "downloads_daily_limit")
        )
    except (TypeError, ValueError):
        return 0


def _start_of_utc_day():
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


async def daily_used(user_id):
    """Requests this user submitted today (UTC), excluding no-op outcomes."""
    if user_id is None:
        return 0
    return (
        await DownloadRequests.filter(
            requested_by_id=user_id, created_at__gte=_start_of_utc_day()
        )
        .exclude(status__in=["duplicate_skipped", "cancelled"])
        .count()
    )


def inline_downloads_ok():
    """Test-only escape hatch: run the task inline against mocked adapters."""
    return os.environ.get("DOWNLOADS_INLINE_OK", "").strip().lower() in ("true", "1")


# --- the enqueue contract --------------------------------------------------


async def enqueue_download(
    url,
    requested_by_id,
    origin="member",
    origin_ref=None,
    priority="normal",
    enforce_user_policy=True,
    request=None,
):
    """
    Validate + admit a download and enqueue the fetch job. Raises
    DownloadPolicyError (or DuplicateActiveRequest) on any rejection; returns
    the created DownloadRequests row on success.

    enforce_user_policy=False is for already-moderated system callers (MOO-81/
    80): it skips the rate-limit + daily-quota checks but NEVER the URL
    validation or the enable/worker gates.
    """
    validated = validate_provider_url(url)  # raises HTTPException(422)

    if not await downloads_enabled():
        raise DownloadPolicyError(403, "Downloads are disabled on this pool")
    if not await provider_enabled(validated.provider):
        raise DownloadPolicyError(
            403, "The {} provider is disabled".format(validated.provider)
        )
    if not workers_enabled() and not inline_downloads_ok():
        raise DownloadPolicyError(
            503, "Download workers are not enabled on this deployment"
        )

    if enforce_user_policy and requested_by_id is not None:
        # Fixed-window rate limit (SECURITY.md 5) + per-user daily quota (D6).
        await rate_limit("fetch_submit", str(requested_by_id), 10, 60)
        limit = await daily_limit()
        if limit and await daily_used(requested_by_id) >= limit:
            raise DownloadPolicyError(429, "Daily download request limit reached")

    existing = (
        await DownloadRequests.filter(
            provider=validated.provider,
            external_id=validated.external_id,
            status__in=list(ACTIVE_STATES),
        )
        .order_by("-id")
        .first()
    )
    if existing is not None:
        raise DuplicateActiveRequest(existing)

    req = await DownloadRequests.create(
        provider=validated.provider,
        url=validated.canonical_url,
        external_id=validated.external_id,
        status="queued",
        origin=origin,
        origin_ref=origin_ref,
        priority=priority,
        requested_by_id=requested_by_id,
    )
    await audit.audit_event(
        "download.requested",
        request=request,
        actor=_actor(requested_by_id),
        target_type="download",
        target_id=req.id,
        detail={"provider": validated.provider, "origin": origin},
    )

    # Enqueue on the heavy tier. In inline mode submit_job runs the pipeline
    # synchronously (test path only), so the row is already terminal on return.
    job = await submit_job(
        "fetch_track",
        payload={"request_id": req.id},
        user_id=requested_by_id,
        queue=QUEUE_HEAVY,
    )
    req = await DownloadRequests.get(id=req.id)
    if req.job_id is None:
        req.job_id = job.id
        await req.save(update_fields=["job_id"])
    return req


def _actor(user_id):
    if user_id is None:
        return None
    return type("_Actor", (), {"id": user_id, "username": None})()


# --- tool version cache (for GET /fetch/providers) -------------------------

_VERSION_CACHE = None


async def _tool_version(binary):
    try:
        proc = await asyncio.create_subprocess_exec(
            binary,
            "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        text = (out or b"").decode("utf-8", "replace").strip().splitlines()
        return text[0].strip() if text else None
    except Exception:
        return None


async def tool_versions():
    """Cached {tool: version|None} read once from `<bin> --version`."""
    global _VERSION_CACHE
    if _VERSION_CACHE is None:
        _VERSION_CACHE = {}
        for name, binary in _TOOL_BINS.items():
            _VERSION_CACHE[name] = await _tool_version(binary)
    return dict(_VERSION_CACHE)


async def providers_status(user_id):
    """The availability payload for the UI gate (GET /fetch/providers)."""
    enabled = await downloads_enabled()
    limit = await daily_limit()
    return {
        "enabled": enabled,
        "providers": {
            "youtube": await provider_enabled("youtube"),
            "soundcloud": await provider_enabled("soundcloud"),
            "spotify": await provider_enabled("spotify"),
        },
        "daily_limit": limit,
        "used_today": await daily_used(user_id),
        "tool_versions": await tool_versions(),
    }
