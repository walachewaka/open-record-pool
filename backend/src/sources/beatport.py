"""
Beatport-backed release source (MOO-80): a thin adapter over MOO-85's client
(src.enrichment.provider -- get_client()/mode_and_reason(), OAuth2 + Postgres
cache + rate limiting + host allowlist all live there, untouched here).

MOO-85 only ships track search/lookup (search_tracks/get_track) -- there is
no artist-id or artist-releases endpoint in the shipped client -- so this
source approximates search_artists/get_artist_releases by querying track
search and grouping results by release. external_id for a Beatport "artist"
is a hash of the normalized name (the shipped client exposes no numeric
Beatport artist id); it is stable and collision-free per name_norm.
"""
import hashlib
from datetime import datetime

from src.enrichment import provider
from src.sources.base import (
    ExternalArtist,
    ExternalRelease,
    ExternalTrack,
    ReleaseSource,
)


def _norm(name):
    return " ".join((name or "").strip().lower().split())


def artist_external_id(name):
    return hashlib.sha1(_norm(name).encode("utf-8")).hexdigest()[:20]


def _parse_release_date(value):
    if not value:
        return None
    if hasattr(value, "year"):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


class BeatportReleaseSource(ReleaseSource):
    name = "beatport"

    def configured(self):
        mode, _reason = provider.mode_and_reason()
        return mode != "disabled"

    async def search_artists(self, query):
        if not self.configured() or not query or not query.strip():
            return []
        client = provider.get_client()
        tracks = await client.search_tracks(query, per_page=25)
        q_norm = _norm(query)
        found = {}
        for track in tracks:
            for artist_name in track.get("artists") or []:
                if q_norm not in _norm(artist_name):
                    continue
                key = _norm(artist_name)
                if key not in found:
                    found[key] = ExternalArtist(
                        source="beatport",
                        external_id=artist_external_id(artist_name),
                        name=artist_name,
                        image_url=track.get("artwork_url"),
                    )
        return list(found.values())[:10]

    async def get_artist_releases(self, external_artist_id, since, artist_name=None):
        if not self.configured() or not artist_name:
            return []
        client = provider.get_client()
        tracks = await client.search_tracks(artist_name, per_page=50)
        target = _norm(artist_name)
        groups = {}
        for track in tracks:
            if not any(_norm(a) == target for a in track.get("artists") or []):
                continue
            release_date = _parse_release_date(track.get("release_date"))
            if release_date is None or release_date < since:
                continue
            key = str(
                track.get("release_id")
                or track.get("release_name")
                or track.get("name")
            )
            group = groups.setdefault(
                key,
                {
                    "title": track.get("release_name") or track.get("name"),
                    "release_date": release_date,
                    "label": track.get("label"),
                    "artwork_url": track.get("artwork_url"),
                    "tracks": [],
                },
            )
            group["tracks"].append(
                ExternalTrack(
                    title=track.get("name"),
                    mix=track.get("mix_name"),
                    external_id=str(track.get("beatport_track_id")),
                    duration_seconds=track.get("duration_seconds"),
                )
            )
        return [
            ExternalRelease(
                source="beatport",
                external_id=key,
                title=group["title"],
                release_date=group["release_date"],
                tracks=group["tracks"],
                label=group["label"],
                artwork_url=group["artwork_url"],
                source_url=None,
            )
            for key, group in groups.items()
        ]
