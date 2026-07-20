"""
SoundCloud adapter (MOO-78). Metadata is probed with yt-dlp's SoundCloud
extractor (JSON only, no audio); audio is fetched with scdl. Public tracks
need nothing; an optional SOUNDCLOUD_AUTH_TOKEN unlocks higher-quality streams.
"""
import json
import os

from src.downloads.providers.base import (
    ProviderAdapter,
    raise_for_tool,
    run_tool,
    single_audio_file,
)
from src.downloads.providers.youtube import YTDLP_BIN, parse_metadata

SCDL_BIN = os.environ.get("SCDL_BIN", "/opt/tools/scdl/bin/scdl")
SOUNDCLOUD_AUTH_TOKEN = os.environ.get("SOUNDCLOUD_AUTH_TOKEN", "")


class SoundCloudAdapter(ProviderAdapter):
    name = "soundcloud"

    async def probe(self, url, external_id, workdir):
        argv = [
            YTDLP_BIN,
            "--dump-single-json",
            "--no-playlist",
            "--skip-download",
            url,
        ]
        rc, stdout, stderr = await run_tool(argv, cwd=workdir)
        raise_for_tool(rc, stderr, "soundcloud probe failed")
        info = json.loads(stdout.strip().splitlines()[-1])
        return parse_metadata(info, url)

    def fetch_argv(self, url, workdir):
        argv = [
            SCDL_BIN,
            "-l",
            url,
            "--path",
            workdir,
            "--name-format",
            "fetch",
            "--onlymp3",
            "--overwrite",
            "--hide-progress",
        ]
        if SOUNDCLOUD_AUTH_TOKEN:
            argv += ["--auth-token", SOUNDCLOUD_AUTH_TOKEN]
        return argv

    async def fetch(self, url, external_id, workdir, progress_cb=None):
        # scdl has no machine-readable progress. The auth token is redacted from
        # any argv logging via redact_argv(argv, redact=("--auth-token",)).
        argv = self.fetch_argv(url, workdir)
        rc, stdout, stderr = await run_tool(argv, cwd=workdir)
        raise_for_tool(rc, stderr, "scdl download failed")
        return single_audio_file(workdir)
