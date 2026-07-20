"""
Zero-downtime full reindex (MOO-79, D2).

Builds the next versioned physical index (orp-tracks-vN+1) by streaming every
song out of PostgreSQL with keyset pagination, replays the outbox drift that
accumulated while streaming, atomically swaps the orp-tracks alias, and
deletes the old versions. ES is rebuildable from PG at all times; any future
mapping change = bump src/search/mapping.py + run this job.
"""
import logging
import time

from src.database.models import SearchOutbox, Songs
from src.search.docs import build_song_docs
from src.search.es import INDEX_ALIAS, INDEX_PREFIX, get_es
from src.search.mapping import MAPPINGS, SETTINGS

logger = logging.getLogger("orp.search")

STREAM_BATCH = 2000


async def _bulk_into(client, index, docs):
    """Bulk-index [docs] directly into the versioned index by song id."""
    body = []
    for doc in docs:
        body.append({"index": {"_index": index, "_id": str(doc["id"])}})
        body.append(doc)
    if body:
        response = await client.bulk(operations=body)
        if response.get("errors"):
            raise RuntimeError("bulk indexing into {} failed".format(index))


async def _existing_versions(client):
    """The existing orp-tracks-v* physical index names."""
    try:
        found = await client.indices.get(index=INDEX_PREFIX + "*")
    except Exception:
        return []
    return sorted(found.keys() if hasattr(found, "keys") else list(found))


_PREFIX_LEN = len(INDEX_PREFIX)


def _next_version(names):
    highest = 0
    for name in names:
        try:
            highest = max(highest, int(name[_PREFIX_LEN:]))
        except ValueError:
            continue
    return highest + 1


async def run_reindex(progress_cb=None):
    """
    The full reindex, steps 1-8 of D2. Returns the job result dict. Raises on
    ES being unreachable -- the caller (the search_reindex job task) records
    the failure on the jobs row.
    """
    client = get_es()
    if client is None:
        raise RuntimeError("Search engine is not configured")
    started = time.monotonic()

    # 1. High-water mark: outbox rows past this are the drift to replay.
    last_row = await SearchOutbox.all().order_by("-id").first()
    high_water = last_row.id if last_row else 0

    # 2. Create the next versioned index with transient bulk-friendly settings.
    old_names = await _existing_versions(client)
    new_index = INDEX_PREFIX + str(_next_version(old_names))
    settings = dict(SETTINGS)
    settings.update({"refresh_interval": "-1", "number_of_replicas": 0})
    settings.pop("auto_expand_replicas", None)
    await client.indices.create(index=new_index, settings=settings, mappings=MAPPINGS)

    # 3. Stream every song from PG via keyset pagination (never OFFSET).
    indexed = 0
    cursor = 0
    while True:
        batch = await Songs.filter(id__gt=cursor).order_by("id").limit(STREAM_BATCH)
        if not batch:
            break
        await _bulk_into(client, new_index, await build_song_docs(batch))
        indexed += len(batch)
        cursor = batch[-1].id
        if progress_cb is not None:
            await progress_cb(indexed)

    # 4. Restore serving settings and make the docs visible.
    await client.indices.put_settings(
        index=new_index,
        settings={"refresh_interval": "1s", "auto_expand_replicas": "0-1"},
    )
    await client.indices.refresh(index=new_index)

    # 5. Replay drift: songs touched while streaming, rebuilt from current PG
    # state (idempotent), directly into the new index.
    drift_ids = set(
        await SearchOutbox.filter(id__gt=high_water).values_list("song_id", flat=True)
    )
    if drift_ids:
        drift_songs = []
        drift_list = list(drift_ids)
        for start in range(0, len(drift_list), 1000):
            end = start + 1000
            chunk = drift_list[start:end]
            drift_songs.extend(await Songs.filter(id__in=chunk))
        await _bulk_into(client, new_index, await build_song_docs(drift_songs))
        alive = {song.id for song in drift_songs}
        gone = [sid for sid in drift_ids if sid not in alive]
        if gone:
            body = [{"delete": {"_index": new_index, "_id": str(sid)}} for sid in gone]
            await client.bulk(operations=body)
        await client.indices.refresh(index=new_index)

    # 6. Atomic alias swap in a single update_aliases call.
    actions = []
    if await client.indices.exists_alias(name=INDEX_ALIAS):
        actions.append({"remove": {"index": INDEX_PREFIX + "*", "alias": INDEX_ALIAS}})
    actions.append({"add": {"index": new_index, "alias": INDEX_ALIAS}})
    await client.indices.update_aliases(actions=actions)

    # 7. Drop the superseded physical indices.
    deleted_indices = [name for name in old_names if name != new_index]
    for name in deleted_indices:
        try:
            await client.indices.delete(index=name)
        except Exception as error:
            logger.warning("could not delete old index %s: %s", name, error)

    duration = round(time.monotonic() - started, 3)
    # 8. Audit (lazy import: audit pulls in models only, but keep the search
    # package import-light for the harnesses).
    from src.security.audit import audit_event

    await audit_event(
        "search.reindex.completed",
        target_type="search_index",
        target_id=new_index,
        detail={"indexed": indexed, "duration_seconds": duration},
    )
    return {
        "indexed": indexed,
        "deleted_indices": deleted_indices,
        "duration_seconds": duration,
        "index": new_index,
    }
