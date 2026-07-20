"""
Deterministic mock release source (MOO-80): gated by RELEASE_SOURCE_MOCK=true
(default false). Lets the whole follow/poll/match/grab pipeline be exercised
by the harness and in dev without any Beatport credentials. Every row it
produces carries source="mock", so it never collides with real Beatport data
even if both were somehow enabled at once.
"""
import hashlib
import os
from datetime import date, timedelta

from src.sources.base import (
    ExternalArtist,
    ExternalRelease,
    ExternalTrack,
    ReleaseSource,
)


def mock_enabled():
    return os.environ.get("RELEASE_SOURCE_MOCK", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _norm(name):
    return " ".join((name or "").strip().lower().split())


def _slug(name):
    return "m-" + hashlib.sha1(_norm(name).encode("utf-8")).hexdigest()[:16]


class MockReleaseSource(ReleaseSource):
    name = "mock"

    def configured(self):
        return True

    async def search_artists(self, query):
        if not query or not query.strip():
            return []
        return [ExternalArtist(source="mock", external_id=_slug(query), name=query)]

    async def get_artist_releases(self, external_artist_id, since, artist_name=None):
        today = date.today()
        specs = (
            (today - timedelta(days=1), "yesterday"),
            (today + timedelta(days=7), "plus7"),
            (today + timedelta(days=30), "plus30"),
        )
        releases = []
        for release_date, tag in specs:
            if release_date < since:
                continue
            release_id = "{}-{}".format(external_artist_id, tag)
            tracks = [
                ExternalTrack(
                    title="Mock Track {} A".format(tag),
                    mix="Original Mix",
                    external_id="{}-a".format(release_id),
                    duration_seconds=360.0,
                ),
                ExternalTrack(
                    title="Mock Track {} B".format(tag),
                    mix="Extended Mix",
                    external_id="{}-b".format(release_id),
                    duration_seconds=420.0,
                ),
            ]
            releases.append(
                ExternalRelease(
                    source="mock",
                    external_id=release_id,
                    title="Mock Release {}".format(tag),
                    release_date=release_date,
                    tracks=tracks,
                    label="Mock Label",
                    artwork_url=None,
                    source_url=None,
                )
            )
        return releases
