"""
rekordbox.xml writer (MOO-86).

The DJ_PLAYLISTS 1.0.0 XML collection is rekordbox's documented import path
(Preferences -> Advanced -> Database -> rekordbox xml), and the reliable one:
writing a PIONEER/ device database (.pdb) means emitting an undocumented binary
that a CDJ will happily refuse or corrupt, so that is deliberately out of scope.

rekordbox Location URIs are ABSOLUTE, so the bundle is built for a root the
user tells us about ("/Volumes/ORP_USB" on macOS, "E:" on Windows) -- see
[rekordbox_root]. Playlist entries reference collection tracks by TrackID.
Tonality is standard notation ("Am"), unlike Traktor's Open Key.
"""
from urllib.parse import quote
from xml.etree import ElementTree as ET

from src.utils.keys import key_forms

KIND_BY_EXT = {
    "mp3": "MP3 File",
    "wav": "WAV File",
    "aiff": "AIFF File",
    "aif": "AIFF File",
    "flac": "FLAC File",
    "m4a": "M4A File",
}


def _set(element, name, value):
    if value not in (None, ""):
        element.set(name, str(value))


def location_uri(rekordbox_root, filename):
    """file://localhost/<root>/Music/<file>, percent-encoded (spaces -> %20)."""
    root = rekordbox_root.rstrip("/")
    if not root.startswith("/"):  # a Windows drive: "E:" -> "/E:"
        root = "/" + root
    return "file://localhost" + quote("{}/Music/{}".format(root, filename), safe="/:")


def build_rekordbox_xml(crate_name, entries, rekordbox_root):
    """The bytes of a rekordbox.xml holding [entries] as one playlist. Pure."""
    root = ET.Element("DJ_PLAYLISTS", {"Version": "1.0.0"})
    ET.SubElement(
        root,
        "PRODUCT",
        {"Name": "rekordbox", "Version": "6.0.0", "Company": "AlphaTheta"},
    )

    collection = ET.SubElement(root, "COLLECTION", {"Entries": str(len(entries))})
    for track_id, entry in enumerate(entries, start=1):
        ext = entry["filename"].rsplit(".", 1)[-1].lower()
        track = ET.SubElement(collection, "TRACK", {"TrackID": str(track_id)})
        _set(track, "Name", entry.get("title") or entry["filename"])
        _set(track, "Artist", entry.get("artist"))
        _set(track, "Album", entry.get("album"))
        _set(track, "Genre", entry.get("genre"))
        _set(track, "Kind", KIND_BY_EXT.get(ext, ext.upper() + " File"))
        _set(track, "Size", entry.get("size_bytes"))
        if entry.get("duration_seconds"):
            _set(track, "TotalTime", int(round(entry["duration_seconds"])))
        _set(track, "Year", entry.get("year"))
        if entry.get("bpm"):
            _set(track, "AverageBpm", "{:.2f}".format(float(entry["bpm"])))
        _set(track, "BitRate", entry.get("bitrate_kbps"))
        _set(track, "SampleRate", entry.get("sample_rate_hz"))
        keys = key_forms(entry.get("key"))
        if keys:
            _set(track, "Tonality", keys["standard"])
        _set(track, "TrackNumber", entry.get("position"))
        track.set("Location", location_uri(rekordbox_root, entry["filename"]))

    playlists = ET.SubElement(root, "PLAYLISTS")
    node_root = ET.SubElement(
        playlists, "NODE", {"Type": "0", "Name": "ROOT", "Count": "1"}
    )
    node = ET.SubElement(
        node_root,
        "NODE",
        {
            "Name": crate_name,
            "Type": "1",
            "KeyType": "0",
            "Entries": str(len(entries)),
        },
    )
    for track_id in range(1, len(entries) + 1):
        ET.SubElement(node, "TRACK", {"Key": str(track_id)})

    document = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        root, encoding="unicode"
    )
    return document.encode("utf-8")
