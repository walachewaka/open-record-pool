"""
API schemas for songs.
"""
from typing import List, Optional

from pydantic import BaseModel
from tortoise.contrib.pydantic import pydantic_model_creator

from src.database.models import Songs
from src.utils.camelot import to_camelot


# What the API exposes about a song. The server-side file path, the internal
# bookkeeping fields, and the reverse relations (crate membership, favorites,
# play events, downloads -- MOO-65) stay private.
_SongOutBase = pydantic_model_creator(
    Songs,
    name="SongOutBase",
    exclude=[
        "file_path",
        "checksum_md5",
        "checksum_sha256",
        "file_mtime",
        "dedup_key",
        "txxx_frames",
        "modified_at",
        # Admin-only / internal fields kept out of the member song shape
        # (MOO-71): members only ever see published tracks, so status/source
        # carry no member-facing meaning, and the uploader stays private.
        "status",
        "source",
        "uploaded_by",
        "crate_tracks",
        "favorites",
        "play_events",
        "downloads",
        "download_requests",
        "uploaded_songs",
        # The analyzer's reverse relation (MOO-87): its facts are served by
        # GET /songs/{id}/analysis, never inlined into the song shape.
        "analysis",
        # Recording dedup internals (MOO-90): members only ever see canonical
        # versions, so the version bookkeeping stays out of the member shape
        # (the detail route exposes recording_id/canonical_song_id itself).
        "recording",
        "version_status",
        "quality_breakdown",
        "artist_norm",
        "title_norm",
        "dup_as_a",
        "dup_as_b",
        "dup_suggested",
        "fp_ngrams",
        # Song requests that reference this song (MOO-81): served by their own
        # routes, never nested onto the song shape.
        "song_requests_duplicate",
        "song_requests_possible_duplicate",
        "song_requests_fulfilled",
        # Beatport enrichment (MOO-85): the row itself is served by its own
        # routes (GET /admin/enrichment/songs/{id}), never nested onto the
        # song shape -- and never prefetched here, so leaving the reverse
        # relation in would raise tortoise.exceptions.NoValuesFetched on
        # every /songs serialization. beatport_track_id/field_locks are
        # admin/enrichment bookkeeping, not member-facing (the admin content
        # dict and the enrichment schemas expose them where needed).
        "enrichments",
        "beatport_track_id",
        "field_locks",
        # Metadata editor (MOO-82): the art lives behind an authenticated route
        # (GET /songs/{id}/artwork) -- never hand out the server-side path. The
        # history/proposal reverse relations are served by their own routes and
        # are not prefetched, so nesting them would raise NoValuesFetched.
        "artwork_path",
        "tag_revisions",
        "tag_proposals",
    ],
)


class SongOutSchema(_SongOutBase):  # type: ignore[misc, valid-type]
    """
    A song as listed by the API (MOO-65): the tag fields plus the derived
    Camelot key (best-effort, null when unknown) and whether the current
    user favorited it. Since MOO-87 the bpm / musical_key / camelot_key
    fields carry the COALESCEd tag-then-detected values (D5: the curated
    tag always wins, analysis fills gaps); bpm_detected / key_detected /
    waveform_ready expose the analyzer's own values for provenance.
    """

    camelot_key: Optional[str] = None
    is_favorite: bool = False


def song_to_schema(song, favorite_ids=None):
    """
    Builds the API schema for a song model instance: coalesces bpm and
    musical_key with the analyzer-detected fallbacks (MOO-87 D5), derives
    camelot_key from the coalesced key, and marks is_favorite against a set
    of the user's favorite song ids.
    """
    data = _SongOutBase.from_orm(song).dict()
    if data.get("bpm") is None:
        data["bpm"] = song.bpm_detected
    if not data.get("musical_key"):
        data["musical_key"] = song.key_detected
    data["camelot_key"] = to_camelot(data["musical_key"])
    data["is_favorite"] = bool(favorite_ids) and song.id in favorite_ids
    return SongOutSchema(**data)


class SongListResponse(BaseModel):
    """
    One page of the song library (#6, #10). Offset mode always sets total;
    cursor mode (MOO-77) sets total to null and carries next_cursor instead
    (COUNT(*) over a millions-row table is banned).
    """

    items: List[SongOutSchema]
    total: Optional[int] = None
    page: int
    page_size: int
    next_cursor: Optional[str] = None


class GenreStat(BaseModel):
    """
    One genre present in the library with its track count (MOO-69). Feeds
    the genre tiles of the Genres view.
    """

    genre: str
    track_count: int


class SongVersion(BaseModel):
    """
    One downloadable version/format of a song (MOO-65). The library holds
    single MP3 files today, so there is exactly one "Original / MP3" entry;
    the shape leaves room for future versions (Clean/Dirty/...) and WAV.
    """

    id: str
    version: str
    format: str
    bitrate_kbps: Optional[int] = None
    file_size_bytes: Optional[int] = None
    stream_url: str
    download_url: str


class SongDetailResponse(SongOutSchema):
    """
    The release-detail view of a song (MOO-65): the listing fields plus
    aggregate counts, tag chips, and the versions/formats list. The
    mismatch flags (MOO-87 D5) surface when the file's tags disagree with
    the audio analysis; null until pass 2 has run (or when either side of
    the comparison is missing).
    """

    download_count: int = 0
    play_count: int = 0
    tags: List[str] = []
    versions: List[SongVersion] = []
    bpm_mismatch: Optional[bool] = None
    key_mismatch: Optional[bool] = None
    # Recording dedup (MOO-90): the song's recording and its canonical
    # version (self when this song IS the canonical), so clients can
    # redirect from a superseded id. Null before any dedup ran.
    recording_id: Optional[int] = None
    canonical_song_id: Optional[int] = None


class ExtractionResult(BaseModel):
    """
    Summary of one extraction run (#5, #9).
    """

    files_parsed: int
    duplicates_skipped: int
    songs_created: int
    songs_updated: int
    songs_deleted: int
    songs_total: int
