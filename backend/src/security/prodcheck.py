"""
Production-mode safety checks (MOO-89).

In production mode (ORP_ENV=production) the app refuses to boot on any known
dev/default secret, so the demo credentials can never survive into production.
In dev mode the same conditions only warn, so the demo stack keeps working
unchanged.
"""
import logging
import os

from src.config import is_production, parse_allowed_origins

logger = logging.getLogger("orp.prodcheck")

# The dev SECRET_KEY committed in docker-compose.yml.
_DEV_SECRET_KEY = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
# The dev Postgres password committed in docker-compose.yml.
_DEV_DB_PASSWORD = "Kae4Apho"
_DEV_ADMIN_PASSWORD = "admin123"
# The dev Grafana password committed in docker-compose.yml (MOO-83).
_DEV_GRAFANA_PASSWORD = "grafana-dev"


async def _collect_problems():
    problems = []

    secret = os.environ.get("SECRET_KEY") or ""
    if not secret:
        problems.append("SECRET_KEY is unset")
    elif len(secret) < 32:
        problems.append("SECRET_KEY is shorter than 32 characters")
    elif secret == _DEV_SECRET_KEY:
        problems.append("SECRET_KEY is the committed dev value")

    db_url = os.environ.get("DATABASE_URL") or ""
    if ":{}@".format(_DEV_DB_PASSWORD) in db_url:
        problems.append("DATABASE_URL uses the dev Postgres password")

    origins = parse_allowed_origins()
    if "*" in origins or "*" in (os.environ.get("ALLOW_ORIGINS") or ""):
        problems.append("ALLOW_ORIGINS contains a wildcard")

    # Refuse the demo admin password without ever storing plaintext: verify the
    # known dev password against the stored hash of the admin account.
    admin_username = os.environ.get("ADMIN_USERNAME", "").strip()
    if admin_username:
        try:
            from src.auth.users import pwd_context
            from src.database.models import Users

            admin = await Users.get_or_none(username=admin_username)
            if admin and admin.password:
                try:
                    if pwd_context.verify(_DEV_ADMIN_PASSWORD, admin.password):
                        problems.append("admin account still uses the demo password")
                except Exception:
                    pass
        except Exception:
            pass

    problems.extend(_collect_sso_problems())
    problems.extend(_collect_grafana_problems())

    return problems


def _collect_grafana_problems():
    """
    Grafana admin credential (MOO-83).

    Grafana is docker-internal and reached only through the authenticated
    /admin/grafana proxy, but its own admin account still exists -- so the
    committed dev password must not survive into production (SECURITY.md 7).
    """
    password = os.environ.get("GRAFANA_ADMIN_PASSWORD") or ""
    if not password:
        return ["GRAFANA_ADMIN_PASSWORD is unset"]
    if password == _DEV_GRAFANA_PASSWORD:
        return ["GRAFANA_ADMIN_PASSWORD is the committed dev value"]
    if len(password) < 12:
        return ["GRAFANA_ADMIN_PASSWORD is shorter than 12 characters"]
    return []


def _collect_sso_problems():
    """
    SSO configuration checks (MOO-88).

    A total lockout (no local login and no identity provider) means nobody can
    sign in at all. The rest are the usual insecure-config refusals: a client
    secret must exist, and every URL in the flow must be https, or the
    authorization code travels in clear text. Like every other check here they
    refuse the boot in production and only warn in dev.
    """
    from src.auth import oidc

    problems = []
    providers = list(oidc.PROVIDERS.values())
    if not oidc.local_login_enabled() and not providers:
        problems.append(
            "LOCAL_LOGIN_ENABLED=false with no OIDC provider configured "
            "(nobody could sign in)"
        )

    for provider in providers:
        if not provider.client_secret.strip():
            problems.append(
                "OIDC provider '{}' has an empty client secret".format(provider.id)
            )
        for label, url in (
            ("issuer", provider.issuer),
            ("discovery URL", provider.discovery_url),
        ):
            if not url.startswith("https://"):
                problems.append(
                    "OIDC provider '{}' has a non-https {}".format(provider.id, label)
                )
    if providers:
        for name, url in (
            ("PUBLIC_BACKEND_URL", oidc.public_backend_url()),
            ("PUBLIC_FRONTEND_URL", oidc.public_frontend_url()),
        ):
            if not url.startswith("https://"):
                problems.append("{} is not https while SSO is enabled".format(name))
    return problems


async def enforce_production_safety() -> None:
    problems = await _collect_problems()
    if not problems:
        return
    message = "Insecure configuration: " + "; ".join(problems)
    if is_production():
        raise RuntimeError(
            message + ". Refusing to start in production mode (ORP_ENV=production)."
        )
    logger.warning(
        "%s (allowed in dev mode; set ORP_ENV=production to enforce)", message
    )
