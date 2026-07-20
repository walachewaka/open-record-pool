"""
Single sign-on routes (MOO-88).

The whole OIDC dance lives here: /auth/oidc/{provider}/start mints a PKCE
transaction and bounces the browser to the IDP; /auth/oidc/{provider}/callback
verifies what comes back and -- only then -- issues one of OUR sessions through
the same auth_sessions cookie mechanism a local login uses. There is no second
session system and no provider token is ever stored.

Both endpoints are top-level browser navigations, so failures cannot be a JSON
body: they redirect to the login gate with a fixed `sso_error` code from the
enum below. The code is deliberately coarse (no IDP detail, no email, no
username) -- an SSO error page is not an account-enumeration oracle.
"""
import hmac
from datetime import timedelta
from typing import List, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

import src.crud.identities as crud
from src.auth import oidc, oidc_http, oidc_txn, oidc_validate
from src.auth.jwthandler import (
    create_access_token,
    get_current_user,
    get_current_user_optional,
)
from src.auth.permissions import require_permission
from src.database.models import Users
from src.schemas.identities import (
    AdminSSOProviderSchema,
    AdminSSOStatusSchema,
    AuthMethodsSchema,
    IdentitySchema,
)
from src.schemas.users import UserOutSchema
from src.security import audit, ratelimit, sessions

router = APIRouter(tags=["auth: sso"])

# Audit events for the SSO surface (MOO-89 item 6).
SSO_LOGIN = "auth.sso.login"
SSO_LOGIN_FAILURE = "auth.sso.login_failure"
SSO_PROVISIONED = "user.sso_provisioned"
IDENTITY_LINKED = "user.identity.linked"
IDENTITY_UNLINKED = "user.identity.unlinked"


