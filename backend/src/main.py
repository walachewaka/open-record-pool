"""
Main entry point of our backend service.
"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from tortoise import Tortoise

from src.config import is_production, parse_allowed_origins
from src.database.register import register_tortoise
from src.database.config import TORTOISE_ORM

# enable schemas to read relationship between models
Tortoise.init_models(["src.database.models"], "models")

# Imports from src.routes must be after 'Tortoise.init_models'
# See https://stackoverflow.com/questions/65531387/tortoise-orm-for-python-no-returns-relations-of-entities-pyndantic-fastapi

from src.routes import analysis
from src.routes import auth_sso
from src.routes import crates
from src.routes import library
from src.routes import library_check
from src.routes import notes
from src.routes import search
from src.routes import songs
from src.routes import users
from src.routes import roles
from src.routes import admin_users
from src.routes import admin_content
from src.routes import admin_duplicates
from src.routes import admin_settings
from src.routes import admin_reports
from src.routes import admin_audit
from src.routes import jobs
from src.routes import fetch
from src.routes import admin_fetch
from src.routes import song_requests
from src.routes import admin_song_requests
from src.routes import admin_enrichment
from src.routes import tags
from src.routes import admin_tags
from src.routes import artists
from src.routes import releases
from src.routes import admin_follows
from src.routes import exports
from src.routes import grafana_proxy
from src.routes import telemetry as telemetry_routes
from src.security.csrf import OriginCheckMiddleware
from src.security.headers import SecurityHeadersMiddleware
from src.security.sessions import SessionCookieMiddleware
from src.telemetry.middleware import TelemetryMiddleware

__version__ = "0.1.0-snapshot"
app_name = "open-record-pool-backend"

# In production, the interactive API docs (and the OpenAPI schema they need)
# are turned off to shrink the surface (MOO-89). Dev keeps them on.
if is_production():
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
else:
    app = FastAPI()


# Middlewares (MOO-89). add_middleware prepends, so the LAST added runs first
# on the request: OriginCheck (reject foreign origins) -> SessionCookie (rotate)
# -> SecurityHeaders (set headers on the way out) -> CORS -> Telemetry -> app.
# Telemetry is added FIRST so it sits innermost and times the handler itself
# rather than the middleware stack around it (MOO-83).
app.add_middleware(TelemetryMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=parse_allowed_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(SessionCookieMiddleware)
app.add_middleware(OriginCheckMiddleware)
app.include_router(users.router)
# OIDC single sign-on (MOO-88): sessions still come from the MOO-89 mechanism.
app.include_router(auth_sso.router)
app.include_router(notes.router)
app.include_router(songs.router)
app.include_router(crates.router)
app.include_router(library.router)
# Admin console (MOO-71):
app.include_router(roles.router)
app.include_router(admin_users.router)
app.include_router(admin_content.router)
app.include_router(admin_settings.router)
app.include_router(admin_reports.router)
# Security audit log (MOO-89):
app.include_router(admin_audit.router)
# Background jobs (MOO-77):
app.include_router(jobs.router)
# ES-backed instant search (MOO-79):
app.include_router(search.router)
# Ingestion analyzer (MOO-87):
app.include_router(analysis.router)
# Recording dedup: admin duplicates surface + the library check (MOO-90):
app.include_router(admin_duplicates.router)
app.include_router(library_check.router)
# Music download engine (MOO-78):
app.include_router(fetch.router)
app.include_router(admin_fetch.router)
# Song request system (MOO-81):
app.include_router(song_requests.router)
app.include_router(admin_song_requests.router)
# Beatport metadata enrichment (MOO-85):
app.include_router(admin_enrichment.router)
# Metadata editor & album art (MOO-82):
app.include_router(tags.router)
app.include_router(admin_tags.router)
# Follow artists / release tracking (MOO-80):
app.include_router(artists.router)
app.include_router(releases.router)
app.include_router(admin_follows.router)
# DJ crate export -- Serato / Traktor / rekordbox (MOO-86):
app.include_router(exports.router)
# Telemetry pipeline + the authenticated Grafana embed proxy (MOO-83):
app.include_router(telemetry_routes.router)
app.include_router(grafana_proxy.router)

# Setup the database:
register_tortoise(app, config=TORTOISE_ORM, generate_schemas=False)


@app.on_event("startup")
async def _ensure_owner():
    """
    Promote the ADMIN_USERNAME account to Owner on boot (MOO-71). Registered
    after register_tortoise so Tortoise is initialized first. Idempotent, so an
    admin created before the role column existed is promoted on the next start.
    """
    from src.crud.users import promote_admin_to_owner

    await promote_admin_to_owner()


@app.on_event("startup")
async def _security_startup():
    """
    Production safety checks and the default-deny route guard (MOO-89).

    enforce_production_safety refuses to boot on dev/default secrets when
    ORP_ENV=production (and only warns in dev). assert_routes_guarded fails the
    boot if any route ships without a declared authorization dependency.
    """
    from src.security.prodcheck import enforce_production_safety
    from src.security.route_guard import assert_routes_guarded

    await enforce_production_safety()
    assert_routes_guarded(app)


@app.on_event("startup")
async def _search_startup():
    """
    Search index bootstrap (MOO-79): ensure orp-tracks-v1 + the alias exist.
    Guarded and non-fatal -- ES still starting (or disabled) leaves search in
    degraded mode, never blocks the API boot.
    """
    from src.search.indexer import ensure_search_index

    await ensure_search_index()


@app.on_event("startup")
async def _telemetry_startup():
    """
    Start the telemetry flush loop (MOO-83). No-op when telemetry is off or no
    ELASTICSEARCH_URL is configured; the ES index template and ILM policy are
    PUT by the loop itself, so a still-booting ES is not a problem.
    """
    from src.telemetry import start_emitter

    start_emitter()


@app.on_event("shutdown")
async def _telemetry_shutdown():
    from src.routes.grafana_proxy import close_grafana_client
    from src.telemetry import stop_emitter

    await stop_emitter()
    await close_grafana_client()


@app.on_event("shutdown")
async def _search_shutdown():
    from src.search.es import close_es

    await close_es()


# Setup the endpoints:
@app.get("/")
def home():
    return f"This is {app_name} {__version__}"


@app.get("/ping")
def ping():
    return {"ping": "pong!"}


@app.get("/version")
def version():
    return {"app": app_name, "version": __version__}


@app.get("/healthz")
async def healthz():
    """
    Readiness probe for API replicas and compose healthchecks (MOO-77). The
    single declared exception to the every-route-declares-auth rule (MOO-89):
    it is public, returns no user data, and may be rate-limited later. redis
    is null when the worker tier is disabled (inline mode).
    """
    import asyncio

    from fastapi.responses import JSONResponse

    from src.jobs.queue import workers_enabled

    database_ok = True
    try:
        connection = Tortoise.get_connection("default")
        await connection.execute_query("SELECT 1")
    except Exception:
        database_ok = False

    redis_ok = None
    if workers_enabled():
        redis_ok = False
        try:
            # Lazy import: arq/redis are absent in inline-mode environments.
            from redis.asyncio import Redis

            client = Redis.from_url(os.environ["REDIS_URL"])
            try:
                redis_ok = bool(await asyncio.wait_for(client.ping(), timeout=0.2))
            finally:
                await client.close()
        except Exception:
            redis_ok = False

    body = {
        "status": "ok" if database_ok else "degraded",
        "database": database_ok,
        "redis": redis_ok,
    }
    return JSONResponse(status_code=200 if database_ok else 503, content=body)
