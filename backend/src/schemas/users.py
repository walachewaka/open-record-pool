from typing import Dict

from tortoise.contrib.pydantic import pydantic_model_creator

from src.database.models import Users


# The reverse relations added by MOO-65/MOO-71 (crates, favorites, play
# events, downloads, uploaded songs) must stay out of the user schemas:
# nesting them would prefetch a user's whole library activity on every
# authenticated request.
_USER_RELATIONS = [
    "crates",
    "favorites",
    "play_events",
    "downloads",
    "uploaded_songs",
    # Duplicate resolutions performed by this user (MOO-90) stay out for the
    # same reason.
    "dup_resolutions",
    # Song requests submitted/decided by this user (MOO-81): served by their
    # own routes, never nested onto the user shape.
    "song_requests",
    "decided_song_requests",
    # Linked IDP identities (MOO-88): their own endpoint, never nested on the
    # user shape that every authenticated request builds.
    "identities",
    # Metadata edits, proposals, and reviews by this user (MOO-82): served by
    # their own routes, never nested onto the user shape.
    "tag_revisions",
    "tag_proposals",
    "reviewed_tag_proposals",
]

# The self-service /register body only carries the account basics. Role, plan,
# status, and email are set by the admin surface (MOO-71), never by the
# registrant -- letting a registrant pick their own role would be a privilege
# escalation on top of the ADMIN_USERNAME bootstrap gating.
UserInSchema = pydantic_model_creator(
    Users,
    name="UserIn",
    exclude_readonly=True,
    exclude=["email", "role", "plan", "status"] + _USER_RELATIONS,
)
# What authenticated callers see about themselves: identity plus the admin
# fields (role/plan/status/email) the frontend needs to render the console.
UserOutSchema = pydantic_model_creator(
    Users,
    name="UserOut",
    exclude=["password", "created_at", "modified_at"] + _USER_RELATIONS,
)
UserDatabaseSchema = pydantic_model_creator(
    Users, name="User", exclude=["created_at", "modified_at"] + _USER_RELATIONS
)


class WhoAmISchema(UserOutSchema):
    """The /users/whoami payload: the user plus their role's effective
    permissions, so the frontend can gate the admin surface (MOO-72)."""

    permissions: Dict[str, bool] = {}
    # Whether the account still has a local password (MOO-88). False for an
    # SSO-only, JIT-provisioned user.
    has_password: bool = True
