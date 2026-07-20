"""
Fixed-window rate limiting (MOO-89).

A tiny in-house limiter so we take on no new third-party pin (slowapi's pins
conflict across the 3.7 harness venv and the 3.11 image). Backend selection is
decided once at import:

- if REDIS_URL is set and redis.asyncio imports, use Redis INCR + EXPIRE
  (shared across API replicas -- reuses the MOO-77 Redis, we do NOT add a new
  requirement here);
- otherwise an in-process per-worker dict (adequate for the single-uvicorn
  deployment; multi-replica deployments must set REDIS_URL -- see SECURITY.md).

rate_limit(bucket, key, limit, window_seconds) raises HTTPException(429) when
the current fixed window is full; rate_limit_clear(bucket, key) drops the
counter (e.g. on a successful login).

The whole limiter is disabled when RATE_LIMIT_ENABLED is falsey, so live e2e
stacks can turn it off; the security harness runs with it on.
"""
import math
import os
import time
from typing import Dict, Optional, Tuple

from fastapi import HTTPException


def rate_limit_enabled() -> bool:
    return os.environ.get("RATE_LIMIT_ENABLED", "true").strip().lower() not in (
        "false",
        "0",
        "no",
        "",
    )


# --- backend selection (decided once at import) ---------------------------

_redis = None  # type: ignore
_redis_url = os.environ.get("REDIS_URL")
if _redis_url:
    try:
        from redis.asyncio import Redis  # type: ignore

        _redis = Redis.from_url(_redis_url)
    except Exception:  # pragma: no cover - redis absent in inline mode
        _redis = None

# In-process fallback store: {(bucket, key): (window_start, count)}.
_local = {}  # type: Dict[Tuple[str, str], Tuple[int, int]]


def _window_start(now: float, window_seconds: int) -> int:
    return int(now) - (int(now) % window_seconds)


def _too_many(retry_after: int) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail="Too many attempts. Try again in {} seconds.".format(retry_after),
        headers={"Retry-After": str(max(1, retry_after))},
    )


async def rate_limit(
    bucket: str, key: Optional[str], limit: int, window_seconds: int
) -> None:
    """
    Count one hit against the fixed window and raise 429 when it overflows.

    The count is incremented as a side effect: call it once per attempt. A
    None/empty key is coerced to "unknown" so a missing client host can never
    crash the request path.
    """
    if not rate_limit_enabled():
        return
    key = key or "unknown"
    now = time.time()
    win = _window_start(now, window_seconds)
    retry_after = int(math.ceil((win + window_seconds) - now))

    if _redis is not None:
        try:
            redis_key = "rl:{}:{}:{}".format(bucket, key, win)
            count = await _redis.incr(redis_key)
            if count == 1:
                await _redis.expire(redis_key, window_seconds)
            if count > limit:
                raise _too_many(retry_after)
            return
        except HTTPException:
            raise
        except Exception:
            # Redis down -> fail open rather than lock everyone out; fall back
            # to the in-process counter for this process.
            pass

    store_key = (bucket, key)
    cur = _local.get(store_key)
    if cur is None or cur[0] != win:
        _local[store_key] = (win, 1)
        count = 1
    else:
        count = cur[1] + 1
        _local[store_key] = (win, count)
    # Opportunistic pruning of stale windows to bound memory.
    if len(_local) > 4096:
        for k, v in list(_local.items()):
            if v[0] != win:
                _local.pop(k, None)
    if count > limit:
        raise _too_many(retry_after)


async def rate_limit_clear(bucket: str, key: Optional[str]) -> None:
    """Reset a bucket's counter for a key (e.g. after a successful login)."""
    if not rate_limit_enabled():
        return
    key = key or "unknown"
    if _redis is not None:
        try:
            now = time.time()
            # Clear the current and previous window so a success fully resets.
            for window_seconds in (60, 300, 3600):
                win = _window_start(now, window_seconds)
                await _redis.delete("rl:{}:{}:{}".format(bucket, key, win))
        except Exception:
            pass
    for k in list(_local.keys()):
        if k[0] == bucket and k[1] == key:
            _local.pop(k, None)


def client_ip(request) -> str:
    """
    The rate-limit key for a request: the direct socket peer. We deliberately
    do NOT trust X-Forwarded-For (spoofable; NGINX does not proxy the API).
    """
    client = getattr(request, "client", None)
    if client is not None and getattr(client, "host", None):
        return client.host
    return "unknown"
