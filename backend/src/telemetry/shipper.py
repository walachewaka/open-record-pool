"""
Audit log -> Elasticsearch projection (MOO-83 D4).

Postgres stays the authoritative audit trail (MOO-89 owns it); this ships a
non-authoritative COPY into the telemetry indices so the Grafana dashboards can
chart logins and admin activity next to everything else.

No checkpoint table (so no migration): each row is written with the
deterministic id "audit-<row id>", which makes re-shipping idempotent, and the
cursor is recovered from Elasticsearch itself with a max aggregation on
audit_id. With ES down we simply skip the tick.

Runs as a 60s arq cron on orp:default (src/worker.py) and, in inline mode where
there is no worker, from the emitter's flush loop.
"""
import logging
from datetime import timezone

from src.database.models import AuditLog
from src.search.es import events_index_name, get_es
from src.telemetry.setup import INDEX_PATTERN

logger = logging.getLogger("orp.telemetry")

BATCH = 1000

# Audit events that become the first-class auth.login telemetry event.
_LOGIN_EVENTS = {"auth.login_success": True, "auth.login_failure": False}

_cursor = None


async def _load_cursor(client):
    """The highest audit_id already in ES (memoized per process)."""
    global _cursor
    if _cursor is not None:
        return _cursor
    response = await client.search(
        index=INDEX_PATTERN,
        size=0,
        query={"exists": {"field": "audit_id"}},
        aggs={"max_id": {"max": {"field": "audit_id"}}},
        allow_no_indices=True,
        ignore_unavailable=True,
    )
    value = ((response.get("aggregations") or {}).get("max_id") or {}).get("value")
    _cursor = int(value) if value else 0
    return _cursor


def _utc(value):
    """Audit rows carry aware UTC datetimes; be explicit anyway."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _document(row, created, timestamp):
    common = {
        "@timestamp": timestamp,
        "hour_of_day": created.hour,
        "day_of_week": created.weekday(),
        "audit_id": row["id"],
        "user_id": row["actor_id"],
        "username": row["actor_username"],
        "ip": row["ip"],
    }
    if row["event"] in _LOGIN_EVENTS:
        common["event"] = "auth.login"
        common["success"] = _LOGIN_EVENTS[row["event"]]
        return common
    common["event"] = "audit." + row["event"]
    common["audit_event"] = row["event"]
    common["target_type"] = row["target_type"]
    common["target_id"] = row["target_id"]
    return common


async def ship_audit_events(ctx=None):
    """Ship the audit rows added since the cursor. Never raises."""
    global _cursor

    client = get_es()
    if client is None:
        return 0
    try:
        cursor = await _load_cursor(client)
        rows = (
            await AuditLog.filter(id__gt=cursor)
            .order_by("id")
            .limit(BATCH)
            .values(
                "id",
                "created_at",
                "event",
                "actor_id",
                "actor_username",
                "target_type",
                "target_id",
                "ip",
            )
        )
        if not rows:
            return 0
        operations = []
        for row in rows:
            created = _utc(row["created_at"])
            timestamp = created.strftime("%Y-%m-%dT%H:%M:%S.") + "{:03d}Z".format(
                created.microsecond // 1000
            )
            operations.append(
                {
                    "index": {
                        "_index": events_index_name(created),
                        "_id": "audit-{}".format(row["id"]),
                    }
                }
            )
            operations.append(_document(row, created, timestamp))
        await client.bulk(operations=operations)
        _cursor = rows[-1]["id"]
        return len(rows)
    except Exception as error:
        logger.warning("audit shipper tick skipped: %s", error)
        return 0


async def shipped_cursor():
    """The highest shipped audit id, straight from ES (status endpoint). None
    when ES is unreachable."""
    client = get_es()
    if client is None:
        return None
    try:
        response = await client.search(
            index=INDEX_PATTERN,
            size=0,
            query={"exists": {"field": "audit_id"}},
            aggs={"max_id": {"max": {"field": "audit_id"}}},
            allow_no_indices=True,
            ignore_unavailable=True,
        )
        value = ((response.get("aggregations") or {}).get("max_id") or {}).get("value")
        return int(value) if value else 0
    except Exception:
        return None


def reset_for_tests():
    global _cursor
    _cursor = None
