"""
The ES-backed instant-search endpoint (MOO-79).

/search reads Elasticsearch through the orp-tracks alias; any ES
error/timeout/disabled state falls through to the existing PG filter path
(same filters, keyset-paginated SQL) with degraded=true -- search never
5xxes because ES is down. The legacy /songs endpoint is untouched.
"""
import time
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

import src.crud.library as library_crud
import src.crud.songs as crud
from src.auth.jwthandler import get_current_user
from src.auth.permissions import require_permission
from src.database.models import Jobs, Songs
from src.schemas.search import SearchFacets, SearchItem, SearchResponse
from src.schemas.songs import song_to_schema
from src.schemas.users import UserOutSchema
from src.search import indexer
from src.search import query as search_query
from src.search.es import INDEX_ALIAS, es_enabled, get_es
from src.security.ratelimit import rate_limit
from src.telemetry import events

router = APIRouter()

SORTS = {"relevance", "added_at", "title", "artist", "bpm", "year"}
SOURCES = {"library", "upload"}

# ES doc fields copied verbatim into a search item (created_at comes from
# added_at, camelot_key/is_favorite are handled separately).
_ITEM_FIELDS = [
    "id",
    "title",
    "artist",
    "album",
    "genre",
    "label",
    "year",
    "track_number",
    "bpm",
    "musical_key",
    "duration_seconds",
    "bitrate_kbps",
    "file_size_bytes",
    "album_artist",
    "composer",
    "comment",
    "disc_number",
    "codec",
    "has_artwork",
]

# Degraded-mode SQL sort columns per API sort key (relevance has no SQL
# meaning; newest-first mirrors the ES tiebreaker).
_SQL_SORT_FIELDS = {
    "relevance": "created_at",
    "added_at": "created_at",
    "title": "title",
    "artist": "artist",
    "bpm": "bpm",
    "year": "year",
}


def _item_from_doc(source, favorite_ids):
    data = {field: source.get(field) for field in _ITEM_FIELDS}
    data["created_at"] = source.get("added_at")
    data["camelot_key"] = source.get("camelot_key")
    data["is_favorite"] = source.get("id") in favorite_ids
    return SearchItem(**data)


@router.get("/search", response_model=SearchResponse)
async def search(
    q: Optional[str] = Query(
        None, max_length=200, description="Free text (MOO-69 semantics)"
    ),
    genre: Optional[List[str]] = Query(None, description="Genre facet, repeatable"),
    year_min: Optional[int] = Query(None, ge=1900, le=2100),
    year_max: Optional[int] = Query(None, ge=1900, le=2100),
    bpm_min: Optional[float] = Query(None, ge=0, le=400),
    bpm_max: Optional[float] = Query(None, ge=0, le=400),
    key: Optional[str] = Query(
        None, max_length=20, description="Camelot ('8A') or raw ('Am')"
    ),
    bitrate_min: Optional[int] = Query(None, ge=0),
    source: Optional[str] = Query(None, description="library | upload"),
    sort: Optional[str] = Query(
        None, description="relevance | added_at | title | artist | bpm | year"
    ),
    order: Optional[str] = Query(None, description="asc | desc"),
    limit: int = Query(50, ge=1, le=100),
    cursor: Optional[str] = Query(None, description="Keyset cursor from next_cursor"),
    current_user: UserOutSchema = Depends(get_current_user),
) -> SearchResponse:
    """
    Instant search with combinable facets (MOO-79). Only published tracks are
    ever searchable. Facet counts exclude their own dimension's filter, so
    multi-select stays correct. Cursor pagination via ES search_after.
    """
    if sort is None:
        sort = "relevance" if q else "added_at"
    if sort not in SORTS:
        raise HTTPException(
            status_code=422,
            detail="sort must be one of: {}".format(", ".join(sorted(SORTS))),
        )
    if order is None:
        order = "desc" if sort in ("relevance", "added_at") else "asc"
    if order not in ("asc", "desc"):
        raise HTTPException(status_code=422, detail="order must be 'asc' or 'desc'")
    if source is not None and source not in SOURCES:
        raise HTTPException(
            status_code=422,
            detail="source must be one of: {}".format(", ".join(sorted(SOURCES))),
        )
    try:
        await rate_limit("search", str(current_user.id), limit=20, window_seconds=5)
    except HTTPException as error:
        raise HTTPException(
            status_code=429,
            detail="Too many search requests",
            headers=error.headers,
        )

    params = {
        "q": q,
        "genres": genre,
        "year_min": year_min,
        "year_max": year_max,
        "bpm_min": bpm_min,
        "bpm_max": bpm_max,
        "key": key,
        "bitrate_min": bitrate_min,
        "source": source,
        "sort": sort,
        "order": order,
        "limit": limit,
    }
    started = time.monotonic()

    if es_enabled():
        sort_length = len(search_query.sort_spec(sort, order))
        search_after = None
        if cursor:
            try:
                search_after = search_query.decode_cursor(cursor, sort_length)
            except ValueError:
                raise HTTPException(status_code=422, detail="Invalid cursor")
        params["search_after"] = search_after
        result = None
        try:
            result = await _es_search(params, current_user, started)
        except HTTPException:
            raise
        except Exception:
            pass  # degrade to SQL below
        if result is not None:
            _emit_search(current_user, params, result, started, "es")
            return result

    result = await _sql_search(params, cursor, current_user, started)
    _emit_search(current_user, params, result, started, "pg")
    return result


def _emit_search(current_user, params, response, started, engine):
    """One search.query telemetry event per /search call (MOO-83)."""
    filters = {
        key: params.get(key)
        for key in (
            "genres",
            "year_min",
            "year_max",
            "bpm_min",
            "bpm_max",
            "key",
            "bitrate_min",
            "source",
            "sort",
        )
    }
    events.search_query(
        current_user,
        query=params.get("q"),
        filters=filters,
        result_count=response.total,
        duration_ms=int((time.monotonic() - started) * 1000),
        engine=engine,
    )


