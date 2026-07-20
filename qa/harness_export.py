"""MOO-86 DJ crate export harness: Serato / Traktor / rekordbox USB bundles.

Runs inside the backend container against the live stack (like every other
harness), and additionally imports the pure writers from /app to unit-test the
key table and round-trip-parse a .crate.

Covers: key notation table, the three bundle layouts, ID3 rewrite on the copies
(GEOB preservation included), path confinement/skip, IDOR on poll + download,
and the request guards (422/409/404/410).
"""
import io
import struct
import sys
import time
import urllib.error
import urllib.request
import zipfile
from xml.etree import ElementTree as ET

sys.path.insert(0, "/app")

from qa_lib import BASE, check, login, request, summary  # noqa: E402

ADMIN_PW = "QaCheck2!pass"
USER_PW = "QaUser2!pass"
A = "qa2_alice"
B = "qa2_bob"


def get_bytes(path, token):
    """A raw (binary) GET -- qa_lib.request decodes as text."""
    req = urllib.request.Request(BASE + path)
    req.add_header("Cookie", "Authorization=Bearer " + token)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as err:
        return err.code, err.read(), dict(err.headers)


def parse_crate(blob):
    """Minimal Serato .crate TLV parser: [(tag, payload_bytes), ...]."""
    fields = []
    offset = 0
    while offset < len(blob):
        tag = blob[offset : offset + 4].decode("ascii")
        (length,) = struct.unpack(">I", blob[offset + 4 : offset + 8])
        payload = blob[offset + 8 : offset + 8 + length]
        fields.append((tag, payload))
        offset += 8 + length
    return fields


def crate_track_paths(blob):
    paths = []
    for tag, payload in parse_crate(blob):
        if tag != "otrk":
            continue
        for child_tag, child_payload in parse_crate(payload):
            if child_tag == "ptrk":
                paths.append(child_payload.decode("utf-16-be"))
    return paths


def run_export(token, crate_id, body):
    """Submit an export and poll it to a terminal state. Returns the job."""
    status, job, _ = request(
        "POST", "/crates/{}/export".format(crate_id), token=token, body=body
    )
    if status != 202 or not isinstance(job, dict):
        return status, job
    for _ in range(240):
        if job.get("status") in ("succeeded", "failed", "cancelled"):
            return status, job
        time.sleep(1)
        _s, job, _h = request("GET", "/exports/{}".format(job["id"]), token=token)
    return status, job


def unit_keys():
    from src.utils.keys import KEY_FORMS, key_forms

    check(
        "MOO-86 keys: the wheel table is complete (24 positions)",
        len(KEY_FORMS) == 24,
        "rows={}".format(len(KEY_FORMS)),
    )
    forms = key_forms("Am")
    check(
        "MOO-86 keys: Am -> 8A / 1m / Traktor 21",
        forms
        and forms["camelot"] == "8A"
        and forms["open_key"] == "1m"
        and forms["traktor_int"] == 21,
        str(forms),
    )
    check(
        "MOO-86 keys: Camelot input round-trips (5A -> Cm / 10m / 12)",
        key_forms("5A")
        == {
            "camelot": "5A",
            "standard": "Cm",
            "open_key": "10m",
            "traktor_int": 12,
        },
        str(key_forms("5A")),
    )
    check(
        "MOO-86 keys: unknown notation is None, never an exception",
        key_forms("banana") is None and key_forms(None) is None,
        "",
    )
    # Every Traktor int is distinct and inside 0-23; every Open Key is distinct.
    ints = sorted(v[2] for v in KEY_FORMS.values())
    check(
        "MOO-86 keys: Traktor ints are the full 0-23 chromatic set",
        ints == list(range(24)),
        str(ints),
    )


class FakeSong(object):
    """The handful of songs columns the tag writer reads."""

    id = 1
    title = "Retagged Title"
    artist = "Retagged Artist"
    album = "Retagged Album"
    genre = "Tech House"
    year = 2024
    bpm = 126.0
    musical_key = "Am"
    bpm_detected = None
    key_detected = None


