"""
Default-deny route guard (MOO-89).

FastAPI cannot literally default-deny, so we make an unguarded route fail the
boot instead. assert_routes_guarded walks every APIRoute and requires that its
dependency tree contains an authz-tagged dependency (get_current_user,
get_current_user_optional, or a require_permission(...) closure -- each tagged
with __orp_authz__), OR that its path is in the frozen PUBLIC_ROUTES allow-list.
Anything else raises at startup, so a new route with no declared authorization
never ships.
"""
from fastapi.routing import APIRoute

# The only routes allowed to carry no auth dependency. Additions need a written
# justification (see SECURITY.md item 1).
PUBLIC_ROUTES = frozenset(
    {
        "/",
        "/ping",
        "/version",
        "/healthz",
        "/login",
        "/logout",
        # SSO (MOO-88). These are the pre-authentication surface by definition:
        # /auth/methods returns static config (which buttons to render), and the
        # two OIDC endpoints ARE the login flow -- start mints a PKCE
        # transaction (it declares get_current_user_optional for link mode) and
        # callback verifies the provider's answer before issuing a session.
        "/auth/methods",
        "/auth/oidc/{provider_id}/start",
        "/auth/oidc/{provider_id}/callback",
        "/docs",
        "/docs/oauth2-redirect",
        "/openapi.json",
        "/redoc",
    }
)


def _has_authz(dependant) -> bool:
    call = getattr(dependant, "call", None)
    if call is not None and getattr(call, "__orp_authz__", None) is not None:
        return True
    for sub in getattr(dependant, "dependencies", []) or []:
        if _has_authz(sub):
            return True
    return False


def assert_routes_guarded(app) -> None:
    for route in app.routes:
        if not isinstance(route, APIRoute):
            # Mounts, static, websocket, etc. are not app API routes.
            continue
        if route.path in PUBLIC_ROUTES:
            continue
        if _has_authz(route.dependant):
            continue
        methods = ",".join(sorted(route.methods or []))
        raise RuntimeError(
            "Route {} {} has no declared authorization".format(methods, route.path)
        )
