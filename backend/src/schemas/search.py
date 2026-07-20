"""
API schemas for the ES-backed /search endpoint (MOO-79).
"""
from typing import List, Optional

from pydantic import BaseModel

from src.schemas.songs import SongOutSchema


class SearchItem(SongOutSchema):
    """
    One search hit: exactly the member song shape (SongOutSchema, which since
    MOO-79 carries the extended ID3 fields), built from the ES _source with
    no per-hit PG round trip.
    """


class FacetValue(BaseModel):
    """One bucket of a terms facet: a value and how many tracks match it."""

    value: str
    count: int


class IntFacetValue(BaseModel):
    """One bucket of an integer terms facet (years, bitrates)."""

    value: int
    count: int


class BpmBucket(BaseModel):
    """One histogram bucket of the BPM facet."""

    from_: float
    to: float
    count: int

    class Config:
        fields = {"from_": "from"}
        allow_population_by_field_name = True


class BpmFacet(BaseModel):
    """The BPM range facet: bounds + histogram buckets (interval 10)."""

    min: Optional[float] = None
    max: Optional[float] = None
    buckets: List[BpmBucket] = []


class SearchFacets(BaseModel):
    """
    The combinable facets of a result set. Counts are computed with each
    dimension's own filter excluded, so multi-select stays correct. Degraded
    (SQL fallback) responses only fill genres; bpm is null then.
    """

    genres: List[FacetValue] = []
    years: List[IntFacetValue] = []
    bpm: Optional[BpmFacet] = None
    keys: List[FacetValue] = []
    bitrates: List[IntFacetValue] = []
    sources: List[FacetValue] = []


class SearchResponse(BaseModel):
    """
    One page of instant search results. total_relation is "gte" when the
    count was capped at track_total_hits (10000); degraded is true when ES
    was unreachable and the SQL fallback served the page.
    """

    items: List[SearchItem]
    next_cursor: Optional[str] = None
    total: int
    total_relation: str = "eq"
    took_ms: int = 0
    degraded: bool = False
    facets: SearchFacets
