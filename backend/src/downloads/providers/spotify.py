"""
Spotify adapter via spotDL (MOO-78).

spotDL never touches Spotify DRM audio: it resolves Spotify *metadata* with its
built-in anonymous client and downloads matching audio from YouTube Music. No
Spotify account, no OAuth, no DRM circumvention. Optional SPOTIFY_CLIENT_ID +
SPOTIFY_CLIENT_SECRET (a free developer app) only avoid shared-key rate limits.
"""
import json
import os

from src.downloads.providers.base import (
    ProviderAdapter,
    raise_for_tool,
    run_tool,
    single_audio_file,
    source_metadata,
)

SPOTDL_BIN = os.environ.get("SPOTDL_BIN", "/opt/tools/spotdl/bin/spotdl")
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "")


def _client_args():
    if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
        return [
            "--client-id",
            SPOTIFY_CLIENT_ID,
            "--client-secret",
            SPOTIFY_CLIENT_SECRET,
        ]
    return []


def _parse_meta(entry, source_url):
    return source_metadata(
        title=entry.get("name"),
        artist=(entry.get("artists") or [entry.get("artist")])[0]
        if entry.get("artists") or entry.get("artist")
        else None,
        album=entry.get("album_name") or entry.get("album"),
        artwork_url=entry.get("cover_url"),
        upload_date=str(entry.get("year")) if entry.get("year") else None,
        duration_seconds=entry.get("duration"),
        uploader=entry.get("artist"),
        source_url=source_url,
        raw=entry,
    )


class SpotifyAdapter(ProviderAdapter):
    name = "spotify"

    async def probe(self, url, external_id, workdir):
        meta_file = os.path.join(workdir, "meta.spotdl")
        argv = [SPOTDL_BIN, "save", url, "--save-file", meta_file] + _client_args()
        rc, stdout, stderr = await run_tool(argv, cwd=workdir)
        raise_for_tool(rc, stderr, "spotdl metadata failed")
        with open(meta_file, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        entry = data[0] if isinstance(data, list) and data else (data or {})
        return _parse_meta(entry, url)

    def fetch_argv(self, url, workdir):
        return [
            SPOTDL_BIN,
            "download",
            url,
            "--format",
            "mp3",
            "--bitrate",
            "320k",
            "--output",
            os.path.join(workdir, "fetch"),
        ] + _client_args()

    async def fetch(self, url, external_id, workdir, progress_cb=None):
        argv = self.fetch_argv(url, workdir)
        rc, stdout, stderr = await run_tool(argv, cwd=workdir)
        raise_for_tool(rc, stderr, "spotdl download failed")
        return single_audio_file(workdir)
