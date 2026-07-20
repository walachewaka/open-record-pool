"""
Pass-1 technical extraction (MOO-87 D3): container/codec facts, embedded-art
facts, and the full raw tag dump, all from mutagen + stdlib -- milliseconds
per file, no subprocesses, safe to run inside the scan/upload paths and in
the Python 3.7 harness venv. Never raises: any parse error degrades to the
null/default dict, a broken tag frame must never fail an ingestion.
"""
import struct

import mutagen

# Tag-dump bounds: frame values are truncated and the frame count is capped
# so a pathological file cannot bloat the tags_json JSONB column.
MAX_TAG_FRAMES = 200
MAX_TAG_VALUE_CHARS = 2000

# type(mutagen.File(...)).__name__.lower() -> container name where the codec
# name alone is ambiguous. Everything else falls back to the codec itself.
_CONTAINERS = {
    "mp3": "mpeg",
    "easymp3": "mpeg",
    "aiff": "aiff",
    "wave": "wav",
    "flac": "flac",
    "oggvorbis": "ogg",
    "oggopus": "ogg",
    "mp4": "mp4",
}


def art_dimensions(data):
    """
    (width, height) of a JPEG or PNG byte payload via a pure-python header
    parse (PNG IHDR / JPEG SOF marker scan), or None when unparseable.
    """
    if not data or len(data) < 24:
        return None
    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            width, height = struct.unpack(">II", data[16:24])
            return (int(width), int(height))
        if data[:2] == b"\xff\xd8":
            offset = 2
            size = len(data)
            while offset + 9 < size:
                if data[offset] != 0xFF:
                    offset += 1
                    continue
                marker = data[offset + 1]
                if marker == 0xFF:  # padding
                    offset += 1
                    continue
                if 0xD0 <= marker <= 0xD9 or marker == 0x01:  # standalone
                    offset += 2
                    continue
                body, body_end = offset + 2, offset + 4
                length = struct.unpack(">H", data[body:body_end])[0]
                if marker in (0xC0, 0xC1, 0xC2, 0xC3):  # SOF0-3
                    sof, sof_end = offset + 5, offset + 9
                    height, width = struct.unpack(">HH", data[sof:sof_end])
                    return (int(width), int(height))
                offset += 2 + length
    except Exception:
        return None
    return None


def _bitrate_mode(info):
    """ "cbr"/"vbr" from mutagen's BitrateMode enum, None when unknown."""
    mode = getattr(info, "bitrate_mode", None)
    if mode is None:
        return None
    name = str(mode)  # e.g. "BitrateMode.CBR"
    if name.endswith("CBR"):
        return "cbr"
    if name.endswith("VBR") or name.endswith("ABR"):
        return "vbr"
    return None


def _encoder(info):
    """The encoder string ("LAME 3.100 -V0") mutagen derived, or None."""
    parts = []
    for attr in ("encoder_info", "encoder_settings"):
        value = getattr(info, attr, None)
        if value:
            parts.append(str(value).strip())
    text = " ".join(part for part in parts if part)
    return text[:120] or None


def _art_facts(tags):
    """Embedded album-art presence/format/dimensions/size (feeds MOO-82)."""
    facts = {
        "art_present": False,
        "art_format": None,
        "art_width": None,
        "art_height": None,
        "art_bytes": None,
    }
    pictures = []
    if tags is not None and hasattr(tags, "getall"):
        pictures = tags.getall("APIC")
    if not pictures:
        return facts
    picture = pictures[0]
    data = getattr(picture, "data", b"") or b""
    mime = str(getattr(picture, "mime", "") or "").lower()
    facts["art_present"] = True
    facts["art_bytes"] = len(data)
    if "png" in mime or data[:8] == b"\x89PNG\r\n\x1a\n":
        facts["art_format"] = "png"
    elif "jpeg" in mime or "jpg" in mime or data[:2] == b"\xff\xd8":
        facts["art_format"] = "jpeg"
    dimensions = art_dimensions(data)
    if dimensions is not None:
        facts["art_width"], facts["art_height"] = dimensions
    return facts


def _tag_dump(tags):
    """
    The full raw tag dump as {frame_id: text} -- every frame including
    custom TXXX ones (frame keys like "TXXX:desc" keep the description),
    values truncated, frame count capped, always JSON-serializable.
    NUL characters are stripped: binary frames (PRIV, APIC digests, ...)
    stringify with embedded \\x00 and PostgreSQL JSONB rejects \\u0000.
    """
    if tags is None:
        return None
    dump = {}
    try:
        for key in tags.keys():
            if len(dump) >= MAX_TAG_FRAMES:
                break
            try:
                value = str(tags[key]).replace("\x00", "")
            except Exception:
                continue
            dump[str(key).replace("\x00", "")[:100]] = value[:MAX_TAG_VALUE_CHARS]
    except Exception:
        return dump or None
    return dump or None


def extract_technical(file_path):
    """
    The pass-1 technical dict for one audio file, keys matching the
    track_analysis pass-1 columns. Never raises; unparseable files yield
    the all-null dict so ingestion continues.
    """
    record = {
        "codec": None,
        "container": None,
        "sample_rate_hz": None,
        "channels": None,
        "bitrate_mode": None,
        "encoder": None,
        "art_present": False,
        "art_format": None,
        "art_width": None,
        "art_height": None,
        "art_bytes": None,
        "tags_json": None,
    }
    try:
        audio = mutagen.File(str(file_path))
        if audio is None:
            return record
        codec = type(audio).__name__.lower() or None
        record["codec"] = codec
        record["container"] = _CONTAINERS.get(codec, codec)
        info = getattr(audio, "info", None)
        if info is not None:
            sample_rate = getattr(info, "sample_rate", None)
            channels = getattr(info, "channels", None)
            record["sample_rate_hz"] = int(sample_rate) if sample_rate else None
            record["channels"] = int(channels) if channels else None
            record["bitrate_mode"] = _bitrate_mode(info)
            record["encoder"] = _encoder(info)
        tags = getattr(audio, "tags", None)
        record.update(_art_facts(tags))
        record["tags_json"] = _tag_dump(tags)
    except Exception as error:
        print("[analysis] technical pass failed for {}: {}".format(file_path, error))
    return record
