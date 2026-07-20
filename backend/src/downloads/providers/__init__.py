"""
Provider adapter registry (MOO-78). get_adapter(provider) returns the adapter
for a provider name. The `fake` adapter is registered over "youtube" only when
ORP_FAKE_DOWNLOADS=true so the e2e/smoke stacks never touch the network.
"""
import os

from src.downloads.providers.soundcloud import SoundCloudAdapter
from src.downloads.providers.spotify import SpotifyAdapter
from src.downloads.providers.youtube import YouTubeAdapter


def fake_downloads_enabled():
    return os.environ.get("ORP_FAKE_DOWNLOADS", "").strip().lower() in ("true", "1")


def _build_registry():
    registry = {
        "youtube": YouTubeAdapter(),
        "soundcloud": SoundCloudAdapter(),
        "spotify": SpotifyAdapter(),
    }
    if fake_downloads_enabled():
        from src.downloads.providers.fake import FakeAdapter

        registry["youtube"] = FakeAdapter()
    return registry


# Rebuilt lazily so tests can flip the env var before first use.
_REGISTRY = None


def get_adapter(provider):
    """The adapter for a provider name, or None for an unknown provider."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _build_registry()
    return _REGISTRY.get(provider)


def reset_registry():
    """Force the registry to rebuild (used by tests after toggling env)."""
    global _REGISTRY
    _REGISTRY = None
