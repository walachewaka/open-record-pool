"""
Object-level authorization helper (MOO-89, IDOR defence).

Downstream issues (playlists, requests, identities) reuse this so a private
resource is always checked against the session user rather than trusting an id
in the URL.
"""
from fastapi import HTTPException


def ensure_owner_or_403(owner_id, user, detail: str = "Not allowed.") -> None:
    """Allow only the resource owner (or the Owner role) through; else 403."""
    if user is not None and (
        getattr(user, "id", None) == owner_id or getattr(user, "role", None) == "owner"
    ):
        return
    raise HTTPException(status_code=403, detail=detail)
