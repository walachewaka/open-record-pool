"""
The active list of release sources (MOO-80 D2). Mock wins when
RELEASE_SOURCE_MOCK=true (dev/test only -- never mixed with live results),
else Beatport when configured (BEATPORT_MOCK/credentials, see
src.enrichment.provider), else an empty list -- callers must handle that as
D3's degraded no-creds mode, never a 5xx. MusicBrainz slots in later behind
one more file + one more line here.
"""
from src.sources.beatport import BeatportReleaseSource
from src.sources.mock import MockReleaseSource, mock_enabled

_mock = MockReleaseSource()
_beatport = BeatportReleaseSource()


def get_release_sources():
    if mock_enabled():
        return [_mock]
    if _beatport.configured():
        return [_beatport]
    return []
