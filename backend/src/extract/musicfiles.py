#!/usr/bin/env python3
"""
Extract the information about the music files.

The music volume is mounted read-only: this module only ever reads from it.
"""

import hashlib
import os
import re

import aiofiles
import mutagen
from mutagen.easyid3 import EasyID3

from src.analysis.technical import extract_technical
from src.utils.normalize import normalize_artist, normalize_title

# Constant for the volume where the music files are.
# Overridable via the environment, e.g. for tests.
MUSIC_PATH = os.environ.get("MUSIC_PATH", "/music")

# The separate, writable volume that admin uploads land on (MOO-71). The
# /music volume is read-only and only ever read by extraction; uploaded files
# are written here instead and served from here.
UPLOAD_PATH = os.environ.get("UPLOAD_PATH", "/uploads")

# EasyID3 does not map the musical key frame (TKEY) by default. We store it
# because record pools browse by key (#6).
if "initialkey" not in EasyID3.valid_keys:
    EasyID3.RegisterTextKey("initialkey", "TKEY")

# The publisher frame (TPUB) holds the record label (MOO-94). EasyID3 maps it
# as "organization" by default; register it defensively like TKEY above.
if "organization" not in EasyID3.valid_keys:
    EasyID3.RegisterTextKey("organization", "TPUB")

_YEAR_PATTERN = re.compile(r"(\d{4})")

# Full-fidelity ID3 capture bounds (MOO-79): TXXX frames are user-defined and
# unbounded in the wild, so the sanitized {desc: text} dict is capped hard --
# the ES mapping stores it as a single `flattened` field either way.
MAX_TXXX_FRAMES = 32
MAX_TXXX_DESC_CHARS = 64
MAX_TXXX_VALUE_CHARS = 512
_TXXX_DESC_PATTERN = re.compile(r"[^a-z0-9]+")


async def get_checksum_for_file(file_name):
    """
    Gets the MD5 checksum for a file, reading it in chunks.
    """
    digest = hashlib.md5()
    async with aiofiles.open(file_name, mode="rb") as f:
        while True:
            chunk = await f.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _iter_music_tree(target_dir):
    """
    Recursively yields the absolute paths of the MP3 files under [target_dir]
    in per-directory sorted order (files of a directory first, then its
    subdirectories). os.scandir streams the tree with O(depth) memory — the
    old glob("**/*") built the whole multi-million-entry tree in memory and
    sorted it before yielding anything (MOO-77).
    """
    try:
        entries = sorted(os.scandir(target_dir), key=lambda entry: entry.name)
    except OSError:
        return
    subdirs = []
    for entry in entries:
        try:
            if entry.is_dir(follow_symlinks=False):
                subdirs.append(entry.path)
            elif entry.is_file() and entry.name.lower().endswith(".mp3"):
                yield os.path.abspath(entry.path)
        except OSError:
            continue
    for subdir in subdirs:
        for path in _iter_music_tree(subdir):
            yield path


def _first_tag(tags, key):
    """
    Returns the first value of an EasyID3 tag, stripped, or None.
    """
    values = tags.get(key) if tags is not None else None
    if not values:
        return None
    value = str(values[0]).strip()
    return value or None


def _parse_year(value):
    """
    Extracts the year from a date tag like "2003" or "2003-04-01".
    """
    if not value:
        return None
    match = _YEAR_PATTERN.search(value)
    return int(match.group(1)) if match else None


def _parse_int(value):
    """
    Parses an integer tag, tolerating "5/12"-style track numbers.
    """
    if not value:
        return None
    try:
        return int(value.split("/")[0])
    except ValueError:
        return None


def _parse_float(value):
    """
    Parses a float tag such as the BPM.
    """
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def build_dedup_key(record):
    """
    The duplicate key for a song (#9).

    Two files are considered the same song when their artist and title tags
    match (case- and whitespace-insensitively) and their durations round to
    the same second. When either tag is missing, we fall back to the file's
    MD5 checksum, so only bit-identical untagged files count as duplicates.
    """
    artist = (record["artist"] or "").strip().lower()
    title = (record["title"] or "").strip().lower()
    if artist and title:
        duration = record["duration_seconds"] or 0.0
        raw = "\x00".join([artist, title, str(int(round(duration)))])
        return "tag:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()
    return "md5:" + record["checksum_md5"]


def _sanitize_txxx(frames):
    """
    TXXX frames as a bounded, sanitized {desc: text} dict (MOO-79): desc
    lowercased, non-alphanumerics collapsed to "_", trimmed; values coerced
    to str and trimmed; empty/binary frames dropped; at most 32 frames.
    """
    result = {}
    for frame in frames:
        if len(result) >= MAX_TXXX_FRAMES:
            break
        desc = str(getattr(frame, "desc", "") or "").strip()[:MAX_TXXX_DESC_CHARS]
        desc = _TXXX_DESC_PATTERN.sub("_", desc.lower()).strip("_")
        texts = getattr(frame, "text", None) or []
        value = texts[0] if texts else ""
        if not isinstance(value, str):
            continue  # binary/odd payloads are dropped, never coerced
        value = value.strip()[:MAX_TXXX_VALUE_CHARS]
        if desc and value and desc not in result:
            result[desc] = value
    return result or None


