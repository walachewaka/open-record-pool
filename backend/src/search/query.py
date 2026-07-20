"""
The /search query builder (MOO-79): pure functions from typed, validated
params to the ES request body, and back from the aggregations to the facets
object.

SECURITY (SECURITY.md items 3 and 9): user input is only ever placed as a
VALUE inside DSL dicts assembled here -- never string-interpolated into query
JSON, never a key, never a field name. query_string and script queries are
forbidden in this codebase.
"""
import base64
import json

from src.utils.camelot import to_camelot

# Fields the free-text search-as-you-type query runs over (bool_prefix over
# the .sayt subfields matches per-token prefixes while typing).
SAYT_FIELDS = [
    "title.sayt",
    "title.sayt._2gram",
    "title.sayt._3gram",
    "artist.sayt",
    "artist.sayt._2gram",
    "artist.sayt._3gram",
    "album.sayt",
    "album_artist.sayt",
    "composer.sayt",
    "label.sayt",
    "genre.sayt",
    "comment",
]

# API sort key -> ES sort field. Text sorts use the case-folded keyword
# subfield; nullable columns sort missing-last.
SORT_FIELDS = {
    "added_at": "added_at",
    "title": "title.norm",
    "artist": "artist.norm",
    "bpm": "bpm",
    "year": "year",
}
SORTS = {"relevance"} | set(SORT_FIELDS)

FACET_TERMS_SIZES = {
    "genres": ("genre", 50),
    "keys": ("camelot_key", 24),
    "bitrates": ("bitrate_kbps", 10),
    "sources": ("source", 4),
}

BPM_HISTOGRAM_INTERVAL = 10


