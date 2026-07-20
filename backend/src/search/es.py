"""
The single Elasticsearch plumbing module for the whole app (MOO-79).

Nothing else constructs an ES client: search indexing uses get_es() through
the "orp-tracks" alias, and telemetry (MOO-83) reuses get_es() +
events_index_name() for its own "orp-events-YYYY.MM" indices.

The elasticsearch package is imported lazily (like arq): it requires 3.8+
extras that the 3.7 harness venv does not carry, and harnesses inject an
in-memory stand-in via set_client_for_tests() instead.
"""
import os

# The read/write alias every application read and outbox write goes through.
# It always points at exactly one physical index (single-index alias, so doc
# writes through it are legal); reindexing builds the next orp-tracks-vN and
# swaps the alias atomically (see src/search/reindex.py).
INDEX_ALIAS = "orp-tracks"
INDEX_PREFIX = "orp-tracks-v"

# Telemetry index naming (created and mapped by MOO-83, reserved here).
EVENTS_INDEX_PATTERN = "orp-events-{yyyy}.{mm}"

_client = None
_client_override = None


def es_enabled():
    """Whether search indexing is configured (or a test client is injected)."""
    if _client_override is not None:
        return True
    return bool(os.environ.get("ELASTICSEARCH_URL"))


def get_es():
    """The lazy AsyncElasticsearch singleton, or None when disabled."""
    global _client
    if _client_override is not None:
        return _client_override
    if not es_enabled():
        return None
    if _client is None:
        from elasticsearch import AsyncElasticsearch

        _client = AsyncElasticsearch(
            os.environ["ELASTICSEARCH_URL"],
            request_timeout=5,
            retry_on_timeout=True,
            max_retries=2,
        )
    return _client


def set_client_for_tests(client):
    """Inject a stand-in client (e.g. FakeES); None removes the override."""
    global _client_override
    _client_override = client


def events_index_name(dt):
    """The telemetry index for a date: "orp-events-2026.07" (MOO-83)."""
    return "orp-events-{:04d}.{:02d}".format(dt.year, dt.month)


async def es_ping():
    """Cheap health probe: True iff ES answers within ~1s. Never raises."""
    client = get_es()
    if client is None:
        return False
    try:
        return bool(await client.options(request_timeout=1).ping())
    except Exception:
        return False


async def close_es():
    """Shutdown hook: close the real client if one was created."""
    global _client
    if _client is not None:
        try:
            await _client.close()
        except Exception:
            pass
        _client = None
