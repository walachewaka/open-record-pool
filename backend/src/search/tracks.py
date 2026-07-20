"""
Track-matching helpers over the search index for downstream stages (MOO-79).

Frozen contracts:
- MOO-90 dedup / MOO-81 request dedup call find_matches(); a checksum gives
  an exact match, otherwise artist/title (.norm, case/accent-insensitive)
  with an optional duration window. Empty list when ES is disabled -- the
  callers fall back to the PG dedup_key.
- MOO-80 artist-follow matches on artist.norm via match_artist().
"""
from src.search.es import INDEX_ALIAS, get_es

DURATION_WINDOW_SECONDS = 2.0


async def _search(query, limit):
    client = get_es()
    if client is None:
        return []
    try:
        response = await client.options(request_timeout=2).search(
            index=INDEX_ALIAS, query=query, size=limit
        )
    except Exception:
        return []
    hits = (response.get("hits") or {}).get("hits") or []
    results = []
    for hit in hits:
        doc = dict(hit.get("_source") or {})
        doc["_score"] = hit.get("_score")
        results.append(doc)
    return results


async def find_matches(
    artist, title, duration_seconds=None, checksum_sha256=None, limit=5
):
    """
    Candidate library matches for an incoming track, as raw doc dicts with
    _score. Checksum given -> exact content match; else normalized
    artist/title terms plus an optional duration window.
    """
    if checksum_sha256:
        return await _search({"term": {"checksum_sha256": checksum_sha256}}, limit)
    must = []
    if artist:
        must.append({"term": {"artist.norm": artist.strip().lower()}})
    if title:
        must.append({"term": {"title.norm": title.strip().lower()}})
    if not must:
        return []
    if duration_seconds is not None:
        must.append(
            {
                "range": {
                    "duration_seconds": {
                        "gte": duration_seconds - DURATION_WINDOW_SECONDS,
                        "lte": duration_seconds + DURATION_WINDOW_SECONDS,
                    }
                }
            }
        )
    return await _search({"bool": {"must": must}}, limit)


async def match_artist(name, limit=50):
    """Every doc whose artist case/accent-insensitively equals [name]."""
    if not name or not name.strip():
        return []
    return await _search({"term": {"artist.norm": name.strip().lower()}}, limit)