def encode_cursor(sort_values):
    """base64url (no padding) of the JSON list of a hit's sort values."""
    raw = json.dumps(list(sort_values), separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(token, expected_length):
    """
    The search_after list for a cursor token. Tampered/undecodable/mismatched
    tokens raise ValueError (the route turns it into a 422, never a 500).
    """
    try:
        padded = token + "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        values = json.loads(raw.decode("utf-8"))
    except Exception:
        raise ValueError("Invalid cursor")
    if not isinstance(values, list) or len(values) != expected_length:
        raise ValueError("Invalid cursor")
    for value in values:
        if value is not None and not isinstance(value, (str, int, float, bool)):
            raise ValueError("Invalid cursor")
    return values


def _text_should(q):
    """The free-text should block: sayt + TXXX + MOO-69 key/BPM semantics."""
    should = [
        {
            "multi_match": {
                "query": q,
                "type": "bool_prefix",
                "fields": list(SAYT_FIELDS),
            }
        },
        {"match": {"txxx": q}},
    ]
    camelot = to_camelot(q)
    if camelot:
        should.append({"term": {"camelot_key": camelot}})
    try:
        bpm_value = float(q)
    except ValueError:
        bpm_value = None
    if bpm_value is not None:
        should.append(
            {"range": {"bpm": {"gte": bpm_value - 0.5, "lt": bpm_value + 0.5}}}
        )
    return should


def facet_filter_clauses(params):
    """
    One DSL filter clause per active facet dimension, keyed by dimension.
    Values go through .norm (lowercase+asciifolding) fields where the PG
    behaviour is case-insensitive (__iexact parity).
    """
    clauses = {}
    genres = params.get("genres")
    if genres:
        clauses["genre"] = {
            "terms": {"genre.norm": [str(g).strip().lower() for g in genres]}
        }
    year_range = {}
    if params.get("year_min") is not None:
        year_range["gte"] = params["year_min"]
    if params.get("year_max") is not None:
        year_range["lte"] = params["year_max"]
    if year_range:
        clauses["year"] = {"range": {"year": year_range}}
    bpm_range = {}
    if params.get("bpm_min") is not None:
        bpm_range["gte"] = params["bpm_min"]
    if params.get("bpm_max") is not None:
        bpm_range["lte"] = params["bpm_max"]
    if bpm_range:
        clauses["bpm"] = {"range": {"bpm": bpm_range}}
    key = params.get("key")
    if key:
        camelot = to_camelot(key)
        if camelot:
            clauses["key"] = {"term": {"camelot_key": camelot}}
        else:
            clauses["key"] = {"term": {"musical_key.norm": key.strip().lower()}}
    if params.get("bitrate_min") is not None:
        clauses["bitrate"] = {"range": {"bitrate_kbps": {"gte": params["bitrate_min"]}}}
    if params.get("source"):
        clauses["source"] = {"term": {"source": params["source"]}}
    return clauses


def _facet_aggs(clauses):
    """
    The facet aggregations. Each dimension is wrapped in a filter agg holding
    every OTHER dimension's filter, so multi-select counts stay correct
    (checking "Techno" still shows what the other genres would return).
    """
    facet_dimension = {
        "genres": "genre",
        "years": "year",
        "bpm": "bpm",
        "keys": "key",
        "bitrates": "bitrate",
        "sources": "source",
    }
    aggs = {}
    for name, dimension in facet_dimension.items():
        others = [clause for dim, clause in clauses.items() if dim != dimension]
        if name == "bpm":
            inner = {
                "hist": {
                    "histogram": {"field": "bpm", "interval": BPM_HISTOGRAM_INTERVAL}
                },
                "stats": {"stats": {"field": "bpm"}},
            }
        elif name == "years":
            inner = {
                name: {
                    "terms": {"field": "year", "size": 60, "order": {"_key": "desc"}}
                }
            }
        else:
            field, size = FACET_TERMS_SIZES[name]
            inner = {name: {"terms": {"field": field, "size": size}}}
        aggs[name] = {"filter": {"bool": {"filter": others}}, "aggs": inner}
    return aggs


def sort_spec(sort, order):
    """The ES sort array for an API sort key (relevance needs a live query)."""
    if sort == "relevance":
        return [
            {"_score": {"order": "desc"}},
            {"added_at": {"order": "desc"}},
            {"id": {"order": "desc"}},
        ]
    field = SORT_FIELDS[sort]
    primary = {field: {"order": order}}
    if sort in ("title", "artist", "bpm", "year"):
        primary[field]["missing"] = "_last"
    return [primary, {"id": {"order": order}}]


def build_search_body(params):
    """
    The full search request body from validated params: query + post_filter
    facet filters + excluded-own-dimension aggs + sort + search_after.
    """
    must_filter = [{"term": {"status": "published"}}]
    bool_query = {"filter": must_filter}
    # Only canonical versions are user-facing (MOO-90). must_not (instead of
    # a positive term) so docs indexed before the field existed still match.
    bool_query["must_not"] = [
        {"terms": {"version_status": ["superseded", "quarantined", "pending_review"]}}
    ]
    q = (params.get("q") or "").strip()
    if q:
        bool_query["should"] = _text_should(q)
        bool_query["minimum_should_match"] = 1

    clauses = facet_filter_clauses(params)
    body = {
        "query": {"bool": bool_query},
        "aggs": _facet_aggs(clauses),
        "sort": sort_spec(params["sort"], params["order"]),
        "size": params["limit"],
        "track_total_hits": 10000,
    }
    if clauses:
        body["post_filter"] = {"bool": {"filter": list(clauses.values())}}
    if params.get("search_after"):
        body["search_after"] = params["search_after"]
    return body


def _buckets(aggregations, name):
    outer = aggregations.get(name) or {}
    inner = outer.get(name) or {}
    return inner.get("buckets") or []


def parse_facets(aggregations):
    """Shape the raw aggregations into the response facets object."""
    bpm_outer = aggregations.get("bpm") or {}
    stats = bpm_outer.get("stats") or {}
    hist = bpm_outer.get("hist") or {}
    bpm_buckets = [
        {
            "from": bucket["key"],
            "to": bucket["key"] + BPM_HISTOGRAM_INTERVAL,
            "count": bucket["doc_count"],
        }
        for bucket in hist.get("buckets") or []
        if bucket.get("doc_count")
    ]
    return {
        "genres": [
            {"value": b["key"], "count": b["doc_count"]}
            for b in _buckets(aggregations, "genres")
        ],
        "years": [
            {"value": int(b["key"]), "count": b["doc_count"]}
            for b in _buckets(aggregations, "years")
        ],
        "bpm": {
            "min": stats.get("min"),
            "max": stats.get("max"),
            "buckets": bpm_buckets,
        },
        "keys": [
            {"value": b["key"], "count": b["doc_count"]}
            for b in _buckets(aggregations, "keys")
        ],
        "bitrates": [
            {"value": int(b["key"]), "count": b["doc_count"]}
            for b in _buckets(aggregations, "bitrates")
        ],
        "sources": [
            {"value": b["key"], "count": b["doc_count"]}
            for b in _buckets(aggregations, "sources")
        ],
    }
