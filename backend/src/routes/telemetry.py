"""
Telemetry routes (MOO-83): the player beacon and the pipeline status card.

The beacon is the one piece of client instrumentation the pipeline needs: the
browser is the only place that knows how far into a track the user actually got
before the player moved on, which is what turns raw play.start events into
completion and skip rates.
"""
import os
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.auth.jwthandler import get_current_user
from src.auth.permissions import require_permission
from src.database.models import AuditLog, Songs
from src.schemas.users import UserOutSchema
from src.search.es import es_ping, events_index_name
from src.security.ratelimit import rate_limit
from src.telemetry import events, shipper
from src.telemetry.emitter import stats

router = APIRouter()

BEACON_TYPES = ("play.end",)


class BeaconIn(BaseModel):
    type: str = Field(..., description="Only 'play.end' in v1")
    song_id: int
    position_ms: int = Field(..., ge=0)
    duration_ms: int = Field(..., gt=0)
    ended: bool = False


@router.post("/telemetry/beacon", status_code=202)
async def beacon(
    payload: BeaconIn, current_user: UserOutSchema = Depends(get_current_user)
) -> Dict[str, bool]:
    """
    Record the end of a playback (completed or skipped).

    Always answers 202, even for an unknown song or with telemetry switched
    off: a beacon must never surface an error in the player, and a 404 here
    would leak which song ids exist.
    """
    await rate_limit("telemetry_beacon", str(current_user.id), 120, 60)
    if payload.type not in BEACON_TYPES:
        raise HTTPException(status_code=422, detail="Unsupported beacon type")
    song = await Songs.get_or_none(id=payload.song_id)
    if song is not None:
        events.play_end(
            current_user,
            song,
            position_ms=payload.position_ms,
            duration_ms=payload.duration_ms,
            ended=payload.ended,
        )
    return {"accepted": True}


async def _grafana_reachable() -> bool:
    """Cheap liveness probe; a down Grafana is a false, never an exception."""
    import httpx

    from src.routes.grafana_proxy import GRAFANA_URL

    try:
        async with httpx.AsyncClient(timeout=0.5) as client:
            response = await client.get(GRAFANA_URL + "/api/health")
            return response.status_code == 200
    except Exception:
        return False


@router.get(
    "/admin/telemetry/status",
    response_model=Dict[str, Any],
    dependencies=[Depends(require_permission("view_reports"))],
)
async def telemetry_status() -> Dict[str, Any]:
    """The health card behind the admin Insights page."""
    from datetime import datetime, timezone

    snapshot = stats()
    reachable = await es_ping()
    shipped = await shipper.shipped_cursor()
    latest = await AuditLog.all().order_by("-id").first()
    latest_id = latest.id if latest else 0

    snapshot["es_reachable"] = reachable
    snapshot["index_today"] = events_index_name(datetime.now(timezone.utc))
    snapshot["grafana_reachable"] = await _grafana_reachable()
    snapshot["audit_shipper"] = {
        "last_shipped_audit_id": shipped,
        "lag": None if shipped is None else max(latest_id - shipped, 0),
    }
    snapshot["grafana_url_path"] = "/admin/grafana/"
    snapshot["dashboards"] = [
        {"uid": "orp-listening", "title": "Listening"},
        {"uid": "orp-library", "title": "Library"},
        {"uid": "orp-engagement", "title": "Engagement"},
        {"uid": "orp-system", "title": "System"},
    ]
    return snapshot


@router.get(
    "/admin/telemetry/config",
    response_model=Dict[str, Any],
    dependencies=[Depends(require_permission("site_settings"))],
)
async def telemetry_config() -> Dict[str, Any]:
    """
    The effective knobs, so an operator can see what the containers were
    actually started with (they are env-only by design -- a self-hosted
    operator edits compose, not a settings row).
    """
    return {
        "TELEMETRY_ENABLED": os.environ.get("TELEMETRY_ENABLED", "true"),
        "TELEMETRY_LEVEL": os.environ.get("TELEMETRY_LEVEL", "detailed"),
        "TELEMETRY_BUFFER_MAX": os.environ.get("TELEMETRY_BUFFER_MAX", "5000"),
        "TELEMETRY_FLUSH_INTERVAL_SECONDS": os.environ.get(
            "TELEMETRY_FLUSH_INTERVAL_SECONDS", "2"
        ),
        "TELEMETRY_FLUSH_MAX_BATCH": os.environ.get("TELEMETRY_FLUSH_MAX_BATCH", "500"),
        "TELEMETRY_API_SAMPLE_RATE": os.environ.get("TELEMETRY_API_SAMPLE_RATE", "0.1"),
        "TELEMETRY_RETENTION_DAYS": os.environ.get("TELEMETRY_RETENTION_DAYS", "180"),
    }
