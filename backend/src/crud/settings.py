"""
CRUD for the instance settings key/value store (MOO-71).

Settings are grouped (general/library/storage/integrations). Each leaf is
stored as one row keyed "group.key" with a JSON-encoded value; reads start
from the coded defaults and overlay the stored rows. Internal bookkeeping
(keys starting with "_") is stored the same way but never exposed.
"""
import json

from fastapi import HTTPException

from src.database.models import InstanceSettings
from src.extract import musicfiles

# The default settings and, implicitly, the set of valid keys. Editing the
# matrix of allowed settings is a one-line change here.
DEFAULT_SETTINGS = {
    "general": {
        "pool_name": "CRATE",
        "tagline": "Self-hosted record pool",
        # Stored only; wiring this to open registration would weaken the
        # ADMIN_USERNAME gating, so it is intentionally informational.
        "public_signup": False,
        "require_approval": False,
    },
    "library": {
        "nas_source_path": musicfiles.MUSIC_PATH,
        "strip_unsafe_tags": False,
        "dedupe": True,
        "search_status": "n/a",
        # Recording-level dedup (MOO-90). auto_resolve toggles whether a
        # high-confidence fingerprint match merges automatically or queues
        # for review; source_trust is a JSON object string overlaying the
        # coded D5 defaults; quarantine_purge_days is a placeholder only --
        # 0 = off, and no purge is implemented (nothing is ever deleted).
        "dedup_auto_resolve_fingerprint": True,
        "dedup_fingerprint_threshold": 0.90,
        "dedup_review_threshold": 0.70,
        "dedup_duration_tolerance_seconds": 3.0,
        "dedup_source_trust": "",
        "dedup_quarantine_purge_days": 0,
    },
    "storage": {
        "media_path": musicfiles.UPLOAD_PATH,
        "max_upload_mb": 50,
        "keep_wav": True,
        # No-op flags today (documented): transcoding and a high-performance
        # mode are not implemented, the fields persist the operator's intent.
        "transcode": False,
        "high_performance_mode": False,
    },
    "integrations": {
        "smtp_host": "",
        "smtp_port": 587,
        "smtp_user": "",
        "smtp_password": "",
        "webhook_url": "",
        "s3_bucket": "",
        "s3_region": "",
        "s3_access_key": "",
        "s3_secret_key": "",
        # Music download engine (MOO-78). All providers ship DISABLED by
        # default -- the operator opts in per provider, since the ToS/legality
        # of ripping varies by source and jurisdiction (see docs/DOWNLOADS.md).
        "downloads_enabled": False,
        "downloads_youtube": False,
        "downloads_soundcloud": False,
        "downloads_spotify": False,
        # When true, fetched tracks enter the moderation queue (status=pending)
        # instead of publishing straight to the library.
        "downloads_require_approval": False,
        # Per-user daily submission cap (UTC day); 0 = unlimited.
        "downloads_daily_limit": 20,
        # Beatport metadata enrichment (MOO-85). Default off: when true and
        # the provider is enabled (mock or live), a library scan/upload
        # auto-enqueues an enrich_song job for each new song id.
        "beatport_auto_enrich": False,
    },
    "song_requests": {
        # Song request system (MOO-81). Master switch; submitting 403s when
        # off, but the member/admin list surfaces keep working.
        "enabled": True,
        # Roles whose submissions skip moderation and enqueue immediately.
        # Owner is implicitly auto-approved and never appears in this list.
        # auto_approve_roles is validated (subset of admin/curator/member) in
        # src/crud/song_requests.py, not here.
        "auto_approve_roles": [],
        # Per-user daily submission cap (UTC day, counts every created row
        # incl. duplicates/cancelled); 0 = unlimited.
        "daily_quota": 5,
    },
}

_LAST_SCAN_KEY = "_internal.last_scan"


async def _stored():
    """All stored settings rows as a {key: decoded_value} map."""
    result = {}
    for row in await InstanceSettings.all():
        try:
            result[row.key] = json.loads(row.value) if row.value is not None else None
        except (ValueError, TypeError):
            result[row.key] = row.value
    return result


async def get_all():
    """The full grouped settings: defaults overlaid with stored overrides."""
    stored = await _stored()
    settings = {group: dict(values) for group, values in DEFAULT_SETTINGS.items()}
    for group, values in settings.items():
        for key in values:
            dotted = "{}.{}".format(group, key)
            if dotted in stored:
                values[key] = stored[dotted]
    return settings


async def _set(dotted_key, value):
    await InstanceSettings.update_or_create(
        key=dotted_key, defaults={"value": json.dumps(value)}
    )


async def update(partial):
    """
    Apply a partial, grouped update ({group: {key: value}}) and return the full
    settings. Unknown groups or keys are rejected so typos surface immediately.
    """
    for group, values in partial.items():
        if group not in DEFAULT_SETTINGS:
            raise HTTPException(
                status_code=422, detail="Unknown settings group: {}".format(group)
            )
        if not isinstance(values, dict):
            raise HTTPException(
                status_code=422,
                detail="Settings group '{}' must be an object".format(group),
            )
        for key, value in values.items():
            if key not in DEFAULT_SETTINGS[group]:
                raise HTTPException(
                    status_code=422,
                    detail="Unknown setting: {}.{}".format(group, key),
                )
            await _set("{}.{}".format(group, key), value)
    return await get_all()


async def get_value(group, key):
    """One effective setting value (default overlaid with any stored override)."""
    dotted = "{}.{}".format(group, key)
    stored = await _stored()
    if dotted in stored:
        return stored[dotted]
    return DEFAULT_SETTINGS[group][key]


async def record_scan(summary):
    """Persist the last /music scan summary for the dashboard health panel."""
    await _set(_LAST_SCAN_KEY, summary)


async def get_last_scan():
    """The last stored scan summary, or None."""
    stored = await _stored()
    return stored.get(_LAST_SCAN_KEY)