def _provider_or_404(provider_id):
    provider = oidc.get_provider(provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Unknown identity provider")
    return provider


def _identity_item(row) -> IdentitySchema:
    provider = oidc.get_provider(row.provider)
    return IdentitySchema(
        id=row.id,
        provider=row.provider,
        # An identity whose provider has since been removed from the config
        # still renders (and can still be unlinked) under its raw id.
        provider_name=provider.display_name if provider else row.provider,
        email=row.email,
        created_at=row.created_at,
        last_login_at=row.last_login_at,
    )


def _gate_redirect(error_code):
    response = RedirectResponse(
        "{}/login?sso_error={}".format(oidc.public_frontend_url(), error_code),
        status_code=302,
    )
    oidc_txn.clear_txn_cookie(response)
    return response


async def _fail(request, provider_id, error_code, reason):
    await audit.audit_event(
        SSO_LOGIN_FAILURE,
        request=request,
        detail={"provider": provider_id, "reason": reason},
    )
    return _gate_redirect(error_code)


@router.get("/auth/methods", response_model=AuthMethodsSchema)
async def auth_methods() -> AuthMethodsSchema:
    """
    What the login gate should render. Public and static: no user data, no DB
    hit, and never the client ids or secrets.
    """
    return AuthMethodsSchema(
        local_login=oidc.local_login_enabled(),
        providers=[
            {"id": provider.id, "display_name": provider.display_name}
            for provider in oidc.PROVIDERS.values()
        ],
    )


@router.get("/auth/oidc/{provider_id}/start")
async def sso_start(
    request: Request,
    provider_id: str,
    link: Optional[str] = None,
    current_user=Depends(get_current_user_optional),
):
    """
    Begin an authorization-code + PKCE flow. `link=1` (with a live session)
    starts the same flow in link mode: the identity is attached to the signed-in
    account instead of signing anyone in.
    """
    provider = _provider_or_404(provider_id)
    try:
        await ratelimit.rate_limit("idp_start", ratelimit.client_ip(request), 10, 60)
    except HTTPException as exc:
        if exc.status_code == 429:
            await audit.audit_event(
                audit.RATE_LIMITED,
                request=request,
                detail={"provider": provider_id, "endpoint": "sso_start"},
            )
            return _gate_redirect("rate_limited")
        raise

    linking = link in ("1", "true", "yes")
    if linking and current_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        metadata = await oidc_http.fetch_discovery(provider)
    except oidc_http.OIDCError:
        raise HTTPException(
            status_code=503,
            detail="Identity provider is unavailable. Try again later.",
        )

    token, state, nonce, challenge = oidc_txn.mint_txn(
        provider_id,
        mode="link" if linking else "login",
        link_user_id=current_user.id if linking else None,
    )
    params = {
        "response_type": "code",
        "client_id": provider.client_id,
        "redirect_uri": oidc.redirect_uri(provider_id),
        "scope": provider.scopes,
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    if provider.is_google and provider.allowed_domains:
        # Cosmetic account-picker filtering only. Enforcement is on the `hd`
        # claim inside the verified ID token, never on this parameter.
        params["hd"] = provider.allowed_domains[0]

    separator = "&" if "?" in metadata["authorization_endpoint"] else "?"
    response = RedirectResponse(
        metadata["authorization_endpoint"] + separator + urlencode(params),
        status_code=302,
    )
    oidc_txn.set_txn_cookie(response, token)
    return response


@router.get("/auth/oidc/{provider_id}/callback")
async def sso_callback(
    request: Request,
    provider_id: str,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
):
    """Verify the provider's answer and, if it holds up, sign the user in."""
    provider = _provider_or_404(provider_id)
    try:
        await ratelimit.rate_limit("idp_callback", ratelimit.client_ip(request), 10, 60)
    except HTTPException as exc:
        if exc.status_code == 429:
            await audit.audit_event(
                audit.RATE_LIMITED,
                request=request,
                detail={"provider": provider_id, "endpoint": "sso_callback"},
            )
            return _gate_redirect("rate_limited")
        raise

    txn = oidc_txn.read_txn(request, provider_id)
    if txn is None:
        return await _fail(request, provider_id, "expired", "no_transaction")
    if error:
        return await _fail(request, provider_id, "denied", "idp_error:{}".format(error))
    if not code or not state or not hmac.compare_digest(state, txn["state"]):
        return await _fail(request, provider_id, "invalid", "state_mismatch")

    try:
        id_token = await oidc_http.exchange_code(
            provider,
            code,
            txn["code_verifier"],
            oidc.redirect_uri(provider_id),
        )
        metadata = await oidc_http.fetch_discovery(provider)
        claims = await oidc_validate.validate_id_token(
            provider, id_token, txn["nonce"], metadata["jwks_uri"]
        )
    except oidc_http.OIDCError as exc:
        return await _fail(request, provider_id, "invalid", str(exc)[:200])

    subject = str(claims.get("sub") or "")
    if not subject:
        return await _fail(request, provider_id, "invalid", "no_subject")
    if not oidc_validate.check_domain(provider, claims):
        return await _fail(request, provider_id, "domain_not_allowed", "domain")

    if txn.get("mode") == "link":
        return await _complete_link(request, provider, claims, txn)
    return await _complete_login(request, provider, claims)


async def _complete_link(request, provider, claims, txn):
    """Attach this identity to the already-signed-in account."""
    user = await Users.get_or_none(id=txn.get("link_user_id"))
    if user is None or user.status == "suspended":
        return await _fail(request, provider.id, "expired", "link_user_gone")

    existing = await crud.get_by_subject(provider.id, str(claims["sub"]))
    if existing is not None and existing.user_id != user.id:
        # Whose account it belongs to is deliberately not disclosed.
        return await _fail(request, provider.id, "already_linked", "already_linked")
    if existing is None:
        await crud.create_identity(user, provider.id, claims)
        await audit.audit_event(
            IDENTITY_LINKED,
            request=request,
            actor=user,
            target_type="user",
            target_id=user.id,
            detail={"provider": provider.id},
        )
    else:
        await crud.touch_login(existing, claims)

    response = RedirectResponse(
        "{}/profile?link=ok".format(oidc.public_frontend_url()), status_code=302
    )
    oidc_txn.clear_txn_cookie(response)
    return response


async def _complete_login(request, provider, claims):
    """Resolve the identity to an account (provisioning it if policy allows)."""
    subject = str(claims["sub"])
    identity = await crud.get_by_subject(provider.id, subject)
    user = None
    provisioned = False

    if identity is not None:
        user = await Users.get_or_none(id=identity.user_id)
        if user is None:
            return await _fail(request, provider.id, "not_permitted", "orphan_identity")
        await crud.touch_login(identity, claims)
    else:
        if oidc.email_autolink_enabled():
            user = await crud.autolink_candidate(provider.id, claims)
            if user is not None:
                identity = await crud.create_identity(user, provider.id, claims)
                await audit.audit_event(
                    IDENTITY_LINKED,
                    request=request,
                    actor=user,
                    target_type="user",
                    target_id=user.id,
                    detail={"provider": provider.id, "via": "email_match"},
                )
        if user is None:
            if provider.provisioning == "closed":
                return await _fail(
                    request, provider.id, "not_permitted", "unknown_subject"
                )
            if provider.provisioning in ("domain", "open") and not claims.get(
                "email_verified"
            ):
                # JIT without a verified email would let an IDP hand us an
                # address its user never proved they own.
                return await _fail(
                    request, provider.id, "not_permitted", "email_unverified"
                )
            user = await crud.provision_user(provider, claims)
            identity = await crud.create_identity(user, provider.id, claims)
            provisioned = True
            await audit.audit_event(
                SSO_PROVISIONED,
                request=request,
                actor=user,
                target_type="user",
                target_id=user.id,
                detail={"provider": provider.id, "status": user.status},
            )

    if user.status == "pending":
        # `invite` policy: the account exists but an admin must activate it
        # (/admin/users?status=pending). No session is issued.
        return await _fail(request, provider.id, "pending_approval", "pending")
    if user.status == "suspended":
        return await _fail(request, provider.id, "not_permitted", "suspended")

    if not provisioned:
        await crud.apply_role_mapping(provider, user, claims)
        user = await Users.get(id=user.id)

    jti = await sessions.create_session(user, request)
    token = create_access_token(
        data={"sub": user.username, "jti": jti},
        expires_delta=timedelta(minutes=sessions.access_token_expire_minutes()),
    )
    await audit.audit_event(
        SSO_LOGIN,
        request=request,
        actor=user,
        detail={"provider": provider.id},
    )
    response = RedirectResponse(
        "{}/home".format(oidc.public_frontend_url()), status_code=302
    )
    sessions.set_auth_cookie(response, token)
    oidc_txn.clear_txn_cookie(response)
    return response


@router.get("/users/me/identities", response_model=List[IdentitySchema])
async def list_my_identities(
    current_user: UserOutSchema = Depends(get_current_user),
) -> List[IdentitySchema]:
    """My linked sign-in methods."""
    return [_identity_item(row) for row in await crud.list_for_user(current_user.id)]


@router.delete("/users/me/identities/{identity_id}")
async def unlink_my_identity(
    request: Request,
    identity_id: int,
    current_user: UserOutSchema = Depends(get_current_user),
):
    """
    Remove one of MY sign-in methods. Someone else's or an unknown id -> 404;
    the last remaining method -> 409.
    """
    identity = await crud.unlink(current_user.id, identity_id)
    await audit.audit_event(
        IDENTITY_UNLINKED,
        request=request,
        actor=current_user,
        target_type="user",
        target_id=current_user.id,
        detail={"provider": identity.provider},
    )
    return {"message": "Sign-in method removed"}


@router.get("/admin/sso/providers", response_model=AdminSSOStatusSchema)
async def admin_sso_providers(
    actor: UserOutSchema = Depends(require_permission("site_settings")),
) -> AdminSSOStatusSchema:
    """
    Read-only view of the configured providers. Providers are environment
    config (secrets never touch the DB), so there is nothing to edit here --
    this page tells the operator what the running process actually loaded, and
    the exact redirect URI each IDP must whitelist.
    """
    counts = await crud.count_by_provider()
    return AdminSSOStatusSchema(
        local_login=oidc.local_login_enabled(),
        email_autolink=oidc.email_autolink_enabled(),
        providers=[
            AdminSSOProviderSchema(
                id=provider.id,
                display_name=provider.display_name,
                issuer=provider.issuer,
                client_id=provider.client_id,
                scopes=provider.scopes,
                provisioning=provider.provisioning,
                allowed_domains=provider.allowed_domains,
                role_mapping=bool(provider.groups_claim and provider.group_role_map),
                redirect_uri=oidc.redirect_uri(provider.id),
                linked_identities=counts.get(provider.id, 0),
                discovery=oidc_http.discovery_status(provider.id),
            )
            for provider in oidc.PROVIDERS.values()
        ],
    )


@router.get("/admin/users/{user_id}/identities", response_model=List[IdentitySchema])
async def admin_list_identities(
    user_id: int,
    actor: UserOutSchema = Depends(require_permission("manage_users")),
) -> List[IdentitySchema]:
    if await Users.get_or_none(id=user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    return [_identity_item(row) for row in await crud.list_for_user(user_id)]


@router.delete("/admin/users/{user_id}/identities/{identity_id}")
async def admin_unlink_identity(
    request: Request,
    user_id: int,
    identity_id: int,
    actor: UserOutSchema = Depends(require_permission("manage_users")),
):
    """
    Unlink a user's sign-in method. The last-method guard applies to admins too:
    stranding an account is fixed with the user tools, not by force-unlinking.
    """
    identity = await crud.unlink(user_id, identity_id)
    await audit.audit_event(
        IDENTITY_UNLINKED,
        request=request,
        actor=actor,
        target_type="user",
        target_id=user_id,
        detail={"provider": identity.provider},
    )
    return {"message": "Sign-in method removed"}
