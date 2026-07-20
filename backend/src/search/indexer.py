"""
The read side of the search outbox (MOO-79): index bootstrap + the drain.

drain_outbox() claims pending rows, coalesces them to the latest op per song,
rebuilds every doc fresh from PostgreSQL, and bulk-writes through the
orp-tracks alias. Failed rows keep their attempts count; rows that failed
MAX_ATTEMPTS times are skipped by the claim (surfaced as dead_rows in
/admin/search/status) so one poison row can never wedge the drain.
"""
import logging
from datetime import datetime, timezone

from src.database.models import SearchOutbox, Songs
from src.search.docs import build_song_docs
from src.search.es import INDEX_ALIAS, INDEX_PREFIX, get_es
from src.search.mapping import MAPPINGS, SETTINGS

logger = logging.getLogger("orp.search")

CLAIM_BATCH = 5000
BULK_CHUNK = 2000
MAX_ATTEMPTS = 10

_IN_CHUNK = 1000


def _chunks(values, size=_IN_CHUNK):
    for start in range(0, len(values), size):
        end = start + size
        yield values[start:end]


async def ensure_search_index():
    """
    First-boot bootstrap: create orp-tracks-v1 + the alias when the alias
    does not exist yet. Tolerant of ES being down (warn and stay degraded);
    runs at FastAPI startup and at arq worker startup.
    """
    client = get_es()
    if client is None:
        return False
    try:
        if await client.indices.exists_alias(name=INDEX_ALIAS):
            # Additive mapping refresh (MOO-87): the index is dynamic:strict,
            # so fields added to MAPPINGS since the index was created must be
            # PUT onto it or every upsert carrying them is rejected. Purely
            # additive put_mapping calls are always legal; anything else
            # still requires the versioned reindex. Best-effort by design.
            try:
                await client.indices.put_mapping(
                    index=INDEX_ALIAS, properties=MAPPINGS["properties"]
                )
            except Exception as error:
                logger.warning("search mapping refresh skipped: %s", error)
            return True
        first = INDEX_PREFIX + "1"
        if not await client.indices.exists(index=first):
            await client.indices.create(
                index=first,
                settings=SETTINGS,
                mappings=MAPPINGS,
                aliases={INDEX_ALIAS: {}},
            )
        elif not await client.indices.exists_alias(name=INDEX_ALIAS):
            await client.indices.update_aliases(
                actions=[{"add": {"index": first, "alias": INDEX_ALIAS}}]
            )
        return True
    except Exception as error:
        logger.warning("search index bootstrap skipped (ES unavailable): %s", error)
        return False


async def dead_row_count():
    """Outbox rows given up on (poison rows), for /admin/search/status."""
    return await SearchOutbox.filter(
        processed_at__isnull=True, attempts__gte=MAX_ATTEMPTS
    ).count()


async def pending_row_count():
    """Outbox rows waiting to be drained, for /admin/search/status."""
    return await SearchOutbox.filter(
        processed_at__isnull=True, attempts__lt=MAX_ATTEMPTS
    ).count()


def _bulk_response_ok(response):
    """Whether a bulk response carries only ignorable errors (delete 404)."""
    if not response.get("errors"):
        return True, None
    for item in response.get("items", []):
        for op, detail in item.items():
            status = detail.get("status", 500)
            if status >= 300 and not (op == "delete" and status == 404):
                return False, str(detail.get("error", "bulk error"))[:500]
    return True, None


async def _bulk(client, operations):
    """
    Chunked bulk write through the alias. [operations] is a list of
    (action_line, source_or_None) pairs. Returns (ok, first_error).
    """
    for start in range(0, len(operations), BULK_CHUNK):
        end = start + BULK_CHUNK
        body = []
        for action, source in operations[start:end]:
            body.append(action)
            if source is not None:
                body.append(source)
        response = await client.bulk(operations=body)
        ok, error = _bulk_response_ok(response)
        if not ok:
            return False, error
    return True, None


async def drain_outbox():
    """
    One drain pass: claim -> coalesce -> rebuild docs from PG -> bulk write ->
    mark processed. Returns a small summary dict. Raises only on unexpected
    programming errors; ES failures are recorded on the claimed rows.
    """
    client = get_es()
    if client is None:
        return {"processed": 0, "reason": "search disabled"}
    # Self-heal: if every process booted before ES came up, the alias may not
    # exist yet — the 30s cron drain is the retry loop that creates it.
    await ensure_search_index()

    rows = (
        await SearchOutbox.filter(processed_at__isnull=True, attempts__lt=MAX_ATTEMPTS)
        .order_by("id")
        .limit(CLAIM_BATCH)
    )
    if not rows:
        return {"processed": 0}

    # Coalesce: rows are id-ordered, so the last op per song wins.
    latest_op = {}
    for row in rows:
        latest_op[row.song_id] = row.op
    upsert_ids = [sid for sid, op in latest_op.items() if op == "upsert"]
    delete_ids = [sid for sid, op in latest_op.items() if op == "delete"]

    songs = []
    for chunk in _chunks(upsert_ids):
        songs.extend(await Songs.filter(id__in=chunk))
    found = {song.id for song in songs}
    # An upsert whose row vanished since (e.g. deleted before the drain ran)
    # becomes a delete: the doc must not outlive the song.
    delete_ids.extend(sid for sid in upsert_ids if sid not in found)

    operations = []
    for doc in await build_song_docs(songs):
        operations.append(
            ({"index": {"_index": INDEX_ALIAS, "_id": str(doc["id"])}}, doc)
        )
    for sid in delete_ids:
        operations.append(({"delete": {"_index": INDEX_ALIAS, "_id": str(sid)}}, None))

    row_ids = [row.id for row in rows]
    try:
        ok, error = await _bulk(client, operations)
    except Exception as exc:
        ok, error = False, str(exc)[:500]

    if not ok:
        for chunk in _chunks(row_ids):
            claimed = await SearchOutbox.filter(id__in=chunk)
            for row in claimed:
                row.attempts += 1
                row.last_error = error
            if claimed:
                await SearchOutbox.bulk_update(
                    claimed, fields=["attempts", "last_error"]
                )
        logger.warning("search drain failed (%d rows kept): %s", len(row_ids), error)
        return {"processed": 0, "error": error}

    now = datetime.now(timezone.utc)
    for chunk in _chunks(row_ids):
        await SearchOutbox.filter(id__in=chunk).update(processed_at=now)
    return {
        "processed": len(row_ids),
        "upserted": len(operations) - len(delete_ids),
        "deleted": len(delete_ids),
    }
