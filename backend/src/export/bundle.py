"""
Bundle assembly: crate -> USB-ready ZIP (MOO-86).

One export = one crate + one target software = one ZIP whose internal layout is
what that software expects at the ROOT of a stick. The user extracts it there;
the server never sees the stick, so a ZIP download is the delivery.

    Music/01 Artist - Title.mp3        (all three formats)
    _Serato_/Subcrates/<Crate>.crate   (serato)
    <Crate>.nml                        (traktor)
    rekordbox.xml                      (rekordbox)
    EXPORT_README.txt                  (all three)

Scratch space is bounded to ONE track: copy the source into /library/tmp, fix
its tags there, stream it into the ZIP, delete it. A 40 GB crate never needs
40 GB of temp. Audio is stored uncompressed (ZIP_STORED) -- MP3 does not
deflate, and skipping it keeps a big export CPU-cheap.

Source files are resolved against the same three serving roots the download
route allows; anything outside them (or missing on disk) is SKIPPED and
reported, never fetched.
"""
import os
import shutil
import time
import zipfile
from datetime import datetime, timedelta, timezone

from mutagen import File as MutagenFile

import src.crud.crates as crates_crud
from src.export import naming, rekordbox, serato, tagging, traktor
from src.export.naming import FORMATS
from src.extract import musicfiles
from src.utils import storage

CHUNK = 1024 * 1024
DEFAULT_VOLUME_LABEL = "ORP_USB"


def export_max_tracks():
    return int(os.environ.get("EXPORT_MAX_TRACKS", "1000"))


def export_ttl_hours():
    return int(os.environ.get("EXPORT_TTL_HOURS", "24"))


def export_dir(job_id):
    return os.path.join(storage.LIBRARY_PATH, "export", str(job_id))


def _staging_dir(job_id):
    return os.path.join(storage.LIBRARY_PATH, "tmp", "export-{}".format(job_id))


def _allowed_roots():
    return (
        os.path.abspath(musicfiles.MUSIC_PATH),
        os.path.abspath(musicfiles.UPLOAD_PATH),
        os.path.abspath(storage.LIBRARY_PATH),
    )


def resolve_source(file_path):
    """
    The real path of a song's file when it lives on a served volume, else None
    (path traversal, a stale row, a file removed from disk). Symlinks are
    resolved BEFORE the containment check, so a symlink out of /music is not a
    way to reach /etc/passwd.
    """
    if not file_path:
        return None
    path = os.path.realpath(file_path)
    roots = [os.path.realpath(root) for root in _allowed_roots()]
    if not any(path.startswith(root + os.sep) for root in roots):
        return None
    if not os.path.isfile(path):
        return None
    return path


README = """Open Record Pool -- {crate} ({fmt} export)

WHAT THIS IS
  {tracks} track(s) with their metadata, laid out the way {fmt} expects to
  find them at the ROOT of a USB stick.

HOW TO USE IT
  1. Extract this ZIP to the root of your stick (not into a subfolder).
{instructions}

LIMITS
  * Tags, BPM and key travel with the files. Beatgrids, cue points and
    waveforms do NOT -- your DJ software analyzes the tracks on first load and
    reads our tags natively. (Any cue/grid data an original file already
    carried is preserved untouched.)
  * Non-MP3 files keep their original tags: we only rewrite ID3.
  * A single file over 4 GB needs an exFAT stick; FAT32 cannot store it.
"""

INSTRUCTIONS = {
    "serato": (
        "  2. Plug the stick in. Serato DJ scans _Serato_/Subcrates/ on every\n"
        "     attached drive and the crate shows up under the drive in the\n"
        "     crate panel -- no import step.\n"
    ),
    "traktor": (
        '  2. Name the stick "{volume}" (or use Traktor\'s right-click ->\n'
        "     Relocate once, which repoints every entry in one go).\n"
        "  3. Drag {crate}.nml onto Traktor's Playlists node to import it.\n"
    ),
    "rekordbox": (
        "  2. rekordbox -> Preferences -> Advanced -> Database -> rekordbox xml:\n"
        '     point "Imported Library" at rekordbox.xml on the stick.\n'
        "  3. The playlist appears under the rekordbox xml tree; drag it into\n"
        "     your collection or a device to import it.\n"
        "     (Built for the stick mounted at: {root})\n"
    ),
}


def readme_text(crate_name, fmt, track_count, volume_label, rekordbox_root):
    return README.format(
        crate=crate_name,
        fmt=fmt,
        tracks=track_count,
        instructions=INSTRUCTIONS[fmt].format(
            crate=naming.sanitize_component(crate_name, fallback="Crate"),
            volume=volume_label,
            root=rekordbox_root,
        ),
    )


def _technical(path):
    """(bitrate_kbps, sample_rate_hz) read off the staged copy; best-effort."""
    try:
        audio = MutagenFile(path)
        info = getattr(audio, "info", None)
        bitrate = getattr(info, "bitrate", None)
        return (
            int(bitrate / 1000) if bitrate else None,
            getattr(info, "sample_rate", None),
        )
    except Exception:
        return None, None