async def _es_search(params, current_user, started):
    """The primary path: one ES request builds items, total, and facets."""
    body = search_query.build_search_body(params)
    client = get_es()
    response = await client.options(request_timeout=2).search(index=INDEX_ALIAS, **body)
    hits = (response.get("hits") or {}).get("hits") or []
    sources = [hit.get("_source") or {} for hit in hits]
    favorite_ids = await library_crud.favorite_song_ids(
        current_user.id, [doc.get("id") for doc in sources]
    )
    items = [_item_from_doc(doc, favorite_ids) for doc in sources]
    next_cursor = None
    if len(hits) == params["limit"] and hits[-1].get("sort"):
        next_cursor = search_query.encode_cursor(hits[-1]["sort"])
    total_info = (response.get("hits") or {}).get("total") or {}
    return SearchResponse(
        items=items,
        next_cursor=next_cursor,
        total=int(total_info.get("value") or 0),
        total_relation=total_info.get("relation") or "eq",
        took_ms=int(response.get("took") or 0),
        degraded=False,
        facets=SearchFacets(
            **search_query.parse_facets(response.get("aggregations") or {})
        ),
    )


async def _sql_search(params, cursor, current_user, started):
    """
    Degraded mode: the identical filters through the PG path, keyset-paginated
    (never OFFSET), genre facet from a cheap GROUP BY, everything else empty.
    """
    from datetime import datetime

    from tortoise.functions import Count

    from src.utils.pagination import keyset_filter

    query = crud.filter_songs(
        search=params["q"],
        bpm_min=params["bpm_min"],
        bpm_max=params["bpm_max"],
        key=params["key"],
        genres=params["genres"],
        year_min=params["year_min"],
        year_max=params["year_max"],
        bitrate_min=params["bitrate_min"],
        source=params["source"],
    )
    sort_field = _SQL_SORT_FIELDS[params["sort"]]
    order = params["order"]

    if cursor:
        try:
            values = search_query.decode_cursor(cursor, 2)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid cursor")
        raw_value, raw_id = values
        try:
            last_id = int(raw_id)
            if sort_field == "created_at":
                sort_value = datetime.fromisoformat(str(raw_value))
            elif sort_field in ("bpm", "year"):
                sort_value = float(raw_value)
            else:
                sort_value = str(raw_value)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="Invalid cursor")
        query = query.filter(keyset_filter(sort_field, order, sort_value, last_id))

    total = await query.count()
    prefix = "" if order == "asc" else "-"
    songs = await query.order_by(prefix + sort_field, prefix + "id").limit(
        params["limit"]
    )
    favorite_ids = await library_crud.favorite_song_ids(
        current_user.id, [song.id for song in songs]
    )
    items = [SearchItem(**song_to_schema(song, favorite_ids).dict()) for song in songs]
    next_cursor = None
    if len(songs) == params["limit"]:
        last = songs[-1]
        raw = getattr(last, sort_field)
        if sort_field == "created_at":
            raw = raw.isoformat() if raw else None
        next_cursor = search_query.encode_cursor([raw, last.id])

    # The genre facet stays useful offline: GROUP BY over the same filters
    # minus the genre dimension itself (multi-select parity with ES).
    genre_query = crud.filter_songs(
        search=params["q"],
        bpm_min=params["bpm_min"],
        bpm_max=params["bpm_max"],
        key=params["key"],
        year_min=params["year_min"],
        year_max=params["year_max"],
        bitrate_min=params["bitrate_min"],
        source=params["source"],
    )
    rows = (
        await genre_query.filter(genre__isnull=False)
        .annotate(count=Count("id"))
        .group_by("genre")
        .values("genre", "count")
    )
    genres = [
        {"value": row["genre"], "count": int(row["count"])}
        for row in sorted(rows, key=lambda r: -int(r["count"]))
        if row["genre"]
    ]
    return SearchResponse(
        items=items,
        next_cursor=next_cursor,
        total=total,
        total_relation="eq",
        took_ms=int((time.monotonic() - started) * 1000),
        degraded=True,
        facets=SearchFacets(genres=genres, bpm=None),
    )


@router.get("/admin/search/status")
async def search_status(
    current_user: UserOutSchema = Depends(require_permission("site_settings")),
):
    """
    The search engine's health card (MOO-79): reachability, the physical
    index behind the alias, doc count vs songs in PG (the "rebuildable"
    check), outbox backlog and dead rows, and the latest reindex job.
    """
    status = {
        "enabled": es_enabled(),
        "reachable": False,
        "alias": INDEX_ALIAS,
        "index": None,
        "doc_count": None,
        "songs_in_db": await Songs.all().count(),
        "outbox_pending": await indexer.pending_row_count(),
        "outbox_dead": await indexer.dead_row_count(),
        "last_reindex_job_id": None,
    }
    last_job = await Jobs.filter(kind="search_reindex").order_by("-id").first()
    if last_job is not None:
        status["last_reindex_job_id"] = last_job.id
    client = get_es()
    if client is None:
        return status
    try:
        aliases = await client.indices.get_alias(name=INDEX_ALIAS)
        names = sorted(aliases.keys() if hasattr(aliases, "keys") else [])
        status["index"] = names[0] if names else None
        counted = await client.options(request_timeout=2).count(index=INDEX_ALIAS)
        status["doc_count"] = int(counted.get("count") or 0)
        status["reachable"] = True
    except Exception:
        status["reachable"] = False
        status["index"] = None
        status["doc_count"] = None
    return status