def _extract_extended_id3(file_name, easy_tags):
    """
    The second, raw-ID3 extraction pass (MOO-79): album artist, composer,
    disc number, first COMM comment, artwork presence, codec, and sanitized
    TXXX frames. Any parse error yields the null/default dict -- extended
    capture must never fail a scan.
    """
    record = {
        "album_artist": None,
        "composer": None,
        "comment": None,
        "disc_number": None,
        "codec": None,
        "has_artwork": False,
        "txxx_frames": None,
    }
    try:
        record["album_artist"] = _first_tag(easy_tags, "albumartist")
        record["composer"] = _first_tag(easy_tags, "composer")
        record["disc_number"] = _parse_int(_first_tag(easy_tags, "discnumber"))
        raw_file = mutagen.File(file_name)
        if raw_file is None:
            return record
        record["codec"] = type(raw_file).__name__.lower() or None
        tags = getattr(raw_file, "tags", None)
        if tags is None or not hasattr(tags, "getall"):
            return record
        for comm in tags.getall("COMM"):
            texts = getattr(comm, "text", None) or []
            text = str(texts[0]).strip() if texts else ""
            if text:
                record["comment"] = text
                break
        record["has_artwork"] = bool(tags.getall("APIC"))
        record["txxx_frames"] = _sanitize_txxx(tags.getall("TXXX"))
    except Exception as error:
        print(f"[extract] extended ID3 pass failed for {file_name}: {error}")
    return record


async def extract_music_file_info(file_name):
    """
    Extracts the information about one music file: the MP3 tags, the audio
    properties, and the file's checksum. Returns a dict whose keys match the
    fields of the Songs model. size/mtime are recorded BEFORE the hashing so
    the unchanged-file fast path (MOO-77) errs toward re-reading a file that
    changes mid-scan, never toward skipping it.
    """
    file_name = str(file_name)
    file_size = os.path.getsize(file_name)
    file_mtime = os.path.getmtime(file_name)
    checksum = await get_checksum_for_file(file_name)
    # FIXME: Use a aiofiles file-like object for mutagen
    mutagen_file = mutagen.File(file_name, easy=True)
    info = getattr(mutagen_file, "info", None)
    duration = round(info.length, 3) if info and info.length else None
    bitrate = int(info.bitrate / 1000) if info and getattr(info, "bitrate", 0) else None
    record = {
        "title": _first_tag(mutagen_file, "title"),
        "artist": _first_tag(mutagen_file, "artist"),
        "album": _first_tag(mutagen_file, "album"),
        "genre": _first_tag(mutagen_file, "genre"),
        "label": _first_tag(mutagen_file, "organization"),
        "year": _parse_year(_first_tag(mutagen_file, "date")),
        "track_number": _parse_int(_first_tag(mutagen_file, "tracknumber")),
        "bpm": _parse_float(_first_tag(mutagen_file, "bpm")),
        "musical_key": _first_tag(mutagen_file, "initialkey"),
        "isrc": _first_tag(mutagen_file, "isrc"),  # TSRC (MOO-82)
        "duration_seconds": duration,
        "bitrate_kbps": bitrate,
        "file_path": file_name,
        "file_size_bytes": file_size,
        "file_mtime": file_mtime,
        "checksum_md5": checksum,
    }
    record.update(_extract_extended_id3(file_name, mutagen_file))
    record["dedup_key"] = build_dedup_key(record)
    # Normalized recording identity (MOO-90 D4): denormalized onto the songs
    # row so the dedup candidate prefilter stays indexed.
    record["artist_norm"] = normalize_artist(record["artist"])
    record["title_norm"] = normalize_title(record["title"])[0]
    # Analyzer pass 1 (MOO-87): container/art/tag-dump facts, mutagen-only,
    # rides the full-read path (the unchanged fast path never gets here).
    # NOT a Songs column: callers pop it and hand it to
    # src.analysis.dispatch.ensure_analysis_row.
    record["technical"] = extract_technical(file_name)
    return record


async def scan_music_files(known=None):
    """
    Extracts the information about all the music files under MUSIC_PATH,
    yielding one record per readable MP3 file. Files that cannot be parsed
    are skipped with a warning.

    [known] is an optional {file_path: (size_bytes, mtime)} map of what the
    database already holds. A file whose size AND mtime both match yields
    {"file_path": ..., "unchanged": True} WITHOUT reading the file — no MD5,
    no tag parsing — which makes a no-change rescan of a million-file library
    O(stat) instead of O(bytes) (MOO-77).
    """
    for file_name in _iter_music_tree(MUSIC_PATH):
        if known is not None:
            fingerprint = known.get(file_name)
            if fingerprint is not None:
                try:
                    stat = os.stat(file_name)
                except OSError:
                    continue
                size, mtime = fingerprint
                if (
                    size is not None
                    and mtime is not None
                    and stat.st_size == size
                    and stat.st_mtime == mtime
                ):
                    yield {"file_path": file_name, "unchanged": True}
                    continue
        try:
            yield await extract_music_file_info(file_name)
        except Exception as error:
            print(f"[extract] skipping unreadable file {file_name}: {error}")
