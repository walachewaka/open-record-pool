"""
Our crates routes: playlist CRUD, ordered track membership, public/shared
read access, and M3U export (MOO-65). Extended MOO-84 with description,
cover art, gap-based single-track reorder, paginated contents, public
discovery, duplicate-to-mine, and share-link rotation.
"""
import hashlib
import re
from typing import List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response

import src.crud.crates as crud
from src.auth.jwthandler import get_current_user
from src.database.models import Crates, CrateTracks, Jobs, Songs
from src.export import bundle
from src.jobs.queue import submit_job
from src.schemas.exports import ExportRequest
from src.schemas.jobs import JobOut
from src.schemas.crates import (
    CrateDetailSchema,
    CrateDuplicateInSchema,
    CrateInSchema,
    CrateReorderSchema,
    CrateSummarySchema,
    CrateTrackInSchema,
    CrateTrackMoveOutSchema,
    CrateTrackMoveSchema,
    CrateTracksPageSchema,
    CrateUpdateSchema,
    PublicCratesResponseSchema,
)
from src.schemas.token import Status
from src.schemas.users import UserOutSchema
from src.security import audit
from src.security.ratelimit import rate_limit
from src.telemetry import events
from src.utils import storage
from tortoise.functions import Count

router = APIRouter()

_UNSAFE_FILENAME = re.compile(r'[\\/:*?"<>|\r\n\x00]')
MAX_COVER_BYTES = 2 * 1024 * 1024
# A DJ bundle is GBs of audio: two in flight per user is plenty (MOO-86).
MAX_ACTIVE_EXPORTS = 2


@router.post("/crates", response_model=CrateSummarySchema)
async def create_crate(
    crate_in: CrateInSchema, current_user: UserOutSchema = Depends(get_current_user)
) -> CrateSummarySchema:
    """
    Creates an empty crate owned by the current user.
    """
    crate = await Crates.create(
        name=crate_in.name,
        color=crate_in.color,
        description=crate_in.description,
        dj_target=crate_in.dj_target,
        owner_id=current_user.id,
        share_token=crud.new_share_token(),
    )
    return CrateSummarySchema(**crud.summary_dict(crate, 0, for_owner=True))


@router.get("/crates", response_model=List[CrateSummarySchema])
async def list_my_crates(
    current_user: UserOutSchema = Depends(get_current_user),
) -> List[CrateSummarySchema]:
    """
    Lists the current user's crates, oldest first.
    """
    crates = (
        await Crates.filter(owner_id=current_user.id)
        .annotate(track_count=Count("tracks"))
        .order_by("id")
    )
    return [
        CrateSummarySchema(**crud.summary_dict(c, int(c.track_count), for_owner=True))
        for c in crates
    ]


@router.get("/crates/public", response_model=PublicCratesResponseSchema)
async def list_public_crates(
    q: Optional[str] = Query(None, max_length=200),
    cursor: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    current_user: UserOutSchema = Depends(get_current_user),
) -> PublicCratesResponseSchema:
    """
    Browsable/searchable public crates (playlists) of ALL users -- name,
    description, owner username, track count. Never a private crate, never
    a share_token.
    """
    items, next_cursor = await crud.public_crates_page(q, cursor=cursor, limit=limit)
    return PublicCratesResponseSchema(items=items, next_cursor=next_cursor)


@router.get("/crates/shared/{share_token}", response_model=CrateDetailSchema)
async def resolve_shared_crate(
    share_token: str, current_user: UserOutSchema = Depends(get_current_user)
) -> CrateDetailSchema:
    """
    Resolves a share link: anyone logged in with the token can read the
    crate, whether or not it is public.
    """
    crate = await Crates.get_or_none(share_token=share_token)
    if crate is None:
        raise HTTPException(status_code=404, detail="Crate not found")
    return CrateDetailSchema(**await crud.detail_dict(crate, current_user))


@router.get("/crates/{crate_id}", response_model=CrateDetailSchema)
async def get_crate(
    crate_id: int, current_user: UserOutSchema = Depends(get_current_user)
) -> CrateDetailSchema:
    """
    The crate with the first page of its ordered tracks. Readable by its
    owner, by anyone logged in when the crate is public, or by a platform
    owner/admin.
    """
    crate = await crud.get_crate_or_404(crate_id)
    crud.check_can_read(crate, current_user)
    return CrateDetailSchema(**await crud.detail_dict(crate, current_user))


@router.get("/crates/{crate_id}/tracks", response_model=CrateTracksPageSchema)
async def get_crate_tracks(
    crate_id: int,
    cursor: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    current_user: UserOutSchema = Depends(get_current_user),
) -> CrateTracksPageSchema:
    """
    Paginated crate contents -- walk a crate with millions of tracks a page
    at a time. Same read access as viewing the crate.
    """
    crate = await crud.get_crate_or_404(crate_id)
    crud.check_can_read(crate, current_user)
    items, next_cursor = await crud.tracks_page(
        crate, current_user, cursor=cursor, limit=limit
    )
    return CrateTracksPageSchema(items=items, next_cursor=next_cursor)


