"""
Fake provider (MOO-78 D2): a deterministic, network-free adapter used by the
Playwright e2e stack and the live mock smoke. Registered ONLY when
ORP_FAKE_DOWNLOADS=true, and only "handles" the fixture URL
https://www.youtube.com/watch?v=ORPFIXTURE1. Never used in production (the app
warns at startup if the flag is set with ORP_ENV=production).
"""
import os

from src.downloads.providers.base import ProviderAdapter, source_metadata

FIXTURE_EXTERNAL_ID = "ORPFIXTURE1"

# A single silent MPEG-1 Layer III frame header: FF FB 90 00 is a valid
# 128 kbps / 44.1 kHz stereo frame. 417 bytes/frame; a few hundred frames give
# mutagen a real, parseable ~2s MP3 with a genuine sha256.
_FRAME_HEADER = b"\xff\xfb\x90\x00"
_FRAME_LEN = 417


def _synth_mp3(frames=200):
    frame = _FRAME_HEADER + b"\x00" * (_FRAME_LEN - len(_FRAME_HEADER))
    return frame * frames


class FakeAdapter(ProviderAdapter):
    name = "youtube"

    async def probe(self, url, external_id, workdir):
        return source_metadata(
            title="ORP Fixture Track",
            artist="ORP Test",
            album="Fixtures",
            duration_seconds=2.0,
            uploader="ORP Test",
            source_url=url,
            raw={"fixture": True, "external_id": external_id},
        )

    async def fetch(self, url, external_id, workdir, progress_cb=None):
        path = os.path.join(workdir, "fetch.mp3")
        with open(path, "wb") as handle:
            handle.write(_synth_mp3())
        if progress_cb is not None:
            await progress_cb(1.0)
        return path