def unit_bundle():
    """Path confinement and the tag rewrite, in-process against a real MP3."""
    import os
    import shutil
    import tempfile

    from mutagen.id3 import ID3, GEOB

    from src.export.bundle import resolve_source
    from src.export.tagging import retag_copy

    check(
        "MOO-86: a path outside the served roots never resolves",
        resolve_source("/etc/passwd") is None
        and resolve_source("/music/../etc/passwd") is None
        and resolve_source(None) is None,
        "",
    )
    check(
        "MOO-86: a missing file on a served root never resolves",
        resolve_source("/music/does-not-exist.mp3") is None,
        "",
    )

    source = None
    for root, _dirs, files in os.walk("/music"):
        for name in files:
            if name.lower().endswith(".mp3"):
                source = os.path.join(root, name)
                break
        if source:
            break
    if not source:
        return
    check(
        "MOO-86: a real /music file resolves to itself",
        resolve_source(source) == os.path.realpath(source),
        source,
    )

    staging = tempfile.mkdtemp()
    try:
        copy = os.path.join(staging, "copy.mp3")
        shutil.copyfile(source, copy)
        # Serato writes its cues/beatgrid into GEOB frames. We do not interpret
        # them -- but we must not destroy them either.
        tags = ID3(copy)
        tags.add(
            GEOB(
                encoding=0,
                mime="application/octet-stream",
                filename="",
                desc="Serato Markers2",
                data=b"QVBQTFRFU1QK",
            )
        )
        tags.save(copy)
        before = os.path.getmtime(source)

        retag_copy(copy, FakeSong(), 1, "serato")
        written = ID3(copy)
        check(
            "MOO-86: the copy carries the DB metadata after retag",
            str(written.get("TIT2")) == "Retagged Title"
            and str(written.get("TPE1")) == "Retagged Artist"
            and str(written.get("TBPM")) == "126.00"
            and str(written.get("TKEY")) == "8A",
            "TIT2={} TBPM={} TKEY={}".format(
                written.get("TIT2"), written.get("TBPM"), written.get("TKEY")
            ),
        )
        geobs = written.getall("GEOB")
        check(
            "MOO-86: Serato GEOB cue/beatgrid frames survive the retag",
            any(g.desc == "Serato Markers2" for g in geobs),
            "geob={}".format([g.desc for g in geobs]),
        )
        check(
            "MOO-86: the ORIGINAL /music file is never touched",
            os.path.getmtime(source) == before,
            source,
        )
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def main():
    admin, _ = login("admin", ADMIN_PW)
    check("auth: admin login", admin is not None)
    for name in (A, B):
        request(
            "POST",
            "/register",
            token=admin,
            body={"username": name, "password": USER_PW},
        )
    alice, _ = login(A, USER_PW)
    bob, _ = login(B, USER_PW)
    if not (admin and alice and bob):
        summary()
        return

    unit_keys()
    unit_bundle()

    # --- fixtures: a crate with a couple of real library tracks ---
    status, songs, _ = request("GET", "/songs", token=alice)
    items = songs.get("items", []) if isinstance(songs, dict) else songs
    song_ids = [s["id"] for s in items][:2]
    check("fixture: library songs available", len(song_ids) == 2, str(song_ids))
    if len(song_ids) < 2:
        summary()
        return

    status, crate, _ = request(
        "POST",
        "/crates",
        token=alice,
        body={"name": "MOO-86 Export QA", "dj_target": "serato"},
    )
    crate_id = crate.get("id") if isinstance(crate, dict) else None
    check(
        "MOO-86: crate creation accepts dj_target",
        status in (200, 201) and crate.get("dj_target") == "serato",
        "status={} dj_target={}".format(status, crate.get("dj_target")),
    )
    for song_id in song_ids:
        request(
            "POST",
            "/crates/{}/tracks".format(crate_id),
            token=alice,
            body={"song_id": song_id},
        )

    status, _, _ = request(
        "PATCH",
        "/crates/{}".format(crate_id),
        token=alice,
        body={"dj_target": "traktor"},
    )
    check("MOO-86: dj_target is switchable via PATCH", status == 200, str(status))
    request(
        "PATCH",
        "/crates/{}".format(crate_id),
        token=alice,
        body={"dj_target": "serato"},
    )

    # --- guards ---
    status, body, _ = request(
        "POST",
        "/crates/{}/export".format(crate_id),
        token=alice,
        body={"format": "virtualdj"},
    )
    check("MOO-86: unknown format -> 422", status == 422, str(status))
    status, _, _ = request(
        "POST",
        "/crates/{}/export".format(crate_id),
        token=alice,
        body={"format": "serato", "volume_label": "bad label!"},
    )
    check("MOO-86: bad volume_label -> 422", status == 422, str(status))
    status, _, _ = request(
        "POST",
        "/crates/{}/export".format(crate_id),
        token=alice,
        body={"format": "rekordbox", "rekordbox_root": "../../etc"},
    )
    check("MOO-86: bad rekordbox_root -> 422", status == 422, str(status))

    status, empty, _ = request(
        "POST", "/crates", token=alice, body={"name": "MOO-86 Empty"}
    )
    empty_id = empty.get("id")
    status, _, _ = request(
        "POST",
        "/crates/{}/export".format(empty_id),
        token=alice,
        body={"format": "serato"},
    )
    check("MOO-86: empty crate -> 422", status == 422, str(status))
    status, _, _ = request(
        "POST", "/crates/{}/export".format(empty_id), token=alice, body={}
    )
    check(
        "MOO-86: no format and no dj_target -> 422",
        status == 422,
        str(status),
    )
    request("DELETE", "/crates/{}".format(empty_id), token=alice)

    status, _, _ = request(
        "POST",
        "/crates/{}/export".format(crate_id),
        token=bob,
        body={"format": "serato"},
    )
    check(
        "MOO-86 IDOR: non-owner cannot export a private crate",
        status in (403, 404),
        str(status),
    )

    # --- the three bundles ---
    jobs = {}
    for fmt in ("serato", "traktor", "rekordbox"):
        body = {"format": fmt, "volume_label": "ORP_QA"}
        if fmt == "rekordbox":
            body["rekordbox_root"] = "/Volumes/ORP_QA"
        status, job = run_export(alice, crate_id, body)
        ok = (
            status == 202 and isinstance(job, dict) and job.get("status") == "succeeded"
        )
        check(
            "MOO-86: {} export job succeeds".format(fmt),
            ok,
            "status={} job={}".format(status, str(job)[:120]),
        )
        if not ok:
            continue
        jobs[fmt] = job

        result = job.get("result") or {}
        status, blob, headers = get_bytes(
            "/exports/{}/download".format(job["id"]), alice
        )
        check(
            "MOO-86: {} bundle downloads as a zip".format(fmt),
            status == 200 and blob[:2] == b"PK",
            "status={} bytes={}".format(status, len(blob)),
        )
        archive = zipfile.ZipFile(io.BytesIO(blob))
        names = archive.namelist()
        check(
            "MOO-86: {} zip integrity".format(fmt),
            archive.testzip() is None,
            "",
        )
        music = [n for n in names if n.startswith("Music/")]
        check(
            "MOO-86: {} bundle carries the audio under Music/".format(fmt),
            len(music) == result.get("track_count") == 2,
            "music={} result={}".format(music, result.get("track_count")),
        )
        check(
            "MOO-86: {} bundle carries EXPORT_README.txt".format(fmt),
            "EXPORT_README.txt" in names,
            str(names),
        )
        check(
            "MOO-86: no zip entry escapes the bundle root ({})".format(fmt),
            all(not n.startswith("/") and ".." not in n for n in names),
            str(names),
        )

        if fmt == "serato":
            crate_files = [
                n
                for n in names
                if n.startswith("_Serato_/Subcrates/") and n.endswith(".crate")
            ]
            check(
                "MOO-86 serato: _Serato_/Subcrates/<name>.crate present",
                len(crate_files) == 1,
                str(names),
            )
            paths = crate_track_paths(archive.read(crate_files[0]))
            check(
                "MOO-86 serato: .crate round-trips to relative ptrk paths",
                paths == sorted(music) and all(not p.startswith("/") for p in paths),
                str(paths),
            )
        elif fmt == "traktor":
            nml = [n for n in names if n.endswith(".nml")]
            check("MOO-86 traktor: .nml present", len(nml) == 1, str(names))
            root = ET.fromstring(archive.read(nml[0]))
            locations = root.findall("./COLLECTION/ENTRY/LOCATION")
            primary = [
                node.get("KEY")
                for node in root.findall("./PLAYLISTS//PLAYLIST/ENTRY/PRIMARYKEY")
            ]
            expected = [
                "{}{}{}".format(loc.get("VOLUME"), loc.get("DIR"), loc.get("FILE"))
                for loc in locations
            ]
            check(
                "MOO-86 traktor: PRIMARYKEY matches LOCATION volume+dir+file",
                len(primary) == 2 and primary == expected,
                "primary={} expected={}".format(primary, expected),
            )
            check(
                "MOO-86 traktor: locations use the /: separator and the volume label",
                all(
                    loc.get("DIR") == "/:Music/:" and loc.get("VOLUME") == "ORP_QA"
                    for loc in locations
                ),
                str([loc.attrib for loc in locations]),
            )
            bitrates = [
                node.get("BITRATE")
                for node in root.findall("./COLLECTION/ENTRY/INFO")
                if node.get("BITRATE")
            ]
            check(
                "MOO-86 traktor: BITRATE is bits/s, not kbps",
                all(int(b) > 10000 for b in bitrates),
                str(bitrates),
            )
        else:
            check(
                "MOO-86 rekordbox: rekordbox.xml present",
                "rekordbox.xml" in names,
                str(names),
            )
            root = ET.fromstring(archive.read("rekordbox.xml"))
            tracks = root.findall("./COLLECTION/TRACK")
            keys = [n.get("Key") for n in root.findall("./PLAYLISTS/NODE/NODE/TRACK")]
            ids = [t.get("TrackID") for t in tracks]
            check(
                "MOO-86 rekordbox: playlist keys reference collection TrackIDs",
                keys == ids and keys == ["1", "2"],
                "keys={} ids={}".format(keys, ids),
            )
            check(
                "MOO-86 rekordbox: Location is a percent-encoded absolute file URI",
                all(
                    t.get("Location").startswith(
                        "file://localhost/Volumes/ORP_QA/Music/"
                    )
                    and " " not in t.get("Location")
                    for t in tracks
                ),
                str([t.get("Location") for t in tracks]),
            )

    # --- the copies carry our metadata; originals are never touched ---
    if "serato" in jobs:
        from mutagen.id3 import ID3

        job = jobs["serato"]
        _s, blob, _h = get_bytes("/exports/{}/download".format(job["id"]), alice)
        archive = zipfile.ZipFile(io.BytesIO(blob))
        mp3s = [n for n in archive.namelist() if n.lower().endswith(".mp3")]
        if mp3s:
            raw = io.BytesIO(archive.read(mp3s[0]))
            tags = ID3(raw)
            status, detail, _ = request(
                "GET", "/crates/{}".format(crate_id), token=alice
            )
            song = detail["tracks"][0]["song"]
            check(
                "MOO-86: the bundled copy carries the DB title/artist",
                str(tags.get("TIT2")) == (song.get("title") or ""),
                "id3={} db={}".format(tags.get("TIT2"), song.get("title")),
            )
            has_bpm_or_key = song.get("bpm") or song.get("musical_key")
            check(
                "MOO-86: BPM/key land in ID3 when the DB has them",
                (not has_bpm_or_key) or tags.get("TBPM") or tags.get("TKEY"),
                "TBPM={} TKEY={}".format(tags.get("TBPM"), tags.get("TKEY")),
            )

    # --- IDOR + lifecycle on the artifact routes ---
    if jobs:
        job_id = list(jobs.values())[0]["id"]
        status, _, _ = request("GET", "/exports/{}".format(job_id), token=bob)
        check(
            "MOO-86 IDOR: another user cannot poll my export",
            status == 403,
            str(status),
        )
        status, _, _ = get_bytes("/exports/{}/download".format(job_id), bob)
        check(
            "MOO-86 IDOR: another user cannot download my bundle",
            status == 403,
            str(status),
        )
        status, _, _ = request("GET", "/exports/{}".format(job_id))
        check("MOO-89: export poll is default-deny", status == 401, str(status))
    status, _, _ = request("GET", "/exports/99999999", token=alice)
    check("MOO-86: unknown export -> 404", status == 404, str(status))

    # --- the artifact is gone (TTL swept) -> 410, not a 500 or a stale file ---
    if jobs:
        import os

        from src.export import bundle as bundle_mod

        job = list(jobs.values())[-1]
        artifact = os.path.join(
            bundle_mod.export_dir(job["id"]), job["result"]["bundle_filename"]
        )
        os.remove(artifact)
        status, _, _ = get_bytes("/exports/{}/download".format(job["id"]), alice)
        check("MOO-86: expired/swept bundle -> 410", status == 410, str(status))

    return summary()


if __name__ == "__main__":
    main()