@router.patch("/crates/{crate_id}", response_model=CrateSummarySchema)
async def update_crate(
    request: Request,
    crate_id: int,
    crate_in: CrateUpdateSchema,
    current_user: UserOutSchema = Depends(get_current_user),
) -> CrateSummarySchema:
    """
    Renames the crate, edits its description, changes its color, or toggles
    its public flag.
    """
    crate = await crud.get_crate_or_404(crate_id)
    crud.check_is_owner(crate, current_user)
    changes = crate_in.dict(exclude_unset=True)
    visibility_changed = "public" in changes and changes["public"] != crate.public
    for field, value in changes.items():
        setattr(crate, field, value)
    if changes:
        await crate.save()
    if visibility_changed:
        await audit.audit_event(
            audit.CRATE_VISIBILITY_CHANGED,
            request=request,
            actor=current_user,
            target_type="crate",
            target_id=crate.id,
            detail={"public": crate.public},
        )
    track_count = await CrateTracks.filter(crate_id=crate.id).count()
    return CrateSummarySchema(**crud.summary_dict(crate, track_count, for_owner=True))


@router.delete("/crates/{crate_id}", response_model=Status)
async def delete_crate(
    crate_id: int, current_user: UserOutSchema = Depends(get_current_user)
) -> Status:
    """
    Deletes the crate and its track membership.
    """
    crate = await crud.get_crate_or_404(crate_id)
    crud.check_is_owner(crate, current_user)
    await crate.delete()
    return Status(message=f"Deleted crate {crate_id}")


@router.post("/crates/{crate_id}/duplicate", response_model=CrateSummarySchema)
async def duplicate_crate(
    request: Request,
    crate_id: int,
    payload: CrateDuplicateInSchema,
    current_user: UserOutSchema = Depends(get_current_user),
) -> CrateSummarySchema:
    """
    "Duplicate to my crates": copies any crate the caller can read (owned,
    public, or reached via its share link) into a fresh private crate they
    own.
    """
    crate = await crud.get_crate_or_404(crate_id)
    crud.check_can_read(crate, current_user)
    await rate_limit("crate_duplicate", str(current_user.id), 10, 3600)
    new_crate = await crud.duplicate_crate(crate, current_user, name=payload.name)
    track_count = await CrateTracks.filter(crate_id=new_crate.id).count()
    return CrateSummarySchema(
        **crud.summary_dict(new_crate, track_count, for_owner=True)
    )


@router.post("/crates/{crate_id}/share/rotate", response_model=CrateSummarySchema)
async def rotate_crate_share_token(
    request: Request,
    crate_id: int,
    current_user: UserOutSchema = Depends(get_current_user),
) -> CrateSummarySchema:
    """
    Rotates the crate's share link: the old link 404s immediately, a fresh
    unguessable token takes its place.
    """
    crate = await crud.get_crate_or_404(crate_id)
    crud.check_is_owner(crate, current_user)
    crate.share_token = crud.new_share_token()
    await crate.save(update_fields=["share_token"])
    await audit.audit_event(
        audit.CRATE_SHARE_ROTATED,
        request=request,
        actor=current_user,
        target_type="crate",
        target_id=crate.id,
    )
    track_count = await CrateTracks.filter(crate_id=crate.id).count()
    return CrateSummarySchema(**crud.summary_dict(crate, track_count, for_owner=True))


@router.post("/crates/{crate_id}/cover", response_model=CrateSummarySchema)
async def upload_crate_cover(
    crate_id: int,
    file: UploadFile = File(...),
    current_user: UserOutSchema = Depends(get_current_user),
) -> CrateSummarySchema:
    """
    Uploads a custom cover (JPEG or PNG, <=2 MiB), stored content-addressed
    under /library/art. Owner only.
    """
    crate = await crud.get_crate_or_404(crate_id)
    crud.check_is_owner(crate, current_user)
    await rate_limit("crate_cover", str(current_user.id), 10, 300)
    data = await file.read(MAX_COVER_BYTES + 1)
    if len(data) > MAX_COVER_BYTES:
        raise HTTPException(
            status_code=413, detail="Cover image is too large (max 2 MiB)"
        )
    if data[:3] == b"\xff\xd8\xff":
        ext = "jpg"
    elif data[:8] == b"\x89PNG\r\n\x1a\n":
        ext = "png"
    else:
        raise HTTPException(status_code=422, detail="Cover must be a JPEG or PNG image")
    sha256_hex = hashlib.sha256(data).hexdigest()
    dest = await storage.store_artifact_bytes(data, sha256_hex, kind="art", ext=ext)
    crate.cover_path = dest
    await crate.save(update_fields=["cover_path"])
    track_count = await CrateTracks.filter(crate_id=crate.id).count()
    return CrateSummarySchema(**crud.summary_dict(crate, track_count, for_owner=True))


