"""
Deterministic mock Beatport client (MOO-85), used when BEATPORT_MOCK=true.

Same call surface as BeatportClient (search_tracks/get_track), zero network,
zero credentials -- every enrichment code path (search, scoring, review,
apply, un-apply, rescan survival) is exercisable end-to-end without a
Beatport partner account. Fixtures are hand-picked to exercise every match
outcome the scoring module can produce:

- FIXTURE_EXACT: a clean, tight match on every signal -> auto-apply.
- FIXTURE_DURATION_MISMATCH: same title/artist/bpm/key but a much longer
  edit (Extended Mix vs whatever the local tag says) -> needs_review, never
  auto-applied.
- FIXTURE_DECOY: shares the bare title but wrong artist/bpm/key/duration ->
  no_match.
- FIXTURE_RICH: exercises every optional field (catalog number, ISRC,
  remixers, subgenre, artwork) for the review-drawer UI to render.
"""
from src.enrichment import normalize as norm

FIXTURE_EXACT = {
    "beatport_track_id": 2000001,
    "name": "Strobe",
    "mix_name": "Original Mix",
    "artists": ["Deadmau5"],
    "remixers": [],
    "genre": "Progressive House",
    "subgenre": "Melodic House",
    "label": "mau5trap",
    "catalog_number": "MAU5008",
    "release_name": "For Lack of a Better Name",
    "release_id": 900001,
    "release_date": "2009-05-25",
    "isrc": "USUM70917980",
    "bpm": 128.0,
    "key": "Am",
    "duration_seconds": 634.0,
    "artwork_url": "https://geo-media.beatport.com/image_size/500x500/1000001.jpg",
}

FIXTURE_DURATION_MISMATCH = {
    "beatport_track_id": 2000002,
    "name": "Strobe",
    "mix_name": "Extended Mix",
    "artists": ["Deadmau5"],
    "remixers": [],
    "genre": "Progressive House",
    "subgenre": "Melodic House",
    "label": "mau5trap",
    "catalog_number": "MAU5008X",
    "release_name": "For Lack of a Better Name (Extended Versions)",
    "release_id": 900002,
    "release_date": "2009-05-25",
    "isrc": "USUM70917981",
    "bpm": 128.0,
    "key": "Am",
    "duration_seconds": 900.0,
    "artwork_url": "https://geo-media.beatport.com/image_size/500x500/1000002.jpg",
}

FIXTURE_DECOY = {
    "beatport_track_id": 2000003,
    "name": "Strobe",
    "mix_name": "Original Mix",
    "artists": ["Not Deadmau5 At All"],
    "remixers": [],
    "genre": "Tech House",
    "subgenre": None,
    "label": "Some Other Label",
    "catalog_number": "SOL001",
    "release_name": "A Totally Different Release",
    "release_id": 900003,
    "release_date": "2015-01-01",
    "isrc": "GBABC1500001",
    "bpm": 140.0,
    "key": "Fm",
    "duration_seconds": 200.0,
    "artwork_url": "https://geo-media.beatport.com/image_size/500x500/1000003.jpg",
}

FIXTURE_RICH = {
    "beatport_track_id": 2000004,
    "name": "Midnight Requiem",
    "mix_name": "Club Mix",
    "artists": ["Nova Horizon", "Kilo Sierra"],
    "remixers": ["DJ Aurora"],
    "genre": "Melodic Techno",
    "subgenre": "Melodic House & Techno",
    "label": "Anjunadeep",
    "catalog_number": "ANJDEE512",
    "release_name": "Midnight Requiem EP",
    "release_id": 900004,
    "release_date": "2023-11-03",
    "isrc": "GBUM72300123",
    "bpm": 122.0,
    "key": "F#m",
    "duration_seconds": 372.0,
    "artwork_url": "https://geo-media.beatport.com/image_size/500x500/1000004.jpg",
}

FIXTURES = [FIXTURE_EXACT, FIXTURE_DURATION_MISMATCH, FIXTURE_DECOY, FIXTURE_RICH]
_BY_ID = {track["beatport_track_id"]: track for track in FIXTURES}


def _tokens(track):
    words = set(norm.normalize(track.get("name") or "").split())
    for artist in track.get("artists") or []:
        words.update(norm.normalize(artist).split())
    return words


class MockBeatportClient:
    """Drop-in replacement for BeatportClient. Deterministic, no network."""

    async def search_tracks(self, query, per_page=25):
        query_tokens = set(norm.normalize(query).split())
        if not query_tokens:
            return list(FIXTURES)[:per_page]
        matches = [track for track in FIXTURES if _tokens(track) & query_tokens]
        return (matches or list(FIXTURES))[:per_page]

    async def get_track(self, track_id):
        try:
            return _BY_ID.get(int(track_id))
        except (TypeError, ValueError):
            return None
