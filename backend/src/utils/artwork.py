"""
Album-art intake and normalization (MOO-82).

Every image that enters the pool -- an admin upload, a Beatport candidate, the
APIC frame already embedded in a file -- goes through normalize(): sniffed by
magic bytes (never by filename or Content-Type), decoded under a bomb guard,
re-encoded to a plain RGB JPEG of at most MAX_EDGE px, and stored
content-addressed under /library/art. Re-encoding is the point: it strips EXIF
and any payload smuggled behind a valid image header, and it is what keeps the
garbage 3000x3000 scans DJs complain about out of the library.

The /music volume is read-only, so nothing here ever writes an APIC frame back
into a file: the normalized copy is the pool's display art and lives in the
database (songs.artwork_path). Embedding is MOO-75's job.
"""
import hashlib
import io
import os

from fastapi import HTTPException
from PIL import Image

from src.utils import storage

MAX_EDGE = 1400
MAX_UPLOAD_BYTES = int(os.environ.get("ART_MAX_UPLOAD_MB", "10")) * 1024 * 1024
JPEG_QUALITY = 87

# A 50 MP ceiling: comfortably above any real cover, far below the pixel counts
# a decompression bomb needs to exhaust memory.
Image.MAX_IMAGE_PIXELS = 50_000_000


def sniff(data):
    """The image type by magic bytes, or None when it is not one we accept."""
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    return None


def normalize(data):
    """
    Re-encode raw image bytes to a normalized cover JPEG.

    Returns (jpeg_bytes, width, height). Raises 413 when the input is over the
    upload cap, 422 when it is not a JPEG/PNG or cannot be decoded.
    """
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Image is too large (max {} MiB)".format(
                MAX_UPLOAD_BYTES // (1024 * 1024)
            ),
        )
    if sniff(data) is None:
        raise HTTPException(
            status_code=422, detail="Album art must be a JPEG or PNG image"
        )
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Image.DecompressionBombError:
        raise HTTPException(status_code=422, detail="Album art has too many pixels")
    except Exception:
        raise HTTPException(status_code=422, detail="Album art could not be decoded")

    if image.mode != "RGB":
        image = image.convert("RGB")
    if max(image.size) > MAX_EDGE:
        image.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)
    out = io.BytesIO()
    image.save(
        out, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True
    )
    return out.getvalue(), image.width, image.height


async def store(data):
    """
    Normalize and store an image under /library/art, addressed by the hash of
    the NORMALIZED bytes (so the same cover picked twice reuses one file).

    Returns (path, width, height).
    """
    jpeg, width, height = normalize(data)
    sha256_hex = hashlib.sha256(jpeg).hexdigest()
    path = await storage.store_artifact_bytes(jpeg, sha256_hex, kind="art", ext="jpg")
    return path, width, height


def embedded_art(file_path):
    """
    The bytes of the first front-cover APIC frame of a file, or None. Read-only
    -- opening a /music file to read its art never mutates it.
    """
    import mutagen

    try:
        audio = mutagen.File(file_path)
        frames = audio.tags.getall("APIC") if audio and audio.tags else []
    except Exception:
        return None
    if not frames:
        return None
    # Prefer the front cover (APIC type 3) when the file carries several.
    front = [f for f in frames if getattr(f, "type", 3) == 3]
    frame = (front or frames)[0]
    return bytes(frame.data) or None
