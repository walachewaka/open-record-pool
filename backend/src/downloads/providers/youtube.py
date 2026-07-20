"""
YouTube adapter via yt-dlp (MOO-78). Metadata from --dump-single-json, audio
extracted to mp3. Nothing is needed for public videos; an optional mounted
cookies file (YTDLP_COOKIES_FILE) unlocks age-restricted content.
"""
import json
import os
import re

from src.downloads.providers.base import (
    DOWNLOAD_MAX_FILE_MB,
    ProviderAdapter,
    raise_for_tool,
    run_tool,
    single_audio_file,
    source_metadata,
)

YTDLP_BIN = os.environ.get("YTDLP_BIN", "/opt/tools/yt-dlp/bin/yt-dlp")
YTDLP_COOKIES_FILE = os.environ.get("YTDLP_COOKIES_FILE", "")

_PROGRESS = re.compile(r"\[download\]\s+([0-9]{1,3}(?:\.[0-9]+)?)%")


def _cookies_args():
    if YTDLP_COOKIES_FILE and os.path.isfile(YTDLP_COOKIES_FILE):
        return ["--cookies", YTDLP_COOKIES_FILE]
    return []


def parse_metadata(info, source_url):
    """Map a yt-dlp info-json dict onto a SourceMetadata dict."""
    upload_date = info.get("upload_date")
    if upload_date and len(str(upload_date)) == 8:
        upload_date = "{}-{}-{}".format(
            str(upload_date)[0:4], str(upload_date)[4:6], str(upload_date)[6:8]
        )
    return source_metadata(
        title=info.get("track") or info.get("title"),
        artist=info.get("artist") or info.get("uploader"),
        album=info.get("album"),
        artwork_url=info.get("thumbnail"),
        upload_date=upload_date,
        duration_seconds=info.get("duration"),
        uploader=info.get("uploader"),
        source_url=source_url,
        raw=info,
    )


class YouTubeAdapter(ProviderAdapter):
    name = "youtube"

    async def probe(self, url, external_id, workdir):
        argv = (
            [
                YTDLP_BIN,
                "--dump-single-json",
                "--no-playlist",
                "--skip-download",
            ]
            + _cookies_args()
            + [url]
        )
        rc, stdout, stderr = await run_tool(argv, cwd=workdir)
        raise_for_tool(rc, stderr, "yt-dlp probe failed")
        info = json.loads(stdout.strip().splitlines()[-1])
        return parse_metadata(info, url)

    def fetch_argv(self, url, workdir):
        return (
            [
                YTDLP_BIN,
                "--no-playlist",
                "--no-continue",
                "--max-filesize",
                "{}M".format(DOWNLOAD_MAX_FILE_MB),
                "-x",
                "--audio-format",
                "mp3",
                "--audio-quality",
                "0",
                "--embed-metadata",
                "--embed-thumbnail",
                "--newline",
                "-o",
                "fetch.%(ext)s",
                "--paths",
                workdir,
            ]
            + _cookies_args()
            + [url]
        )

    async def fetch(self, url, external_id, workdir, progress_cb=None):
        async def on_line(line):
            if progress_cb is None:
                return
            match = _PROGRESS.search(line)
            if match:
                await progress_cb(float(match.group(1)) / 100.0)

        argv = self.fetch_argv(url, workdir)
        rc, stdout, stderr = await run_tool(argv, cwd=workdir, progress_cb=on_line)
        raise_for_tool(rc, stderr, "yt-dlp download failed")
        return single_audio_file(workdir)
