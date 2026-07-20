"""
Filenames inside an export bundle (MOO-86).

Everything here is pure and defensive: crate and track names are user input,
and they end up as paths inside a ZIP that a DJ extracts onto a USB stick. No
name may escape the bundle root, contain a separator, or collide.
"""
import re

# Windows/FAT-hostile characters, path separators, control chars. "%%" is
# Serato's subcrate separator, so it is stripped too.
_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_WHITESPACE = re.compile(r"\s+")

FORMATS = ("serato", "traktor", "rekordbox")


def sanitize_component(name, fallback="Untitled", max_len=120):
    """One safe path component: no separators, no control chars, never empty."""
    text = _UNSAFE.sub(" ", str(name or "")).replace("%%", " ")
    text = _WHITESPACE.sub(" ", text).strip().strip(".").strip()
    text = text[:max_len].strip()
    return text or fallback


def track_filename(position, artist, title, ext, song_id=None):
    """
    "NN Artist - Title.ext" -- the 2-digit crate position keeps the DJ's
    order intact in any file manager.
    """
    stem = " - ".join(
        part
        for part in (sanitize_component(artist, ""), sanitize_component(title, ""))
        if part
    )
    if not stem:
        stem = "Track {}".format(song_id if song_id is not None else position)
    ext = _UNSAFE.sub("", str(ext or "")).lstrip(".").lower() or "mp3"
    return "{:02d} {}.{}".format(position, sanitize_component(stem), ext)


def dedupe(filename, taken):
    """A name unique within [taken] (a set, mutated): "x.mp3" -> "x (2).mp3"."""
    if filename not in taken:
        taken.add(filename)
        return filename
    stem, _, ext = filename.rpartition(".")
    counter = 2
    while True:
        candidate = "{} ({}).{}".format(stem, counter, ext)
        if candidate not in taken:
            taken.add(candidate)
            return candidate
        counter += 1


def bundle_name(crate_name, fmt, crate_id=None):
    """The ZIP's filename: "<Crate>_serato.zip"."""
    safe = sanitize_component(crate_name, fallback="Crate {}".format(crate_id or ""))
    return "{}_{}.zip".format(safe.strip() or "Crate", fmt)
