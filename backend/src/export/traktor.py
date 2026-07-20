"""
Traktor .nml writer (MOO-86).

NML is Traktor's collection/playlist XML (VERSION 19). We emit a COLLECTION of
the bundled copies plus one PLAYLIST node, which the DJ drags into Traktor's
Playlists tree from the stick.

Traktor addresses a file as volume + directory + filename, where directory
segments are separated by "/:" -- so the entries stay portable as long as the
stick carries the volume label the bundle was built for (the README says so;
Traktor's "Relocate" fixes it in one click otherwise). A playlist entry's
PRIMARYKEY must byte-match its LOCATION's volume + dir + file, or Traktor
imports the playlist with every track greyed out.

Field semantics follow traktor-nml-utils; the writer is stdlib ElementTree, so
no dependency is added.
"""
import uuid
from xml.etree import ElementTree as ET

from src.utils.keys import key_forms

MUSIC_DIR = "/:Music/:"


def _set(element, name, value):
    """Set an attribute, but never an empty/None one -- Traktor prefers absence."""
    if value not in (None, ""):
        element.set(name, str(value))


def _entry(collection, entry, volume_label):
    node = ET.SubElement(collection, "ENTRY")
    _set(node, "ARTIST", entry.get("artist"))
    _set(node, "TITLE", entry.get("title") or entry["filename"])

    location = ET.SubElement(node, "LOCATION")
    location.set("DIR", MUSIC_DIR)
    location.set("FILE", entry["filename"])
    location.set("VOLUME", volume_label)
    location.set("VOLUMEID", volume_label)

    if entry.get("album"):
        album = ET.SubElement(node, "ALBUM")
        _set(album, "TITLE", entry["album"])

    keys = key_forms(entry.get("key"))
    info = ET.SubElement(node, "INFO")
    if entry.get("bitrate_kbps"):
        _set(info, "BITRATE", int(entry["bitrate_kbps"]) * 1000)
    _set(info, "GENRE", entry.get("genre"))
    if keys:
        _set(info, "KEY", keys["open_key"])
    if entry.get("duration_seconds"):
        _set(info, "PLAYTIME", int(round(entry["duration_seconds"])))
    if entry.get("year"):
        _set(info, "RELEASE_DATE", "{}/1/1".format(int(entry["year"])))

    if entry.get("bpm"):
        tempo = ET.SubElement(node, "TEMPO")
        tempo.set("BPM", "{:.6f}".format(float(entry["bpm"])))
        tempo.set("BPM_QUALITY", "100.000000")
    if keys:
        ET.SubElement(node, "MUSICAL_KEY").set("VALUE", str(keys["traktor_int"]))


def build_nml(crate_name, entries, volume_label, playlist_uuid=None):
    """The bytes of an .nml holding [entries] as one playlist. Pure."""
    nml = ET.Element("NML", {"VERSION": "19"})
    ET.SubElement(
        nml, "HEAD", {"COMPANY": "www.native-instruments.com", "PROGRAM": "Traktor"}
    )
    ET.SubElement(nml, "MUSICFOLDERS")

    collection = ET.SubElement(nml, "COLLECTION", {"ENTRIES": str(len(entries))})
    for entry in entries:
        _entry(collection, entry, volume_label)
    ET.SubElement(nml, "SETS", {"ENTRIES": "0"})

    playlists = ET.SubElement(nml, "PLAYLISTS")
    root = ET.SubElement(playlists, "NODE", {"TYPE": "FOLDER", "NAME": "$ROOT"})
    subnodes = ET.SubElement(root, "SUBNODES", {"COUNT": "1"})
    node = ET.SubElement(subnodes, "NODE", {"TYPE": "PLAYLIST", "NAME": crate_name})
    playlist = ET.SubElement(
        node,
        "PLAYLIST",
        {
            "ENTRIES": str(len(entries)),
            "TYPE": "LIST",
            "UUID": playlist_uuid or uuid.uuid4().hex,
        },
    )
    for entry in entries:
        item = ET.SubElement(playlist, "ENTRY")
        ET.SubElement(
            item,
            "PRIMARYKEY",
            {
                "TYPE": "TRACK",
                "KEY": "{}{}{}".format(volume_label, MUSIC_DIR, entry["filename"]),
            },
        )

    document = '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n' + ET.tostring(
        nml, encoding="unicode"
    )
    return document.encode("utf-8")
