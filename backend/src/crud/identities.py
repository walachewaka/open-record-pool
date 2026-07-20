"""
Linked IDP identities: matching, provisioning, linking (MOO-88).

The account rules that matter, in one place:

- A login is resolved by (provider, subject) and nothing else. The email copy we
  store is informational; a provider-side email change must not move an
  identity, and a matching email must never claim an account on its own.
- SSO provisioning is a separate, more restrictive path than /register: it is
  default-closed per provider, always creates a plain member with no password,
  and can never create or claim the ADMIN_USERNAME account. The existing admin
  registration gate is neither weakened nor bypassed.
- Unlinking may never strand an account: the last sign-in method cannot be
  removed.
"""
import random
import re
from datetime import datetime, timezone

from fastapi import HTTPException

from src.auth.permissions import OWNER
from src.crud.users import get_admin_username
from src.database.models import UserIdentities, Users

_USERNAME_CHARS = re.compile(r"[^a-z0-9_.-]")
USERNAME_MAX = 20


async def get_by_subject(provider_id, subject):
    return await UserIdentities.get_or_none(provider=provider_id, subject=subject)


async def list_for_user(user_id):
    return await UserIdentities.filter(user_id=user_id).order_by("created_at").all()


async def count_by_provider():
    """{provider: linked identities} for the admin SSO page."""
    counts = {}
    for row in await UserIdentities.all().only("id", "provider"):
        counts[row.provider] = counts.get(row.provider, 0) + 1
    return counts


async def touch_login(identity, claims):
    """Refresh the informational copies after a successful login."""
    identity.email = claims.get("email") or identity.email
    identity.email_verified = bool(claims.get("email_verified"))
    identity.display_name = claims.get("name") or identity.display_name
    identity.last_login_at = datetime.now(timezone.utc)
    await identity.save(
        update_fields=["email", "email_verified", "display_name", "last_login_at"]
    )


async def create_identity(user, provider_id, claims):
    return await UserIdentities.create(
        user_id=user.id,
        provider=provider_id,
        subject=str(claims["sub"]),
        email=claims.get("email"),
        email_verified=bool(claims.get("email_verified")),
        display_name=claims.get("name"),
        last_login_at=datetime.now(timezone.utc),
    )


async def autolink_candidate(provider_id, claims):
    """
    The one existing account a verified IDP email may claim, or None.

    Only ever consulted when OIDC_EMAIL_AUTOLINK is on. Ambiguity (zero or more
    than one match, an unverified email, or a user who already holds another
    identity on this provider) resolves to None -- we never guess.
    """
    if not claims.get("email_verified"):
        return None
    email = (claims.get("email") or "").strip().lower()
    if not email:
        return None
    matches = await Users.filter(email__iexact=email).all()
    if len(matches) != 1:
        return None
    user = matches[0]
    if await UserIdentities.filter(user_id=user.id, provider=provider_id).exists():
        return None
    return user


def _sanitize_username(raw):
    candidate = _USERNAME_CHARS.sub("", (raw or "").strip().lower())
    return candidate[:USERNAME_MAX]


async def _unique_username(claims):
    """
    Derive a free username from the claims. Never the ADMIN_USERNAME account:
    SSO must not be able to create or claim the pool Owner.
    """
    admin_username = get_admin_username()
    base = _sanitize_username((claims.get("email") or "").split("@")[0]) or "sso"

    async def free(name):
        if not name or (admin_username and name == admin_username):
            return False
        return not await Users.filter(username=name).exists()

    if await free(base):
        return base
    for _ in range(3):
        candidate = "{}{:04d}".format(base[:16], random.randint(0, 9999))
        if await free(candidate):
            return candidate
    for _ in range(10):
        candidate = "sso{:08d}".format(random.randint(0, 99999999))
        if await free(candidate):
            return candidate
    raise HTTPException(status_code=503, detail="Could not provision an account")


def mapped_role(provider, claims):
    """The role a group claim grants, or None when mapping is off/silent."""
    if not provider.groups_claim or not provider.group_role_map:
        return None
    raw = claims.get(provider.groups_claim)
    if raw is None:
        return None
    groups = raw if isinstance(raw, (list, tuple)) else [raw]
    groups = [str(group) for group in groups]
    for group, role in provider.group_role_map.items():
        if group in groups:
            return role
    return None


async def apply_role_mapping(provider, user, claims):
    """
    Update an existing user's role from the group claim.

    Only a positive match writes: with mapping off, or a token that carries no
    mapped group, the locally assigned role stays authoritative. The Owner is
    never remapped.
    """
    role = mapped_role(provider, claims)
    if not role or user.role == OWNER or user.role == role:
        return False
    await Users.filter(id=user.id).update(role=role)
    return True


async def provision_user(provider, claims):
    """
    JIT-create the account for a first SSO login. `invite` mode parks it as
    pending for an admin to activate; every other allowed mode creates it
    active. Always a passwordless member (unless a group claim maps a role).
    """
    username = await _unique_username(claims)
    full_name = (claims.get("name") or "")[:50] or None
    status = "pending" if provider.provisioning == "invite" else "active"
    return await Users.create(
        username=username,
        full_name=full_name,
        email=claims.get("email"),
        password=None,
        role=mapped_role(provider, claims) or "member",
        plan="free",
        status=status,
    )


async def unlink(user_id, identity_id):
    """
    Remove a sign-in method. Refused when it is the last one the account has --
    an SSO-only user unlinking their only identity would lock themselves out.
    """
    identity = await UserIdentities.get_or_none(id=identity_id, user_id=user_id)
    if identity is None:
        raise HTTPException(status_code=404, detail="Identity not found")
    user = await Users.get_or_none(id=user_id)
    identity_count = await UserIdentities.filter(user_id=user_id).count()
    has_password = bool(user and user.password)
    if not has_password and identity_count <= 1:
        raise HTTPException(
            status_code=409,
            detail=(
                "Removing this sign-in method would leave the account with no "
                "way to sign in."
            ),
        )
    await identity.delete()
    return identity
