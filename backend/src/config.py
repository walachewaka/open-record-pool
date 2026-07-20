"""
Small, import-safe configuration helpers shared across the app and the
security middlewares (MOO-89).

Kept dependency-free (only os / typing) so it can be imported from both
src.main and src.security.* without creating an import cycle.
"""
import os
from typing import List


def orp_env() -> str:
    """The deployment mode: "dev" (default) or "production" (MOO-89)."""
    return os.environ.get("ORP_ENV", "dev").strip().lower() or "dev"


def is_production() -> bool:
    return orp_env() == "production"


def parse_allowed_origins() -> List[str]:
    """
    Parse ALLOW_ORIGINS into the list of browser origins allowed to make
    credentialed requests. The frontend origin (localhost:8088) is always
    included so the demo stack works with no configuration.

    Example: ALLOW_ORIGINS=http://localhost:8088,http://192.168.0.1:8088
    """
    allow_origins = os.environ.get("ALLOW_ORIGINS", "http://localhost:8088")
    ret = [o.strip() for o in allow_origins.split(",") if o.strip()]
    ret.append("http://localhost:8088")
    # Remove duplicates, preserving no particular order.
    return list(set(ret))


def resolve_cookie_secure() -> bool:
    """
    Whether the auth cookie (and HSTS) should be marked Secure (MOO-89).

    COOKIE_SECURE=auto (default) -> True only in production mode; explicit
    "true"/"false" override it (for TLS-terminating proxies, or prod-without-
    TLS labs).
    """
    raw = os.environ.get("COOKIE_SECURE", "auto").strip().lower()
    if raw in ("true", "1", "yes"):
        return True
    if raw in ("false", "0", "no"):
        return False
    return is_production()
