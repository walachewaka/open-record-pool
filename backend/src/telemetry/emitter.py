"""
The telemetry emitter (MOO-83).

emit() appends a document to an in-process bounded deque and returns; a
background asyncio task bulk-ships batches to the monthly orp-events-YYYY.MM
index every TELEMETRY_FLUSH_INTERVAL_SECONDS. No Redis, no arq, no awaiting in
the request path -- an event costs a dict build and a deque append.

Failure policy (the whole point of the design): telemetry never degrades the
app. Every entry point swallows its errors; a flush against a dead ES requeues
the batch and warns at most once a minute; a buffer that overflows drops its
OLDEST events and counts them. Nothing here can raise into a request handler.

The elasticsearch package is imported lazily (MOO-79 rule) so this module stays
importable from the Python 3.7 environments that never install it.
"""
import asyncio
import logging
import os
import time
from collections import deque
from datetime import datetime, timezone

from src.search.es import es_enabled, events_index_name

logger = logging.getLogger("orp.telemetry")

LEVELS = ("off", "basic", "detailed")

# Fields with an explicit mapping in the index template (src/telemetry/setup.py).
# Anything a call site passes outside this set is nested under "attrs" (a
# flattened field), so the strict `dynamic: false` mapping never silently drops
# it and the mapping can never explode.
MAPPED_FIELDS = frozenset(
    [
        "user_id",
        "username",
        "song_id",
        "song_label",
        "artist",
        "genre",
        "duration_ms",
        "position_ms",
        "listened_ms",
        "completion_pct",
        "format",
        "query",
        "filters",
        "result_count",
        "zero_results",
        "engine",
        "success",
        "method",
        "route",
        "status_code",
        "source",
        "fields",
        "job_kind",
        "job_status",
        "queue",
        "crate_id",
        "track_count",
        "request_id",
        "audit_id",
        "audit_event",
        "target_type",
        "target_id",
        "error",
        "ip",
        "attrs",
    ]
)

_WARN_INTERVAL_SECONDS = 60
_AUDIT_SHIP_INTERVAL_SECONDS = 60

_buffer = None
_task = None
_setup_ok = False
_warned_at = 0.0
_audit_shipped_at = 0.0

_stats = {
    "events_emitted": 0,
    "events_dropped": 0,
    "events_suppressed": 0,
    "last_flush_at": None,
    "last_error": None,
    "es_reachable": None,
}


# --- configuration (read per call so tests and the status endpoint see env
# changes without a reimport) --------------------------------------------


def _int_env(name, default):
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def enabled():
    """
    Whether events are collected at all.

    TELEMETRY_ENABLED=false turns emit() into a pure no-op, and so does an
    unset ELASTICSEARCH_URL -- there is nowhere to ship to, so we do not pay
    for the buffer. That is what keeps the ES-less environments untouched.
    """
    raw = os.environ.get("TELEMETRY_ENABLED", "true").strip().lower()
    if raw in ("false", "0", "no"):
        return False
    if level_setting() == "off":
        return False
    return es_enabled()


def level_setting():
    """The raw consent level: off | basic | detailed (default detailed)."""
    raw = os.environ.get("TELEMETRY_LEVEL", "detailed").strip().lower()
    return raw if raw in LEVELS else "detailed"


def level():
    """The effective level ("off" whenever telemetry is disabled)."""
    return level_setting() if enabled() else "off"


def buffer_max():
    return max(1, _int_env("TELEMETRY_BUFFER_MAX", 5000))


def flush_interval():
    return max(1, _int_env("TELEMETRY_FLUSH_INTERVAL_SECONDS", 2))


def flush_max_batch():
    return max(1, _int_env("TELEMETRY_FLUSH_MAX_BATCH", 500))


def retention_days():
    return max(1, _int_env("TELEMETRY_RETENTION_DAYS", 180))


def api_sample_rate():
    try:
        rate = float(os.environ.get("TELEMETRY_API_SAMPLE_RATE", "0.1"))
    except ValueError:
        return 0.1
    return min(max(rate, 0.0), 1.0)


def _get_buffer():
    global _buffer
    if _buffer is None or _buffer.maxlen != buffer_max():
        existing = list(_buffer) if _buffer is not None else []
        _buffer = deque(existing, maxlen=buffer_max())
    return _buffer


# --- emission -------------------------------------------------------------


