"""
Serato .crate writer (MOO-86).

The crate file is an undocumented but stable TLV stream (as reverse-engineered
by serato-tools / pyserato / the Deep Symmetry notes). We only WRITE it, which
is ~40 lines of struct, so we take no dependency:

    field = tag (4 ASCII bytes) + length (big-endian uint32) + payload
    string payloads are UTF-16BE, no BOM, no terminator
    container payloads are their child fields concatenated

    vrsn   "1.0/Serato ScratchLive Crate"
    osrt   default sort column
    ovct   one per displayed column
    otrk   one per track, holding a ptrk path

ptrk paths are RELATIVE to the root of the drive the crate lives on, with
forward slashes and no leading slash ("Music/01 Artist - Title.mp3") -- that
is what makes a stick work regardless of drive letter or mount point. Serato
rebuilds "_Serato_/database V2" itself on first read, so we never write one:
a malformed database is worse than no database.
"""
import struct

VERSION = "1.0/Serato ScratchLive Crate"
COLUMNS = ("song", "artist", "bpm", "key", "year", "added")


def _field(tag, payload):
    return tag.encode("ascii") + struct.pack(">I", len(payload)) + payload


def _string_field(tag, value):
    return _field(tag, value.encode("utf-16-be"))


def build_crate(track_relpaths):
    """The bytes of a .crate listing [track_relpaths] in order. Pure."""
    out = [_string_field("vrsn", VERSION)]
    out.append(_field("osrt", _string_field("tvcn", "song") + _field("brev", b"\x00")))
    for column in COLUMNS:
        out.append(
            _field("ovct", _string_field("tvcn", column) + _string_field("tvcw", "0"))
        )
    for relpath in track_relpaths:
        out.append(_field("otrk", _string_field("ptrk", relpath)))
    return b"".join(out)
