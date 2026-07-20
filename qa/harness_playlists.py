"""MOO-84 playlists/crates + MOO-89 default-deny/IDOR harness (QA2, MOO-92).

Covers: admin-gated registration, crate CRUD, track add/remove, public vs
private visibility, and cross-user IDOR on every {crate_id} route.
"""
from qa_lib import check, login, request, summary

ADMIN_PW = "QaCheck2!pass"
USER_PW = "QaUser2!pass"
A = "qa2_alice"
B = "qa2_bob"


def ensure_user(admin_token, username):
    status, body, _ = request(
        "POST",
        "/register",
        token=admin_token,
        body={"username": username, "password": USER_PW},
    )
    # 409/400 => already exists from a previous run; fine.
    return status, body


def main():
    admin, meta = login("admin", ADMIN_PW)
    check("auth: admin local login", admin is not None, str(meta[0]))

    # --- MOO-89: registration is admin-gated ---
    status, body, _ = request(
        "POST", "/register", body={"username": "qa2_intruder", "password": USER_PW}
    )
    check(
        "MOO-89: anonymous /register is refused (admin-gated)",
        status in (401, 403),
        "status={} body={}".format(status, body),
    )

    for name in (A, B):
        ensure_user(admin, name)
    alice, ameta = login(A, USER_PW)
    bob, bmeta = login(B, USER_PW)
    check("auth: admin-created user A can log in", alice is not None, str(ameta[0]))
    check("auth: admin-created user B can log in", bob is not None, str(bmeta[0]))
    if not (alice and bob):
        summary()
        return

    # --- default-deny: unauthenticated crate access ---
    status, _, _ = request("GET", "/crates")
    check("MOO-89: GET /crates unauthenticated -> 401", status == 401, str(status))
    status, _, _ = request("GET", "/crates/public")
    check(
        "MOO-89: GET /crates/public unauthenticated -> 401", status == 401, str(status)
    )

    # --- songs to work with ---
    status, songs, _ = request("GET", "/songs", token=alice)
    items = songs.get("items", []) if isinstance(songs, dict) else songs
    song_ids = [s["id"] for s in items][:3] if isinstance(items, list) else []
    check("fixture: songs available for crate tracks", len(song_ids) >= 2, str(song_ids))

    # --- CRUD: create private + public crates as Alice ---
    status, priv, _ = request(
        "POST", "/crates", token=alice, body={"name": "QA2 Private"}
    )
    check("MOO-84: create crate (private by default)", status in (200, 201), str(status))
    priv_id = priv.get("id") if isinstance(priv, dict) else None
    check(
        "MOO-84: new crate defaults to public=false",
        isinstance(priv, dict) and priv.get("public") is False,
        "public={}".format(priv.get("public") if isinstance(priv, dict) else priv),
    )

    status, pub, _ = request(
        "POST", "/crates", token=alice, body={"name": "QA2 Public"}
    )
    pub_id = pub.get("id") if isinstance(pub, dict) else None
    status, upd, _ = request(
        "PATCH", "/crates/{}".format(pub_id), token=alice, body={"public": True}
    )
    check(
        "MOO-84: PATCH crate -> public=true",
        status == 200 and isinstance(upd, dict) and upd.get("public") is True,
        "status={}".format(status),
    )

    # --- tracks: add ---
    for sid in song_ids:
        request(
            "POST",
            "/crates/{}/tracks".format(priv_id),
            token=alice,
            body={"song_id": sid},
        )
        request(
            "POST",
            "/crates/{}/tracks".format(pub_id),
            token=alice,
            body={"song_id": sid},
        )
    status, tracks, _ = request(
        "GET", "/crates/{}/tracks".format(priv_id), token=alice
    )
    got = len(tracks.get("items", [])) if isinstance(tracks, dict) else -1
    check(
        "MOO-84: add tracks to crate",
        status == 200 and got == len(song_ids),
        "status={} tracks={}".format(status, got),
    )

    # --- tracks: remove ---
    status, _, _ = request(
        "DELETE",
        "/crates/{}/tracks/{}".format(priv_id, song_ids[0]),
        token=alice,
    )
    status2, tracks2, _ = request(
        "GET", "/crates/{}/tracks".format(priv_id), token=alice
    )
    left = len(tracks2.get("items", [])) if isinstance(tracks2, dict) else -1
    check(
        "MOO-84: remove track from crate",
        status in (200, 204) and left == len(song_ids) - 1,
        "delete={} remaining={}".format(status, left),
    )

    # --- IDOR: Bob must not reach Alice's PRIVATE crate on any route ---
    idor = [
        ("GET", "/crates/{}".format(priv_id), None),
        ("GET", "/crates/{}/tracks".format(priv_id), None),
        ("PATCH", "/crates/{}".format(priv_id), {"name": "pwned"}),
        ("DELETE", "/crates/{}".format(priv_id), None),
        ("POST", "/crates/{}/tracks".format(priv_id), {"song_id": song_ids[0]}),
        ("PUT", "/crates/{}/tracks".format(priv_id), {"song_ids": song_ids}),
        (
            "DELETE",
            "/crates/{}/tracks/{}".format(priv_id, song_ids[-1]),
            None,
        ),
        ("POST", "/crates/{}/duplicate".format(priv_id), {}),
        ("POST", "/crates/{}/share/rotate".format(priv_id), None),
        ("GET", "/crates/{}/export.m3u".format(priv_id), None),
    ]
    for method, path, payload in idor:
        status, body, _ = request(method, path, token=bob, body=payload)
        check(
            "MOO-84 IDOR: {} {} as other user -> denied".format(method, path),
            status in (403, 404),
            "status={} body={}".format(status, str(body)[:90]),
        )

    # --- visibility: Bob CAN read the public crate ---
    status, _, _ = request("GET", "/crates/{}".format(pub_id), token=bob)
    check(
        "MOO-84: public crate readable by other user", status == 200, "status={}".format(status)
    )
    status, plist, _ = request("GET", "/crates/public", token=bob)
    ids = (
        [c["id"] for c in plist.get("items", plist)]
        if isinstance(plist, (dict, list))
        else []
    )
    check(
        "MOO-84: /crates/public lists the public crate",
        pub_id in ids,
        "ids={}".format(ids),
    )
    check(
        "MOO-84: /crates/public does NOT leak the private crate",
        priv_id not in ids,
        "ids={}".format(ids),
    )

    # --- Bob's own crate list must not contain Alice's crates ---
    status, mine, _ = request("GET", "/crates", token=bob)
    mine_rows = mine.get("items", []) if isinstance(mine, dict) else mine
    mine_ids = [c["id"] for c in mine_rows] if isinstance(mine_rows, list) else []
    check(
        "MOO-84: GET /crates (mine) is owner-scoped",
        priv_id not in mine_ids and pub_id not in mine_ids,
        "bob sees={}".format(mine_ids),
    )

    # --- delete own crate ---
    status, _, _ = request("DELETE", "/crates/{}".format(pub_id), token=alice)
    check("MOO-84: owner can DELETE own crate", status in (200, 204), str(status))

    return summary()


if __name__ == "__main__":
    main()
