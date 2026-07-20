"""
Beatport provider enablement (MOO-85 D1): a mock / live / disabled tri-state
computed purely from environment variables -- this module NEVER calls
Beatport itself (token validity is not probed; API errors surface later, on
individual enrichment rows, as status="error").

- BEATPORT_MOCK=true -> "mock" (the deterministic fixture client, zero
  network/creds -- lets the whole feature be exercised without a Beatport
  partner account).
- BEATPORT_ENABLED=false -> "disabled", reason "disabled_by_env" (explicit
  operator opt-out, independent of whether creds are present).
- BEATPORT_CLIENT_ID and BEATPORT_CLIENT_SECRET both set -> "live".
- otherwise -> "disabled", reason "credentials_not_configured".

Flipping BEATPORT_MOCK off and setting real credentials is a pure env-var
change: no code path here or in the client needs to change.
"""
import os

from src.database.models import BeatportCache, SongEnrichment

STATUSES = ("pending", "applied", "needs_review", "no_match", "rejected", "error")


class ProviderDisabled(Exception):
    """Raised by get_client() when Beatport is not configured/enabled."""

    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def _truthy(value):
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def mock_enabled():
    return _truthy(os.environ.get("BEATPORT_MOCK"))


def _creds_present():
    return bool(os.environ.get("BEATPORT_CLIENT_ID", "").strip()) and bool(
        os.environ.get("BEATPORT_CLIENT_SECRET", "").strip()
    )


def _explicitly_disabled():
    return os.environ.get("BEATPORT_ENABLED", "").strip().lower() == "false"


def mode_and_reason():
    """("mock"|"live"|"disabled", reason|None) -- see module docstring."""
    if mock_enabled():
        return "mock", None
    if _explicitly_disabled():
        return "disabled", "disabled_by_env"
    if _creds_present():
        return "live", None
    return "disabled", "credentials_not_configured"


def get_client():
    """
    The active client (mock or real). Raises ProviderDisabled (never an
    HTTPException -- callers translate it) when Beatport is not usable.
    """
    mode, reason = mode_and_reason()
    if mode == "mock":
        from src.enrichment.mock_client import MockBeatportClient

        return MockBeatportClient()
    if mode == "live":
        from src.enrichment.beatport_client import BeatportClient

        return BeatportClient()
    raise ProviderDisabled(reason)


async def provider_status():
    """The GET /admin/enrichment/status payload. Never calls Beatport."""
    mode, reason = mode_and_reason()
    counts = {}
    for status in STATUSES:
        counts[status] = await SongEnrichment.filter(
            provider="beatport", status=status
        ).count()
    cache_entries = await BeatportCache.all().count()
    auto_enrich = False
    try:
        import src.crud.settings as settings_crud

        auto_enrich = bool(
            await settings_crud.get_value("integrations", "beatport_auto_enrich")
        )
    except Exception:
        auto_enrich = False
    return {
        "provider": "beatport",
        "enabled": mode != "disabled",
        "mode": mode,
        "reason": reason,
        "auto_enrich_on_import": auto_enrich,
        "rate_limit_rps": float(os.environ.get("BEATPORT_RATE_LIMIT_RPS", "2")),
        "cache_entries": cache_entries,
        "counts": counts,
    }