def _metadata_files(crate_name, fmt, entries, volume_label, rekordbox_root):
    """The format's playlist file(s): {arcname: bytes}."""
    safe_name = naming.sanitize_component(crate_name, fallback="Crate")
    relpaths = ["Music/" + entry["filename"] for entry in entries]
    if fmt == "serato":
        return {
            "_Serato_/Subcrates/{}.crate".format(safe_name): serato.build_crate(
                relpaths
            )
        }
    if fmt == "traktor":
        return {
            "{}.nml".format(safe_name): traktor.build_nml(
                safe_name, entries, volume_label
            )
        }
    return {
        "rekordbox.xml": rekordbox.build_rekordbox_xml(
            safe_name, entries, rekordbox_root
        )
    }


async def build_bundle(
    job, crate, fmt, volume_label, rekordbox_root, progress_cb=None, track_count=None
):
    """
    Assemble the crate's bundle and return the job result dict. Raises when the
    bundle cannot be produced at all (no readable track); individual unreadable
    tracks are skipped and reported.
    """
    if fmt not in FORMATS:
        raise ValueError("Unknown export format: {}".format(fmt))

    staging = _staging_dir(job.id)
    destination = export_dir(job.id)
    os.makedirs(staging, exist_ok=True)
    os.makedirs(destination, exist_ok=True)
    bundle_filename = naming.bundle_name(crate.name, fmt, crate.id)
    zip_path = os.path.join(destination, bundle_filename)

    entries = []
    skipped = []
    taken = set()
    done = 0

    try:
        with zipfile.ZipFile(
            zip_path, "w", compression=zipfile.ZIP_STORED, allowZip64=True
        ) as archive:
            position = 0
            async for membership in crates_crud.crate_tracks(crate):
                song = membership.song
                done += 1
                source = resolve_source(song.file_path)
                if source is None:
                    skipped.append(
                        {"song_id": song.id, "reason": "file not on a served volume"}
                    )
                    continue
                position += 1

                ext = os.path.splitext(source)[1]
                filename = naming.dedupe(
                    naming.track_filename(
                        position, song.artist, song.title, ext, song_id=song.id
                    ),
                    taken,
                )
                staged = os.path.join(staging, filename)
                try:
                    with open(source, "rb") as src, open(staged, "wb") as dst:
                        shutil.copyfileobj(src, dst, CHUNK)
                    tagging.retag_copy(staged, song, position, fmt)
                    bitrate, sample_rate = _technical(staged)
                    with open(staged, "rb") as src:
                        with archive.open("Music/" + filename, "w") as member:
                            shutil.copyfileobj(src, member, CHUNK)
                    size_bytes = os.path.getsize(staged)
                finally:
                    if os.path.exists(staged):
                        os.remove(staged)

                entries.append(
                    {
                        "filename": filename,
                        "position": position,
                        "title": song.title,
                        "artist": song.artist,
                        "album": song.album,
                        "genre": song.genre,
                        "year": song.year,
                        "bpm": tagging.track_bpm(song),
                        "key": tagging.track_key(song),
                        "duration_seconds": song.duration_seconds,
                        "bitrate_kbps": bitrate or song.bitrate_kbps,
                        "sample_rate_hz": sample_rate,
                        "size_bytes": size_bytes,
                    }
                )
                if progress_cb and track_count:
                    await progress_cb(done, track_count)

            if not entries:
                raise RuntimeError(
                    "None of this crate's files are readable on the library volumes"
                )

            for arcname, data in _metadata_files(
                crate.name, fmt, entries, volume_label, rekordbox_root
            ).items():
                archive.writestr(arcname, data, compress_type=zipfile.ZIP_DEFLATED)
            archive.writestr(
                "EXPORT_README.txt",
                readme_text(
                    crate.name, fmt, len(entries), volume_label, rekordbox_root
                ),
                compress_type=zipfile.ZIP_DEFLATED,
            )
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    return {
        "download_url": "/exports/{}/download".format(job.id),
        "bundle_filename": bundle_filename,
        "zip_size_bytes": os.path.getsize(zip_path),
        "track_count": len(entries),
        "skipped": skipped,
        "expires_at": (
            datetime.now(timezone.utc) + timedelta(hours=export_ttl_hours())
        ).isoformat(),
    }


def cleanup_expired(ttl_hours=None):
    """
    Drop export artifacts older than the TTL and any staging directory left
    behind by a crashed worker. Returns a small summary for the job log.
    """
    ttl_seconds = (ttl_hours or export_ttl_hours()) * 3600
    now = time.time()
    removed = 0

    export_root = os.path.join(storage.LIBRARY_PATH, "export")
    for name in os.listdir(export_root) if os.path.isdir(export_root) else []:
        path = os.path.join(export_root, name)
        try:
            if os.path.isdir(path) and now - os.path.getmtime(path) > ttl_seconds:
                shutil.rmtree(path, ignore_errors=True)
                removed += 1
        except OSError:
            continue

    tmp_root = os.path.join(storage.LIBRARY_PATH, "tmp")
    orphans = 0
    for name in os.listdir(tmp_root) if os.path.isdir(tmp_root) else []:
        if not name.startswith("export-"):
            continue
        path = os.path.join(tmp_root, name)
        try:
            if os.path.isdir(path) and now - os.path.getmtime(path) > 2 * 3600:
                shutil.rmtree(path, ignore_errors=True)
                orphans += 1
        except OSError:
            continue

    return {"expired_bundles": removed, "orphan_staging": orphans}
