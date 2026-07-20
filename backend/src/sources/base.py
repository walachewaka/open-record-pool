"""
Release-source abstraction (MOO-80): a small interface any external release
catalog (Beatport today, MusicBrainz/others later) implements so the poller
and the API never care which source answered. Adding a new source is one
file + one src/sources/registry.py line -- no other code changes.
"""


class ExternalArtist:
    def __init__(self, source, external_id, name, image_url=None):
        self.source = source
        self.external_id = external_id
        self.name = name
        self.image_url = image_url


class ExternalTrack:
    def __init__(self, title, mix=None, external_id=None, duration_seconds=None):
        self.title = title
        self.mix = mix
        self.external_id = external_id
        self.duration_seconds = duration_seconds


class ExternalRelease:
    def __init__(
        self,
        source,
        external_id,
        title,
        release_date,
        tracks,
        label=None,
        artwork_url=None,
        source_url=None,
    ):
        self.source = source
        self.external_id = external_id
        self.title = title
        self.release_date = release_date
        self.tracks = tracks
        self.label = label
        self.artwork_url = artwork_url
        self.source_url = source_url


class ReleaseSource:
    name = "base"

    def configured(self):
        raise NotImplementedError

    async def search_artists(self, query):
        raise NotImplementedError

    async def get_artist_releases(self, external_artist_id, since, artist_name=None):
        """Must include future-dated (upcoming) releases, not just past ones."""
        raise NotImplementedError