@router.delete("/crates/{crate_id}/cover", response_model=Status)
async def delete_crate_cover(
    crate_id: int, current_user: UserOutSchema = Depends(get_current_user)
) -> Status:
    """
    Clears the crate's custom cover (falls back to the auto-collage).
    """
    crate = await crud.get_crate_or_404(crate_id)
    crud.check_is_owner(crate, current_user)
    if not crate.cover_path:
        raise HTTPException(status_code=404, detail="This crate has no cover")
    crate.cover_path = None
    await crate.save(update_fields=["cover_path"])
    return Status(message=f"Removed cover for crate {crate_id}")


@router.get("/crates/{crate_id}/cover")
async def get_crate_cover(
    crate_id: int, current_user: UserOutSchema = Depends(get_current_user)
):
    """
    Serves the crate's cover image bytes. Same read access as viewing the
    crate -- covers are never a static (unauthenticated) mount.
    """
    crate = await crud.get_crate_or_404(crate_id)
    crud.check_can_read(crate, current_user)
    if not crate.cover_path:
        raise HTTPException(status_code=404, detail="This crate has no cover")
    ext = crate.cover_path.rsplit(".", 1)[-1].lower()
    media_type = "image/png" if ext == "png" else "image/jpeg"
    return FileResponse(
        crate.cover_path,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.post("/crates/{crate_id}/tracks", response_model=CrateDetailSchema)
async def add_crate_track(
    crate_id: int,
    track_in: CrateTrackInSchema,
    current_user: UserOutSchema = Depends(get_current_user),
) -> CrateDetailSchema:
    """
    Appends a song at the end of the crate. Adding a song that is already
    in the crate is a 409.
    """
    crate = await crud.get_crate_or_404(crate_id)
    crud.check_is_owner(crate, current_user)
    song = await Songs.get_or_none(id=track_in.song_id)
    if song is None:
        raise HTTPException(status_code=404, detail="Song not found")
    exists = await CrateTracks.filter(crate_id=crate.id, song_id=song.id).exists()
    if exists:
        raise HTTPException(status_code=409, detail="Song is already in this crate")
    await CrateTracks.create(
        crate_id=crate.id, song_id=song.id, position=await crud.next_position(crate)
    )
    return CrateDetailSchema(**await crud.detail_dict(crate, current_user))


@router.put("/crates/{crate_id}/tracks", response_model=CrateDetailSchema)
async def reorder_crate_tracks(
    crate_id: int,
    reorder: CrateReorderSchema,
    current_user: UserOutSchema = Depends(get_current_user),
) -> CrateDetailSchema:
    """
    Reorders the crate: the payload must list every song id currently in
    the crate exactly once, in the new order. Crates over
    MAX_PERMUTATION_REORDER tracks must use the single-track move endpoint
    instead.
    """
    crate = await crud.get_crate_or_404(crate_id)
    crud.check_is_owner(crate, current_user)
    memberships = await CrateTracks.filter(crate_id=crate.id)
    current_ids = {m.song_id for m in memberships}
    if len(current_ids) > crud.MAX_PERMUTATION_REORDER:
        raise HTTPException(
            status_code=422,
            detail="Use the move endpoint for crates over {} tracks".format(
                crud.MAX_PERMUTATION_REORDER
            ),
        )
    if (
        len(reorder.song_ids) != len(set(reorder.song_ids))
        or set(reorder.song_ids) != current_ids
    ):
        raise HTTPException(
            status_code=422,
            detail="song_ids must be a permutation of the crate's current songs",
        )
    position_by_song = {
        song_id: i * crud.POSITION_STEP for i, song_id in enumerate(reorder.song_ids)
    }
    for membership in memberships:
        new_position = position_by_song[membership.song_id]
        if membership.position != new_position:
            membership.position = new_position
            await membership.save(update_fields=["position"])
    return CrateDetailSchema(**await crud.detail_dict(crate, current_user))


@router.patch(
    "/crates/{crate_id}/tracks/{song_id}", response_model=CrateTrackMoveOutSchema
)
async def move_crate_track(
    crate_id: int,
    song_id: int,
    move: CrateTrackMoveSchema,
    current_user: UserOutSchema = Depends(get_current_user),
) -> CrateTrackMoveOutSchema:
    """
    Single-track drag-and-drop reorder: moves [song_id] to sit immediately
    after [after_song_id] (the very top when null).
    """
    crate = await crud.get_crate_or_404(crate_id)
    crud.check_is_owner(crate, current_user)
    new_position = await crud.move_track(crate, song_id, move.after_song_id)
    return CrateTrackMoveOutSchema(song_id=song_id, position=new_position)


@router.delete("/crates/{crate_id}/tracks/{song_id}", response_model=Status)
async def remove_crate_track(
    crate_id: int,
    song_id: int,
    current_user: UserOutSchema = Depends(get_current_user),
) -> Status:
    """
    Removes a song from the crate.
    """
    crate = await crud.get_crate_or_404(crate_id)
    crud.check_is_owner(crate, current_user)
    deleted = await CrateTracks.filter(crate_id=crate.id, song_id=song_id).delete()
    if not deleted:
        raise HTTPException(status_code=404, detail="Song is not in this crate")
    return Status(message=f"Removed song {song_id} from crate {crate_id}")


@router.post("/crates/{crate_id}/export", response_model=JobOut, status_code=202)
async def export_crate_for_dj(
    crate_id: int,
    export_in: ExportRequest,
    request: Request,
    current_user: UserOutSchema = Depends(get_current_user),
) -> JobOut:
    """
    Builds a USB-ready bundle of the crate for Serato, Traktor or rekordbox
    (MOO-86) as a background job; poll it at GET /exports/{job_id} and pull the
    ZIP from its download_url. Same read access as viewing the crate -- a
    bundle only ever contains tracks the caller can already stream.
    """
    crate = await crud.get_crate_or_404(crate_id)
    crud.check_can_read(crate, current_user)

    fmt = export_in.format or crate.dj_target
    if not fmt:
        raise HTTPException(
            status_code=422, detail="Pick a target DJ software for this crate first"
        )

    track_count = await CrateTracks.filter(crate_id=crate.id).count()
    if track_count == 0:
        raise HTTPException(status_code=422, detail="Crate has no tracks")
    if track_count > bundle.export_max_tracks():
        raise HTTPException(
            status_code=422,
            detail="Crates over {} tracks are too large to export".format(
                bundle.export_max_tracks()
            ),
        )

    active = await Jobs.filter(
        kind="export_crate",
        created_by_id=current_user.id,
        status__in=["queued", "running"],
    ).count()
    if active >= MAX_ACTIVE_EXPORTS:
        raise HTTPException(
            status_code=409,
            detail="You already have {} exports in progress".format(MAX_ACTIVE_EXPORTS),
        )
    await rate_limit("export_crate", str(current_user.id), 10, 3600)

    sizes = await Songs.filter(crate_tracks__crate_id=crate.id).values_list(
        "file_size_bytes", flat=True
    )
    volume_label = export_in.volume_label
    job = await submit_job(
        "export_crate",
        payload={
            "crate_id": crate.id,
            "format": fmt,
            "volume_label": volume_label,
            "rekordbox_root": export_in.rekordbox_root
            or "/Volumes/{}".format(volume_label),
            "estimated_size_bytes": int(sum(size or 0 for size in sizes)),
        },
        user_id=current_user.id,
    )
    await audit.audit_event(
        audit.EXPORT_REQUESTED,
        request=request,
        actor=current_user,
        target_type="crate",
        target_id=crate.id,
        detail={"format": fmt, "track_count": track_count},
    )
    events.export_crate(current_user, crate.id, fmt, track_count)
    return JobOut.from_orm(job)


@router.get("/crates/{crate_id}/export.m3u")
async def export_crate_m3u(
    crate_id: int,
    request: Request,
    current_user: UserOutSchema = Depends(get_current_user),
):
    """
    Exports the crate as an extended M3U playlist whose entries point at
    the songs' download URLs. Same read access as viewing the crate. Walks
    the membership in batches so an export never loads a huge crate at once.
    """
    crate = await crud.get_crate_or_404(crate_id)
    crud.check_can_read(crate, current_user)
    base_url = str(request.base_url)
    lines = ["#EXTM3U"]
    track_count = 0
    async for membership in crud.crate_tracks(crate):
        song = membership.song
        duration = int(round(song.duration_seconds or 0))
        title = " - ".join(part for part in (song.artist, song.title) if part)
        lines.append(f"#EXTINF:{duration},{title or 'Unknown'}")
        lines.append(f"{base_url}songs/{song.id}/download")
        track_count += 1
    events.export_crate(current_user, crate.id, "m3u", track_count)
    content = "\n".join(lines) + "\n"
    filename = _UNSAFE_FILENAME.sub("_", f"{crate.name}.m3u")
    return Response(
        content=content,
        media_type="audio/x-mpegurl",
        headers={
            "Content-Disposition": "attachment; filename*=utf-8''{}".format(
                quote(filename)
            )
        },
    )
