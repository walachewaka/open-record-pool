"""
The managed, sharded, content-addressed /library volume (MOO-77).

All new audio/artifact files are written here — never into flat directories,
never onto the read-only /music volume. Layout (binding for downstream
stages, see docs/ARCHITECTURE.md):

    /library/audio/<sha256[0:2]>/<sha256[2:4]>/<sha256>.<ext>
    /library/art/<aa>/<bb>/<sha256>.jpg
    /library/waveform/<aa>/<bb>/<sha256>.json

Two shard levels give 65 536 leaf directories; at 5M files that is ~76 files
per leaf. Writes are atomic: stream to /library/tmp/<uuid4>, then os.replace()
into the sharded path (same filesystem).
"""
import hashlib
import os
import uuid

import aiofiles

LIBRARY_PATH = os.environ.get("LIBRARY_PATH", "/library")

_CHUNK = 1024 * 1024


def sharded_path(sha256_hex, ext, kind="audio"):
    """
    The absolute sharded path for a content hash:
    <LIBRARY_PATH>/<kind>/<aa>/<bb>/<sha256>.<ext>.
    """
    ext = ext.lstrip(".").lower() or "bin"
    return os.path.join(
        LIBRARY_PATH, kind, sha256_hex[0:2], sha256_hex[2:4], sha256_hex + "." + ext
    )


def artifact_path(sha256_hex, ext, kind):
    """
    Read-side resolver for a derived artifact (e.g. the MOO-87 waveform
    peaks JSON): the sharded path the artifact was stored at. Purely
    content-addressed -- no user-supplied name ever reaches the path.
    """
    return sharded_path(sha256_hex, ext, kind=kind)


async def store_artifact_bytes(data, sha256_hex, kind, ext):
    """
    Atomically store a small derived artifact (MOO-87 waveform peaks, later
    MOO-82 art) under the CONTENT HASH OF ITS SOURCE FILE [sha256_hex] --
    unlike store_stream, the payload is not self-addressed, so re-analysis
    of the same source overwrites in place. tmp + os.replace like all
    /library writes. Returns the final path.
    """
    tmp_dir = os.path.join(LIBRARY_PATH, "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_path = os.path.join(tmp_dir, uuid.uuid4().hex)
    final_path = sharded_path(sha256_hex, ext, kind=kind)
    try:
        async with aiofiles.open(tmp_path, "wb") as out:
            await out.write(data)
        os.makedirs(os.path.dirname(final_path), exist_ok=True)
        os.replace(tmp_path, final_path)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise
    return final_path


async def store_stream(reader, ext, kind="audio"):
    """
    Streams [reader] (any object with `await read(n)`, e.g. an UploadFile)
    into the sharded tree, hashing incrementally. Returns
    (final_path, sha256_hex, size_bytes). Never reads the payload into memory
    and never leaves partial files at the final path: data lands in
    /library/tmp first and is os.replace()d into place.
    """
    tmp_dir = os.path.join(LIBRARY_PATH, "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_path = os.path.join(tmp_dir, uuid.uuid4().hex)
    digest = hashlib.sha256()
    size = 0
    try:
        async with aiofiles.open(tmp_path, "wb") as out:
            while True:
                chunk = await reader.read(_CHUNK)
                if not chunk:
                    break
                digest.update(chunk)
                size += len(chunk)
                await out.write(chunk)
        sha256_hex = digest.hexdigest()
        final_path = sharded_path(sha256_hex, ext, kind=kind)
        os.makedirs(os.path.dirname(final_path), exist_ok=True)
        os.replace(tmp_path, final_path)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise
    return final_path, sha256_hex, size
