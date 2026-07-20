"""
Elasticsearch bootstrap for telemetry (MOO-83): the ILM retention policy and
the composable index template behind orp-events-*.

Both PUTs are idempotent, so every process (API and both workers) may run this
on startup, and the flush loop retries until it lands once -- an ES that is
still booting costs nothing.

The mapping is `dynamic: false` on purpose: an unmapped field is stored in
_source but never indexed, so a stray call site can never explode the mapping.
Fields outside the list below travel under the flattened "attrs" object.
"""
import logging

logger = logging.getLogger("orp.telemetry")

TEMPLATE_NAME = "orp-events"
INDEX_PATTERN = "orp-events-*"
ILM_POLICY_NAME = "orp-events-retention"

PROPERTIES = {
    "@timestamp": {"type": "date"},
    "event": {"type": "keyword"},
    "user_id": {"type": "long"},
    "username": {"type": "keyword"},
    "hour_of_day": {"type": "byte"},
    "day_of_week": {"type": "byte"},
    "song_id": {"type": "long"},
    "song_label": {"type": "keyword"},
    "artist": {"type": "keyword"},
    "genre": {"type": "keyword"},
    "duration_ms": {"type": "long"},
    "position_ms": {"type": "long"},
    "listened_ms": {"type": "long"},
    "completion_pct": {"type": "float"},
    "format": {"type": "keyword"},
    "query": {
        "type": "text",
        "fields": {"raw": {"type": "keyword", "ignore_above": 256}},
    },
    "filters": {"type": "flattened"},
    "result_count": {"type": "integer"},
    "zero_results": {"type": "boolean"},
    "engine": {"type": "keyword"},
    "success": {"type": "boolean"},
    "method": {"type": "keyword"},
    "route": {"type": "keyword"},
    "status_code": {"type": "short"},
    "source": {"type": "keyword"},
    "fields": {"type": "keyword"},
    "job_kind": {"type": "keyword"},
    "job_status": {"type": "keyword"},
    "queue": {"type": "keyword"},
    "crate_id": {"type": "long"},
    "track_count": {"type": "integer"},
    "request_id": {"type": "long"},
    "audit_id": {"type": "long"},
    "audit_event": {"type": "keyword"},
    "target_type": {"type": "keyword"},
    "target_id": {"type": "keyword"},
    "error": {"type": "text"},
    "ip": {"type": "keyword"},
    "attrs": {"type": "flattened"},
}


def ilm_policy(days):
    """Delete raw events once the index is [days] old (no rollover: the
    monthly index ages from its creation date, so effective raw retention is
    days..days+31 -- documented and accepted)."""
    return {
        "phases": {
            "hot": {"min_age": "0ms", "actions": {}},
            "delete": {"min_age": "{}d".format(days), "actions": {"delete": {}}},
        }
    }


def index_template():
    return {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "refresh_interval": "5s",
            "index.lifecycle.name": ILM_POLICY_NAME,
        },
        "mappings": {"dynamic": False, "properties": PROPERTIES},
    }


async def ensure_telemetry_setup():
    """PUT the policy and the template. Returns True on success; never raises."""
    from src.search.es import get_es
    from src.telemetry.emitter import retention_days

    client = get_es()
    if client is None:
        return False
    try:
        await client.ilm.put_lifecycle(
            name=ILM_POLICY_NAME, policy=ilm_policy(retention_days())
        )
        await client.indices.put_index_template(
            name=TEMPLATE_NAME,
            index_patterns=[INDEX_PATTERN],
            priority=200,
            template=index_template(),
        )
        logger.info("telemetry index template and ILM policy are in place")
        return True
    except Exception as error:
        logger.warning("telemetry ES setup deferred: %s", error)
        return False
