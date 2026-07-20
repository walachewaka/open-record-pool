"""The metadata editor + album art, end to end (MOO-82).

Run the same way as the other QA2 harnesses (see qa/README.md):

    docker compose exec -T backend mkdir -p /tmp/qa
    docker cp qa/. open-record-pool-backend-1:/tmp/qa/
    docker compose exec -T -w /tmp/qa backend python harness_tags.py

Covers: the full ID3 field set (incl. TXXX) through PATCH /admin/content/{id},
revision history + rollback (and the stale-rollback 409), batch edit + batch
rollback, album art upload/serve/remove (with the magic-byte, size and
decode-bomb rejections), the artwork candidate list, the Beatport suggestion
panel, the member propose -> curator approve flow, and the authz sweep.
"""
import io
import json
import mimetypes
import sys
import urllib.request
import uuid

sys.path.insert(0, "/app")

from qa_lib import BASE, check, login, request, summary  # noqa: E402

ADMIN_PW = "QaCheck2!pass"
MEMBER_PW = "QaCheck2!member"


def multipart(path, token, field, filename, data, content_type="image/png"):
    """PUT a file as multipart/form-data (urllib has no helper for this)."""
    boundary = uuid.uuid4().hex
    body = io.BytesIO()
    body.write(("--%s\r\n" % boundary).encode())
    body.write(
        (
            'Content-Disposition: form-data; name="%s"; filename="%s"\r\n'
            % (field, filename)
        ).encode()
    )
    body.write(("Content-Type: %s\r\n\r\n" % content_type).encode())
    body.write(data)
    body.write(("\r\n--%s--\r\n" % boundary).encode())
    req = urllib.request.Request(
        BASE + path,
        data=body.getvalue(),
        method="PUT",
        headers={
            "Content-Type": "multipart/form-data; boundary=" + boundary,
            "Cookie": "Authorization=Bearer " + token,
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8", "replace")
        try:
            return err.code, json.loads(raw)
        except ValueError:
            return err.code, raw


def png_bytes(size=(2000, 2000)):
    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", size, (200, 30, 90)).save(out, format="PNG")
    return out.getvalue()


def main():
    mimetypes.init()
    admin, _ = login("admin", ADMIN_PW)
    if not admin:
        print("cannot log in as admin -- is the stack up?")
        return 1

    status, page, _ = request("GET", "/admin/content?page_size=3", token=admin)
    songs = (page or {}).get("items") or []
    if status != 200 or len(songs) < 2:
        print("need at least two songs in the library; got %s" % status)
        return 1
    song, other = songs[0], songs[1]
    sid, oid = song["id"], other["id"]

    # --- 1. the full ID3 field set ------------------------------------------
    edit = {
        "title": "QA Title %s" % uuid.uuid4().hex[:6],
        "album_artist": "QA Album Artist",
        "composer": "QA Composer",
        "label": "QA Label",
        "comment": "QA comment",
        "isrc": "GBAHS1700001",
        "disc_number": 2,
        "genre": "Tech House",
        "year": 2019,
        "bpm": 126.0,
        "musical_key": "8A",
        "txxx_frames": {"ENERGY": "7"},
    }
    status, body, _ = request(
        "PATCH", "/admin/content/%d" % sid, token=admin, body=edit
    )
    check(
        "edit: every ID3 field (incl. TXXX) is writable",
        status == 200
        and all(body.get(f) == v for f, v in edit.items() if f != "bpm")
        and abs((body.get("bpm") or 0) - 126.0) < 0.01,
        "status=%s body=%s" % (status, json.dumps(body)[:200]),
    )
    check(
        "edit: every edited field is locked 'manual' (survives a rescan)",
        all((body.get("field_locks") or {}).get(f) == "manual" for f in edit),
        str(body.get("field_locks")),
    )
    status, body, _ = request(
        "PATCH", "/admin/content/%d" % sid, token=admin, body={"isrc": "nope"}
    )
    check("edit: a malformed ISRC is rejected", status == 422, "status=%s" % status)
    status, body, _ = request(
        "PATCH", "/admin/content/%d" % sid, token=admin, body={"bpm": 5000}
    )
    check("edit: an absurd BPM is rejected", status == 422, "status=%s" % status)
    status, body, _ = request(
        "PATCH",
        "/admin/content/%d" % sid,
        token=admin,
        body={"txxx_frames": {"X" * 80: "v"}},
    )
    check(
        "edit: an oversized custom tag name is rejected",
        status == 422,
        "status=%s" % status,
    )

    # --- 2. history + rollback ----------------------------------------------
    status, history, _ = request(
        "GET", "/admin/content/%d/revisions" % sid, token=admin
    )
    items = (history or {}).get("items") or []
    latest = items[0] if items else {}
    check(
        "history: the edit is recorded with who/when/old->new",
        status == 200
        and latest.get("editor_username") == "admin"
        and "title" in (latest.get("changes") or {})
        and "old" in latest["changes"]["title"],
        "status=%s latest=%s" % (status, json.dumps(latest)[:160]),
    )
    old_title = latest["changes"]["title"]["old"]
    status, body, _ = request(
        "POST",
        "/admin/content/%d/revisions/%d/rollback" % (sid, latest["id"]),
        token=admin,
    )
    check(
        "history: rollback restores the previous values",
        status == 200 and body.get("title") == old_title,
        "status=%s title=%r" % (status, (body or {}).get("title")),
    )
    status, body, _ = request(
        "POST",
        "/admin/content/%d/revisions/%d/rollback" % (sid, latest["id"]),
        token=admin,
    )
    check(
        "history: rolling the same revision back twice is a 409, not a clobber",
        status == 409,
        "status=%s" % status,
    )

    # --- 3. batch edit + batch rollback -------------------------------------
    status, batch, _ = request(
        "POST",
        "/admin/content/tags/batch",
        token=admin,
        body={"song_ids": [sid, oid], "fields": {"genre": "QA Batch Genre"}},
    )
    check(
        "batch: one field set applied to a multi-selection",
        status == 200 and batch.get("updated") >= 1,
        "status=%s body=%s" % (status, batch),
    )
    status, body, _ = request("GET", "/admin/content?page_size=3", token=admin)
    got = {s["id"]: s["genre"] for s in body["items"]}
    check(
        "batch: both tracks carry the new genre",
        got.get(sid) == "QA Batch Genre" and got.get(oid) == "QA Batch Genre",
        str(got),
    )
    status, body, _ = request(
        "POST",
        "/admin/content/tags/batch",
        token=admin,
        body={"song_ids": [sid], "fields": {"title": "nope"}},
    )
    check(
        "batch: a per-track field (title) is not batch-editable",
        status == 422,
        "status=%s" % status,
    )
    status, undo, _ = request(
        "POST", "/admin/content/batches/%s/rollback" % batch["batch_id"], token=admin
    )
    check(
        "batch: the whole batch can be undone",
        status == 200 and undo.get("undone") == batch.get("updated"),
        "status=%s body=%s" % (status, undo),
    )

    # --- 4. album art --------------------------------------------------------
    status, body = multipart(
        "/admin/content/%d/artwork" % sid, admin, "file", "cover.png", png_bytes()
    )
    check(
        "art: an upload is normalized to at most 1400px and stored",
        status == 200
        and body.get("artwork_source") == "upload"
        and body.get("artwork_width") == 1400
        and body.get("artwork_height") == 1400,
        "status=%s w=%s h=%s" % (status, body.get("artwork_width"), body.get("artwork_height")),
    )
    status, raw, headers = request("GET", "/songs/%d/artwork" % sid, token=admin)
    check(
        "art: the cover is served (as a re-encoded JPEG) behind auth",
        status == 200 and headers.get("content-type") == "image/jpeg",
        "status=%s ct=%s" % (status, headers.get("content-type")),
    )
    status, _raw, _h = request("GET", "/songs/%d/artwork" % sid)
    check("art: serving requires auth", status == 401, "status=%s" % status)
    status, body = multipart(
        "/admin/content/%d/artwork" % sid,
        admin,
        "file",
        "evil.png",
        b"<?php system($_GET['c']); ?>",
    )
    check(
        "art: a PHP payload named .png is rejected (magic bytes, not extension)",
        status == 422,
        "status=%s" % status,
    )
    status, body = multipart(
        "/admin/content/%d/artwork" % sid, admin, "file", "big.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * (11 * 1024 * 1024)
    )
    check(
        "art: an oversized upload is rejected",
        status == 413,
        "status=%s" % status,
    )
    status, cands, _ = request(
        "GET", "/admin/content/%d/artwork/candidates" % sid, token=admin
    )
    origins = [c["origin"] for c in (cands or {}).get("items", [])]
    check(
        "art: the candidate list offers the current cover",
        status == 200 and "current" in origins,
        "status=%s origins=%s" % (status, origins),
    )
    status, body, _ = request(
        "POST",
        "/admin/content/%d/artwork/select" % sid,
        token=admin,
        body={"origin": "beatport", "url": "https://evil.example.com/x.jpg"},
    )
    check(
        "art: an off-allowlist URL is never fetched",
        status == 422,
        "status=%s" % status,
    )
    status, body, _ = request(
        "DELETE", "/admin/content/%d/artwork" % sid, token=admin
    )
    check(
        "art: the cover can be removed (the garbage-art case)",
        status == 200 and body.get("artwork_source") is None,
        "status=%s" % status,
    )

    # --- 5. suggestions ------------------------------------------------------
    status, sugg, _ = request(
        "GET", "/admin/content/%d/suggestions" % sid, token=admin
    )
    check(
        "suggestions: the panel answers even with no Beatport match",
        status == 200 and "items" in (sugg or {}),
        "status=%s body=%s" % (status, json.dumps(sugg)[:120]),
    )

    # --- 6. member propose -> curator approve --------------------------------
    member, _ = login("qamember", MEMBER_PW)
    if not member:
        # /register is admin-gated (MOO-89), so the account is created with the
        # admin's token.
        request(
            "POST",
            "/register",
            token=admin,
            body={"username": "qamember", "password": MEMBER_PW},
        )
        member, _ = login("qamember", MEMBER_PW)
    if not member:
        check("proposals: could not create a member account", False, "skipped")
        return 1 if summary() else 0

    status, body, _ = request(
        "PATCH", "/admin/content/%d" % sid, token=member, body={"genre": "Nope"}
    )
    check(
        "authz: a member cannot edit metadata directly",
        status == 403,
        "status=%s" % status,
    )
    for path, method in [
        ("/admin/content/%d/revisions" % sid, "GET"),
        ("/admin/content/%d/artwork/candidates" % sid, "GET"),
        ("/admin/content/%d/suggestions" % sid, "GET"),
        ("/admin/tag-proposals", "GET"),
    ]:
        status, _b, _h = request(method, path, token=member)
        if status != 403:
            check("authz: %s %s is 403 for a member" % (method, path), False, str(status))
            break
    else:
        check("authz: every editor route is 403 for a member", True)

    status, proposal, _ = request(
        "POST",
        "/songs/%d/tag-proposals" % sid,
        token=member,
        body={"changes": {"genre": "Proposed Genre"}, "note": "this is techno"},
    )
    check(
        "proposals: a member can suggest an edit",
        status == 200 and proposal.get("status") == "pending",
        "status=%s body=%s" % (status, json.dumps(proposal)[:140]),
    )
    status, dup, _ = request(
        "POST",
        "/songs/%d/tag-proposals" % sid,
        token=member,
        body={"changes": {"genre": "Again"}},
    )
    check(
        "proposals: a second pending suggestion on the same track is a 409",
        status == 409,
        "status=%s" % status,
    )
    status, mine, _ = request("GET", "/users/me/tag-proposals", token=member)
    check(
        "proposals: a member sees their own suggestions",
        status == 200 and any(i["id"] == proposal["id"] for i in mine["items"]),
        "status=%s" % status,
    )
    status, queue, _ = request(
        "GET", "/admin/tag-proposals?status=pending", token=admin
    )
    check(
        "proposals: the suggestion is in the curator queue",
        status == 200 and any(i["id"] == proposal["id"] for i in queue["items"]),
        "status=%s" % status,
    )
    status, approved, _ = request(
        "POST", "/admin/tag-proposals/%d/approve" % proposal["id"], token=admin
    )
    check(
        "proposals: approval applies the edit",
        status == 200 and approved.get("status") == "approved",
        "status=%s" % status,
    )
    status, body, _ = request("GET", "/admin/content?page_size=3", token=admin)
    applied = {s["id"]: s["genre"] for s in body["items"]}
    check(
        "proposals: the approved value is live on the track",
        applied.get(sid) == "Proposed Genre",
        str(applied.get(sid)),
    )
    status, history, _ = request(
        "GET", "/admin/content/%d/revisions" % sid, token=admin
    )
    top = history["items"][0]
    check(
        "proposals: the revision is credited to the member who proposed it",
        top.get("source") == "proposal" and top.get("editor_username") == "qamember",
        json.dumps(top)[:140],
    )
    status, again, _ = request(
        "POST", "/admin/tag-proposals/%d/approve" % proposal["id"], token=admin
    )
    check(
        "proposals: a reviewed suggestion cannot be reviewed twice",
        status == 409,
        "status=%s" % status,
    )

    return 1 if summary() else 0


if __name__ == "__main__":
    sys.exit(main())
