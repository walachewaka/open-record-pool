"""
OIDC provider registry (MOO-88).

A provider is a config entry, not code: Entra ID, Google, Google Workspace,
Okta -- and anything else that speaks OpenID Connect (Keycloak, Authentik, ...)
-- are the same code path with different environment variables.

Client secrets live in the environment/secret store only, never in the database
and never in the repo, so the registry is parsed from env at import:

    OIDC_PROVIDERS=entra,google,workspace,okta
    OIDC_ENTRA_ISSUER=https://login.microsoftonline.com/<tenant>/v2.0
    OIDC_ENTRA_CLIENT_ID=...
    OIDC_ENTRA_CLIENT_SECRET=...

With OIDC_PROVIDERS unset the platform behaves exactly as it did before this
feature: pure local username/password auth.

Parsing fails closed -- a half-configured provider raises at import (and so at
boot), rather than 500ing at someone's first login attempt.
"""
import json
import os
import re
from collections import OrderedDict

GOOGLE_ISSUER = "https://accounts.google.com"

# Per-provider registration policy. `closed` is the default: an unknown subject
# cannot create an account, which is the conservative extension of the existing
# ADMIN_USERNAME registration gate.
PROVISIONING_MODES = ("closed", "invite", "domain", "open")

# Roles a claim->role mapping is allowed to grant. `owner` is deliberately
# absent: the pool Owner is the ADMIN_USERNAME account, never an IDP claim.
MAPPABLE_ROLES = ("admin", "curator", "member")

_ID_RE = re.compile(r"^[a-z0-9_]{1,40}$")


class OIDCProvider(object):
    """One configured identity provider."""

    def __init__(
        self,
        id,
        issuer,
        client_id,
        client_secret,
        discovery_url=None,
        display_name=None,
        scopes=None,
        provisioning="closed",
        allowed_domains=None,
        groups_claim=None,
        group_role_map=None,
    ):
        self.id = id
        self.issuer = issuer
        self.client_id = client_id
        self.client_secret = client_secret
        self.discovery_url = discovery_url or (
            issuer.rstrip("/") + "/.well-known/openid-configuration"
        )
        self.display_name = display_name or id.title()
        self.scopes = scopes or "openid email profile"
        self.provisioning = provisioning
        self.allowed_domains = allowed_domains or []
        self.groups_claim = groups_claim
        self.group_role_map = group_role_map or {}

    @property
    def is_google(self):
        """Google issuers carry the hosted-domain (`hd`) claim we enforce on."""
        return self.issuer.rstrip("/") == GOOGLE_ISSUER

    def __repr__(self):  # pragma: no cover - debugging aid
        return "<OIDCProvider {}>".format(self.id)


def _env(provider_id, suffix, default=None):
    return os.environ.get("OIDC_{}_{}".format(provider_id.upper(), suffix), default)


def _bool_env(name, default=False):
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ("true", "1", "yes")


def _csv(raw):
    return [part.strip().lower() for part in (raw or "").split(",") if part.strip()]


def load_providers():
    """Parse OIDC_* into an ordered {id: OIDCProvider}. Raises on bad config."""
    providers = OrderedDict()
    for provider_id in _csv(os.environ.get("OIDC_PROVIDERS")):
        if not _ID_RE.match(provider_id):
            raise RuntimeError(
                "OIDC_PROVIDERS: '{}' is not a valid provider id "
                "(lowercase letters, digits and underscore, max 40)".format(provider_id)
            )
        issuer = (_env(provider_id, "ISSUER") or "").strip()
        client_id = (_env(provider_id, "CLIENT_ID") or "").strip()
        client_secret = _env(provider_id, "CLIENT_SECRET") or ""
        for name, value in (
            ("ISSUER", issuer),
            ("CLIENT_ID", client_id),
            ("CLIENT_SECRET", client_secret.strip()),
        ):
            if not value:
                raise RuntimeError(
                    "OIDC provider '{}' is missing OIDC_{}_{}".format(
                        provider_id, provider_id.upper(), name
                    )
                )

        provisioning = (
            (_env(provider_id, "PROVISIONING", "closed") or "").strip().lower()
        )
        if provisioning not in PROVISIONING_MODES:
            raise RuntimeError(
                "OIDC provider '{}': PROVISIONING must be one of {}".format(
                    provider_id, ", ".join(PROVISIONING_MODES)
                )
            )
        allowed_domains = _csv(_env(provider_id, "ALLOWED_DOMAINS"))
        if provisioning == "domain" and not allowed_domains:
            raise RuntimeError(
                "OIDC provider '{}': PROVISIONING=domain needs "
                "OIDC_{}_ALLOWED_DOMAINS".format(provider_id, provider_id.upper())
            )

        groups_claim = (_env(provider_id, "GROUPS_CLAIM") or "").strip() or None
        raw_map = (_env(provider_id, "GROUP_ROLE_MAP") or "").strip()
        group_role_map = {}
        if raw_map:
            try:
                group_role_map = json.loads(raw_map)
            except ValueError:
                raise RuntimeError(
                    "OIDC provider '{}': GROUP_ROLE_MAP is not valid JSON".format(
                        provider_id
                    )
                )
            if not isinstance(group_role_map, dict):
                raise RuntimeError(
                    "OIDC provider '{}': GROUP_ROLE_MAP must be a JSON object "
                    "of group -> role".format(provider_id)
                )
            for group, role in group_role_map.items():
                if role not in MAPPABLE_ROLES:
                    raise RuntimeError(
                        "OIDC provider '{}': GROUP_ROLE_MAP maps '{}' to '{}'; "
                        "allowed roles are {}".format(
                            provider_id, group, role, ", ".join(MAPPABLE_ROLES)
                        )
                    )

        providers[provider_id] = OIDCProvider(
            id=provider_id,
            issuer=issuer,
            client_id=client_id,
            client_secret=client_secret,
            discovery_url=(_env(provider_id, "DISCOVERY_URL") or "").strip() or None,
            display_name=(_env(provider_id, "DISPLAY_NAME") or "").strip() or None,
            scopes=(_env(provider_id, "SCOPES") or "").strip() or None,
            provisioning=provisioning,
            allowed_domains=allowed_domains,
            groups_claim=groups_claim,
            group_role_map=group_role_map,
        )
    return providers


PROVIDERS = load_providers()


def reload_providers():
    """Re-parse the registry from the current environment (tests, boot checks)."""
    global PROVIDERS
    PROVIDERS = load_providers()
    return PROVIDERS


def get_provider(provider_id):
    """The configured provider, or None when it is unknown/disabled."""
    return PROVIDERS.get(provider_id)


def public_frontend_url():
    return os.environ.get("PUBLIC_FRONTEND_URL", "http://localhost:8088").rstrip("/")


def public_backend_url():
    return os.environ.get("PUBLIC_BACKEND_URL", "http://localhost:5000").rstrip("/")


def redirect_uri(provider_id):
    """The exact redirect URI to register with the IDP (never host-derived)."""
    return "{}/auth/oidc/{}/callback".format(public_backend_url(), provider_id)


def local_login_enabled():
    """Whether username/password sign-in is offered (IDP-only pools set false)."""
    return _bool_env("LOCAL_LOGIN_ENABLED", True)


def email_autolink_enabled():
    """
    Whether a verified IDP email may claim an existing local account.

    Off by default: email-match linking is the classic SSO account-takeover
    primitive (IDPs disagree on what "verified" means, mailbox addresses get
    recycled). The safe path is the explicit logged-in link flow.
    """
    return _bool_env("OIDC_EMAIL_AUTOLINK", False)
