"""
Append-only security audit log (MOO-89).

Security-relevant events are persisted to the `audit_log` table and surfaced to
admins at GET /admin/audit. The Postgres copy is authoritative; MOO-83 ships it
into telemetry later. audit_event NEVER raises -- an audit failure must never
break a request path.
"""
import logging
from typing import Optional

from src.database.models import AuditLog

logger = logging.getLogger("orp.audit")

# Event name constants. Callers should use these rather than raw strings.
LOGIN_SUCCESS = "auth.login_success"
LOGIN_FAILURE = "auth.login_failure"
RATE_LIMITED = "auth.rate_limited"
LOGOUT = "auth.logout"
LOGOUT_ALL = "auth.logout_all"
SESSION_REVOKED_ADMIN = "auth.session_revoked_admin"
USER_CREATED = "user.created"
USER_UPDATED = "user.updated"
USER_DELETED = "user.deleted"
ROLE_MATRIX_UPDATED = "role.matrix_updated"
CONTENT_STATUS_CHANGED = "content.status_changed"
CONTENT_UPLOADED = "content.uploaded"
SETTINGS_UPDATED = "settings.updated"
# Recording dedup (MOO-90): canonical merges are audit-worthy (item 6).
DEDUP_AUTO_MERGED = "dedup.auto_merged"
DEDUP_REVIEWED = "dedup.reviewed"
DEDUP_PROMOTED = "dedup.promoted"
DEDUP_MISMATCH_FLAGGED = "dedup.mismatch_flagged"
DEDUP_BACKFILL_STARTED = "dedup.backfill_started"
DEDUP_BACKFILL_FINISHED = "dedup.backfill_finished"
# Playlists / crates (MOO-84)
CRATE_VISIBILITY_CHANGED = "crate.visibility_changed"
CRATE_SHARE_ROTATED = "crate.share_rotated"
# DJ bundle export (MOO-86)
EXPORT_REQUESTED = "export.requested"
EXPORT_DOWNLOADED = "export.downloaded"
# Song requests (MOO-81)
SONG_REQUEST_CREATED = "song_request.created"
SONG_REQUEST_AUTO_APPROVED = "song_request.auto_approved"
SONG_REQUEST_APPROVED = "song_request.approved"
SONG_REQUEST_REJECTED = "song_request.rejected"
SONG_REQUEST_RETRIED = "song_request.retried"
SONG_REQUEST_CANCELLED = "song_request.cancelled"
SONG_REQUEST_FULFILLED = "song_request.fulfilled"
SONG_REQUEST_FAILED = "song_request.failed"

# Metadata editor (MOO-82).
CONTENT_METADATA_EDITED = "content.metadata_edited"
CONTENT_METADATA_ROLLBACK = "content.metadata_rollback"
CONTENT_ART_CHANGED = "content.art_changed"
TAG_PROPOSAL_CREATED = "tag_proposal.created"
TAG_PROPOSAL_APPROVED = "tag_proposal.approved"
TAG_PROPOSAL_REJECTED = "tag_proposal.rejected"


async def audit_event(
    event: str,
    request=None,
    actor=None,
    target_type: Optional[str] = None,
    target_id=None,
    detail: Optional[dict] = None,
) -> None:
    """Record one security event. Best-effort: swallows every error."""
    try:
        ip = None
        user_agent = None
        if request is not None:
            client = getattr(request, "client", None)
            if client is not None and getattr(client, "host", None):
                ip = client.host
            ua = request.headers.get("user-agent")
            if ua:
                user_agent = ua[:255]

        actor_id = getattr(actor, "id", None)
        actor_username = getattr(actor, "username", None)
        if actor_username:
            actor_username = str(actor_username)[:20]

        await AuditLog.create(
            event=event,
            actor_id=actor_id,
            actor_username=actor_username,
            target_type=target_type,
            target_id=None if target_id is None else str(target_id)[:64],
            ip=ip,
            user_agent=user_agent,
            detail=detail,
        )
    except Exception:  # pragma: no cover - never break the caller
        logger.exception("audit_event failed for %s", event)
