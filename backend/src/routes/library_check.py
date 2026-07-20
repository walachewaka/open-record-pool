"""
POST /library/check (MOO-90): the pre-download library check the download
engine (MOO-78) and the request flow (MOO-81) call before fetching anything.
Answers "is this recording already in the library, and would the offered
source improve on the canonical version?" so equal-or-worse downloads are
skipped entirely.

Security bar (MOO-89): authenticated (members submit requests), rate
limited (item 5) -- it fans out indexed lookups per call.
"""
from fastapi import APIRouter, Depends, HTTPException

import src.crud.dedup as dedup_crud
from src.auth.jwthandler import get_current_user
from src.database.models import TrackAnalysis
from src.schemas.dedup import LibraryCheckIn, LibraryCheckOut
from src.schemas.users import UserOutSchema
from src.security.ratelimit import rate_limit
from src.services import dedup as dedup_service

router = APIRouter()


@router.post("/library/check", response_model=LibraryCheckOut)
async def library_check(
    payload: LibraryCheckIn,
    current_user: UserOutSchema = Depends(get_current_user),
) -> LibraryCheckOut:
    """
    Resolve a track offer against the library: external IDs first (ISRC is
    the strongest cross-platform identity), then the local fingerprint
    index, then exact metadata (review-only confidence). would_improve is
    computed from the offered source/bitrate/format hints when given.
    """
    await rate_limit(
        "library_check", str(current_user.id), limit=120, window_seconds=60
    )
    has_identity = bool(
        (payload.artist and payload.title)
        or payload.isrc
        or payload.musicbrainz_id
        or payload.beatport_id
        or payload.spotify_id
        or payload.fingerprint_b64
    )
    if not has_identity:
        raise HTTPException(
            status_code=422,
            detail="Provide metadata, an external id, or a fingerprint",
        )
    result = await dedup_service.check_library(
        artist=payload.artist,
        title=payload.title,
        mix=payload.mix,
        duration_seconds=payload.duration_seconds,
        isrc=payload.isrc,
        musicbrainz_id=payload.musicbrainz_id,
        beatport_id=payload.beatport_id,
        spotify_id=payload.spotify_id,
        fingerprint_b64=payload.fingerprint_b64,
        source=payload.source,
        declared_bitrate_kbps=payload.declared_bitrate_kbps,
        format=payload.format,
    )
    canonical = result.pop("canonical", None)
    if canonical is not None:
        analysis = await TrackAnalysis.get_or_none(song_id=canonical.id)
        result["canonical"] = dedup_crud.song_version_dict(canonical, analysis)
    else:
        result["canonical"] = None
    return LibraryCheckOut(**result)
