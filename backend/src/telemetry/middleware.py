"""
API request telemetry (MOO-83).

Pure ASGI, NOT BaseHTTPMiddleware, for the same reason as the security headers
(MOO-89): BaseHTTPMiddleware buffers the response body, which would wreck the
Range/206 audio streaming path.

Only the route TEMPLATE is recorded ("/songs/{song_id}/download"), never the
concrete path -- a keyword field fed raw paths would have unbounded cardinality.
Requests are sampled at TELEMETRY_API_SAMPLE_RATE (5xx always recorded), and
the whole middleware is inert unless TELEMETRY_LEVEL=detailed.
"""
import random
import time

from src.telemetry import events
from src.telemetry.emitter import api_sample_rate, level

# Noise: health probes, the static root, the beacon itself (it would double
# count every play), and the Grafana proxy (dozens of asset requests per view).
SKIP_PATHS = frozenset(["/", "/ping", "/healthz", "/version", "/telemetry/beacon"])
SKIP_PREFIXES = ("/admin/grafana",)


def route_template(scope):
    """
    The path with its parameters put back as {name} placeholders. Starlette
    0.19 does not stash the matched route on the scope, so we rebuild the
    template from the concrete path and the captured path_params -- which keeps
    the cardinality of the `route` keyword bounded either way.
    """
    route = scope.get("route")
    if route is not None and getattr(route, "path", None):
        return route.path
    path = scope.get("path") or "/"
    params = scope.get("path_params") or {}
    if not params:
        return path if scope.get("endpoint") is not None else "unmatched"
    name_by_value = {str(value): name for name, value in params.items()}
    segments = [
        "{" + name_by_value[seg] + "}" if seg in name_by_value else seg
        for seg in path.split("/")
    ]
    return "/".join(segments)


class TelemetryMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or level() != "detailed":
            return await self.app(scope, receive, send)
        path = scope.get("path") or "/"
        if path in SKIP_PATHS or path.startswith(SKIP_PREFIXES):
            return await self.app(scope, receive, send)

        started = time.monotonic()
        status = {"code": 500}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = int((time.monotonic() - started) * 1000)
            code = status["code"]
            # 5xx is never sampled away -- an error rate panel built on a 10%
            # sample of failures is worse than no panel.
            if code >= 500 or random.random() < api_sample_rate():
                events.api_request(
                    method=scope.get("method"),
                    route=route_template(scope),
                    status_code=code,
                    duration_ms=duration_ms,
                    user_id=None,
                )