def _envelope(event, fields, effective_level):
    now = datetime.now(timezone.utc)
    doc = {
        "@timestamp": now.strftime("%Y-%m-%dT%H:%M:%S.")
        + "{:03d}Z".format(now.microsecond // 1000),
        "event": event,
        # Precomputed so the Grafana listening-hours heatmap is one terms agg
        # instead of a painless script.
        "hour_of_day": now.hour,
        "day_of_week": now.weekday(),
    }
    attrs = dict(fields.pop("attrs", None) or {})
    for key, value in fields.items():
        if value is None:
            continue
        if key in MAPPED_FIELDS:
            doc[key] = value
        else:
            attrs[key] = value
    if effective_level == "basic":
        # The consent lever: the raw query string is the one free-text field a
        # self-hosted operator may not want recorded (D2/D3).
        doc.pop("query", None)
    if attrs:
        doc["attrs"] = attrs
    return doc


def emit(event, **fields):
    """
    Record one event. Synchronous, O(1), and it NEVER raises -- call it from
    any request path without a try/except.
    """
    try:
        effective_level = level()
        if effective_level == "off":
            _stats["events_suppressed"] += 1
            return
        if effective_level == "basic" and event == "api.request":
            _stats["events_suppressed"] += 1
            return
        buffer = _get_buffer()
        if len(buffer) >= buffer.maxlen:
            # The deque drops its oldest entry on append; count it (D2).
            _stats["events_dropped"] += 1
        buffer.append(_envelope(event, fields, effective_level))
        _stats["events_emitted"] += 1
    except Exception:  # pragma: no cover - telemetry must never break a caller
        logger.debug("telemetry emit failed for %s", event, exc_info=True)


# --- flushing -------------------------------------------------------------


def _requeue(batch):
    """Put a failed batch back at the head, counting whatever no longer fits."""
    buffer = _get_buffer()
    overflow = len(batch) + len(buffer) - buffer.maxlen
    if overflow > 0:
        _stats["events_dropped"] += overflow
    buffer.extendleft(reversed(batch))


def _warn_throttled(error):
    global _warned_at
    now = time.time()
    _stats["last_error"] = str(error)[:300]
    if now - _warned_at >= _WARN_INTERVAL_SECONDS:
        _warned_at = now
        logger.warning(
            "telemetry flush failed (buffering, will retry): %s", _stats["last_error"]
        )


async def flush_once():
    """
    Ship at most flush_max_batch() buffered events. Returns the number of
    documents accepted by ES (0 when there is nothing to do, or on failure).
    Never raises.
    """
    from src.search.es import get_es

    buffer = _get_buffer()
    if not buffer:
        return 0
    client = get_es()
    if client is None:
        return 0

    batch = [buffer.popleft() for _ in range(min(len(buffer), flush_max_batch()))]
    index = events_index_name(datetime.now(timezone.utc))
    operations = []
    for doc in batch:
        operations.append({"index": {"_index": index}})
        operations.append(doc)
    try:
        await client.bulk(operations=operations)
    except Exception as error:
        _stats["es_reachable"] = False
        _requeue(batch)
        _warn_throttled(error)
        return 0
    _stats["es_reachable"] = True
    _stats["last_error"] = None
    _stats["last_flush_at"] = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    return len(batch)


async def _tick():
    """One iteration of the background loop. Never raises."""
    global _setup_ok, _audit_shipped_at

    if not _setup_ok:
        # Retried every tick until it lands once: ES still booting at app
        # start is normal and must not cost us the template.
        from src.telemetry import setup

        _setup_ok = await setup.ensure_telemetry_setup()

    await flush_once()

    # Inline mode has no arq cron, so the audit->ES projection rides the flush
    # loop instead (D4). With workers on, src/worker.py owns the 60s cron.
    from src.jobs.queue import workers_enabled

    if not workers_enabled():
        now = time.time()
        if now - _audit_shipped_at >= _AUDIT_SHIP_INTERVAL_SECONDS:
            _audit_shipped_at = now
            from src.telemetry import shipper

            await shipper.ship_audit_events()


async def _flush_loop():
    while True:
        try:
            await asyncio.sleep(flush_interval())
            await _tick()
        except asyncio.CancelledError:
            raise
        except Exception as error:  # pragma: no cover - defensive
            _warn_throttled(error)


def start_emitter():
    """Start the background flush task (idempotent; no-op when disabled)."""
    global _task
    if not enabled() or _task is not None:
        return
    try:
        _task = asyncio.get_event_loop().create_task(_flush_loop())
    except Exception:  # pragma: no cover - no running loop
        _task = None


async def stop_emitter():
    """Cancel the loop and make one best-effort final flush."""
    global _task, _setup_ok
    task = _task
    _task = None
    _setup_ok = False
    if task is not None:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    try:
        await asyncio.wait_for(flush_once(), timeout=2)
    except Exception:
        pass


def stats():
    """The counters behind GET /admin/telemetry/status."""
    buffer = _get_buffer()
    snapshot = dict(_stats)
    snapshot["enabled"] = enabled()
    snapshot["level"] = level()
    snapshot["buffer_size"] = len(buffer)
    snapshot["buffer_capacity"] = buffer.maxlen
    snapshot["retention_days"] = retention_days()
    return snapshot


def reset_for_tests():
    """Drop the buffer and counters (harness helper; never used in the app)."""
    global _buffer, _setup_ok, _warned_at, _audit_shipped_at
    _buffer = None
    _setup_ok = False
    _warned_at = 0.0
    _audit_shipped_at = 0.0
    _stats.update(
        {
            "events_emitted": 0,
            "events_dropped": 0,
            "events_suppressed": 0,
            "last_flush_at": None,
            "last_error": None,
            "es_reachable": None,
        }
    )
