"""
The explicit settings + mappings of the orp-tracks index (MOO-79).

Principles (millions-of-docs safe):
- dynamic: "strict" and every field explicitly mapped -- no dynamic string
  explosion; arbitrary TXXX frame names go into a single `flattened` field.
- Text fields carry a .sayt search_as_you_type subfield (gives ._2gram /
  ._3gram / ._index_prefix for instant search), a .raw keyword, and a .norm
  lowercase+asciifolding keyword mirroring the PG __iexact semantics.
- Facet keywords keep original case at the top level for display, with .norm
  for case-insensitive filtering.
- 3 primary shards; replicas auto-expand 0-1 so the single-node dev stack
  stays green and a second node gets a replica with zero config.

Any mapping change = bump this file + run the reindex job (versioned indices
behind the alias are the ES migration story; aerich never touches ES).
"""

SETTINGS = {
    "number_of_shards": 3,
    "number_of_replicas": 0,
    "auto_expand_replicas": "0-1",
    "analysis": {
        "normalizer": {
            "orp_norm": {"type": "custom", "filter": ["lowercase", "asciifolding"]}
        },
        "analyzer": {
            "orp_folding": {
                "type": "custom",
                "tokenizer": "standard",
                "filter": ["lowercase", "asciifolding"],
            }
        },
    },
}


def _text():
    """A searchable text field: folded text + .sayt / .raw / .norm subfields."""
    return {
        "type": "text",
        "analyzer": "orp_folding",
        "fields": {
            "sayt": {"type": "search_as_you_type", "analyzer": "orp_folding"},
            "raw": {"type": "keyword", "ignore_above": 512},
            "norm": {"type": "keyword", "normalizer": "orp_norm", "ignore_above": 512},
        },
    }


MAPPINGS = {
    "dynamic": "strict",
    "properties": {
        "id": {"type": "integer"},
        "title": _text(),
        "artist": _text(),
        "album": _text(),
        "album_artist": _text(),
        "composer": _text(),
        "label": _text(),
        "genre": {
            "type": "keyword",
            "ignore_above": 128,
            "fields": {
                "norm": {
                    "type": "keyword",
                    "normalizer": "orp_norm",
                    "ignore_above": 128,
                },
                "text": {"type": "text", "analyzer": "orp_folding"},
                "sayt": {"type": "search_as_you_type", "analyzer": "orp_folding"},
            },
        },
        "comment": {"type": "text", "analyzer": "orp_folding"},
        "musical_key": {
            "type": "keyword",
            "ignore_above": 20,
            "fields": {
                "norm": {
                    "type": "keyword",
                    "normalizer": "orp_norm",
                    "ignore_above": 20,
                }
            },
        },
        "camelot_key": {"type": "keyword"},
        "year": {"type": "integer"},
        "track_number": {"type": "integer"},
        "disc_number": {"type": "integer"},
        "bpm": {"type": "float"},
        # Analyzer provenance (MOO-87): bpm/musical_key above are indexed
        # COALESCEd (tag wins, detected fills); these carry the detected
        # values verbatim plus the EBU R128 integrated loudness.
        "bpm_detected": {"type": "float"},
        "key_detected": {
            "type": "keyword",
            "ignore_above": 20,
            "fields": {
                "norm": {
                    "type": "keyword",
                    "normalizer": "orp_norm",
                    "ignore_above": 20,
                }
            },
        },
        "loudness_lufs": {"type": "float"},
        "duration_seconds": {"type": "float"},
        "bitrate_kbps": {"type": "integer"},
        "file_size_bytes": {"type": "long"},
        "codec": {"type": "keyword"},
        "has_artwork": {"type": "boolean"},
        "txxx": {"type": "flattened", "depth_limit": 2, "ignore_above": 512},
        "status": {"type": "keyword"},
        "source": {"type": "keyword"},
        # Recording dedup (MOO-90): only canonical versions are user-facing.
        "version_status": {"type": "keyword"},
        "recording_id": {"type": "integer"},
        "checksum_sha256": {"type": "keyword"},
        "uploaded_by_id": {"type": "integer"},
        "added_at": {"type": "date"},
        "play_count": {"type": "integer"},
        "download_count": {"type": "integer"},
    },
}
