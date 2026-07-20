"""MOO-81 song requests x MOO-78 downloads x MOO-87/90 dedup x MOO-79 search.

The cross-issue acquisition chain for QA checkpoint 2 (MOO-92):

  request submitted -> moderated -> download enqueued -> file imported ->
  analyzed + deduped -> searchable in Elasticsearch exactly once

Runs against the live stack with ORP_FAKE_DOWNLOADS=true, so the provider
fetch is a network-free fixture but every stage downstream of it (import,
analyzer, dedup, ES outbox) is the real code path.
"""
import time

from qa_lib import check, login, request, summary

ADMIN_PW = "QaCheck2!pass"
USER_PW = "QaUser2!pass"
A = "qa2_alice"
B = "qa2_bob"

FIXTURE_URL = "https://www.youtube.com/watch?v=ORPFIXTURE1"


def wait_for(fn, timeout=180, interval=5):
    """Poll fn() until it returns a truthy value or the timeout elapses."""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = fn()
        if last:
            return last
        time.sleep(interval)
    return last


def req_status(token, rid):
    _, body, _ = request("GET", "/requests/{}".format(rid), token=token)
    return body.get("status") if isinstance(body, dict) else None


def main():
    admin, _ = login("admin", ADMIN_PW)
    alice, _ = login(A, USER_PW)
    bob, _ = login(B, USER_PW)
    check("auth: admin + 2 members logged in", all([admin, alice, bob]))

    # ---------- default-deny on the request surface (MOO-89) ----------
    status, _, _ = request("POST", "/requests", body={"kind": "url", "source_url": FIXTURE_URL})
    check("MOO-89: POST /requests unauthenticated -> 401", status == 401, str(status))
    status, _, _ = request("GET", "/admin/requests", token=bob)
    check(
        "MOO-89: member hitting /admin/requests -> 403",
        status == 403,
        "status={}".format(status),
    )

    # ---------- free-text request lands pending (MOO-81 deviation) ----------
    status, ft, _ = request(
        "POST",
        "/requests",
        token=bob,
        body={"kind": "free_text", "artist": "QA Two", "title": "Pending Track"},
    )
    ft_id = ft.get("id") if isinstance(ft, dict) else None
    check(
        "MOO-81: free-text request accepted and lands 'pending'",
        status in (200, 201) and isinstance(ft, dict) and ft.get("status") == "pending",
        "status={} body={}".format(status, str(ft)[:100]),
    )

    # validation: free_text without artist/title is refused
    status, _, _ = request(
        "POST", "/requests", token=bob, body={"kind": "free_text", "title": "No Artist"}
    )
    check("MOO-81: free-text without artist -> 422", status == 422, str(status))
    # validation: url kind without source_url is refused
    status, _, _ = request("POST", "/requests", token=bob, body={"kind": "url"})
    check("MOO-81: url request without source_url -> 422", status == 422, str(status))

    # ---------- moderation: it shows up in the admin queue ----------
    status, queue, _ = request("GET", "/admin/requests", token=admin)
    ids = [r["id"] for r in queue.get("items", [])] if isinstance(queue, dict) else []
    check("MOO-81: request visible in admin queue", ft_id in ids, "queue={}".format(ids[:8]))

    # ---------- IDOR: Alice must not read Bob's request ----------
    status, body, _ = request("GET", "/requests/{}".format(ft_id), token=alice)
    check(
        "MOO-81 IDOR: other member cannot read someone else's request",
        status in (403, 404),
        "status={} body={}".format(status, str(body)[:70]),
    )

    # ---------- reject flow ----------
    status, rej, _ = request(
        "POST",
        "/admin/requests/{}/reject".format(ft_id),
        token=admin,
        body={"reason": "QA2 reject path"},
    )
    check(
        "MOO-81: admin reject -> status=rejected with reason",
        status == 200
        and isinstance(rej, dict)
        and rej.get("status") == "rejected"
        and rej.get("reason") == "QA2 reject path",
        "status={} body={}".format(status, str(rej)[:90]),
    )

    # ---------- cancel flow (member cancels own pending request) ----------
    _, c1, _ = request(
        "POST",
        "/requests",
        token=bob,
        body={"kind": "free_text", "artist": "QA Two", "title": "Cancel Me"},
    )
    c1_id = c1.get("id")
    status, cancelled, _ = request(
        "POST", "/requests/{}/cancel".format(c1_id), token=bob
    )
    check(
        "MOO-81: member can cancel own pending request",
        status == 200 and isinstance(cancelled, dict) and cancelled.get("status") == "cancelled",
        "status={} -> {}".format(status, str(cancelled)[:70]),
    )

    # ---------- THE CHAIN: approve a free-text request with a source_url ----------
    _, chain, _ = request(
        "POST",
        "/requests",
        token=bob,
        body={"kind": "free_text", "artist": "ORP Test", "title": "ORP Fixture Track"},
    )
    chain_id = chain.get("id")

    status, appr, _ = request(
        "POST",
        "/admin/requests/{}/approve".format(chain_id),
        token=admin,
        body={"source_url": FIXTURE_URL},
    )
    dl_id = appr.get("download_id") if isinstance(appr, dict) else None
    check(
        "MOO-81->MOO-78: approve with source_url enqueues a download",
        status == 200 and dl_id is not None,
        "status={} request_status={} download_id={}".format(
            status, appr.get("status") if isinstance(appr, dict) else "?", dl_id
        ),
    )

    # download reaches a terminal state
    def dl_done():
        _, d, _ = request("GET", "/fetch/{}".format(dl_id), token=admin)
        if isinstance(d, dict) and d.get("status") in (
            "imported",
            "failed",
            "duplicate_skipped",
        ):
            return d
        return None

    dl = wait_for(dl_done, timeout=180, interval=5)
    check(
        "MOO-78: download completes and imports the file",
        isinstance(dl, dict) and dl.get("status") == "imported" and dl.get("song_id"),
        "download={}".format(str(dl)[:140]),
    )
    song_id = dl.get("song_id") if isinstance(dl, dict) else None

    # the 60s sync cron flips the request to fulfilled
    fulfilled = wait_for(
        lambda: req_status(bob, chain_id) == "fulfilled", timeout=150, interval=5
    )
    final = req_status(bob, chain_id)
    check(
        "MOO-81: sync cron flips request -> fulfilled after the download lands",
        final == "fulfilled",
        "request_status={}".format(final),
    )
    _, chain_final, _ = request("GET", "/requests/{}".format(chain_id), token=bob)
    check(
        "MOO-81: fulfilled request points at the imported song",
        isinstance(chain_final, dict)
        and (chain_final.get("fulfilled_song") or {}).get("id") == song_id,
        "fulfilled_song={}".format(str(chain_final.get("fulfilled_song"))[:80]),
    )

    # ---------- MOO-79: the imported song is searchable, exactly once ----------
    def in_search():
        _, res, _ = request("GET", "/search?q=ORP%20Fixture%20Track", token=admin)
        items = res.get("items", []) if isinstance(res, dict) else []
        hits = [i for i in items if i.get("id") == song_id]
        return hits if hits else None

    hits = wait_for(in_search, timeout=120, interval=5)
    check(
        "MOO-79: imported song is searchable in Elasticsearch",
        bool(hits),
        "hits={}".format(len(hits) if hits else 0),
    )
    check(
        "MOO-79: imported song appears EXACTLY once in search",
        hits is not None and len(hits) == 1,
        "hits={}".format(len(hits) if hits else 0),
    )

    # ---------- MOO-90: pre-download dedup skip ----------
    # The same fixture is now in the library at identical quality: a second
    # request for it must NOT trigger a second download.
    _, before, _ = request("GET", "/fetch", token=admin)
    n_before = len(before.get("items", [])) if isinstance(before, dict) else -1

    status, dup, _ = request(
        "POST", "/requests", token=alice, body={"kind": "url", "source_url": FIXTURE_URL}
    )
    dup_id = dup.get("id") if isinstance(dup, dict) else None
    dup_final = {}
    if status == 409:
        # The open-duplicate guard fired first: an open request for this track
        # already exists, so no second download can be started either way.
        dup_state = "open_duplicate_guard"
    else:
        dup_state = wait_for(
            lambda: (
                req_status(alice, dup_id)
                if req_status(alice, dup_id) in ("duplicate", "fulfilled", "pending")
                else None
            ),
            timeout=90,
            interval=5,
        )
        _, dup_final, _ = request("GET", "/requests/{}".format(dup_id), token=alice)
    check(
        "MOO-90: re-request of an in-library track never starts a second download",
        dup_state in ("duplicate", "fulfilled", "pending", "open_duplicate_guard"),
        "outcome={}".format(dup_state),
    )

    _, after, _ = request("GET", "/fetch", token=admin)
    n_after = len(after.get("items", [])) if isinstance(after, dict) else -1
    check(
        "MOO-90: no new download row was created for the duplicate request",
        n_after == n_before,
        "downloads before={} after={}".format(n_before, n_after),
    )

    # the library still holds exactly one copy of the fixture
    def one_copy():
        _, res, _ = request("GET", "/search?q=ORP%20Fixture%20Track", token=admin)
        items = res.get("items", []) if isinstance(res, dict) else []
        return [i for i in items if i.get("title") == "ORP Fixture Track"]

    copies = one_copy()
    check(
        "MOO-87/90: library holds exactly ONE copy of the fixture after 2 requests",
        len(copies) == 1,
        "copies={}".format(len(copies)),
    )

    # ---------- direct duplicate download is skipped too ----------
    # The engine dedups after the probe: the row goes terminal as
    # duplicate_skipped and is pointed at the song already in the library.
    status, redl, _ = request("POST", "/fetch", token=admin, body={"url": FIXTURE_URL})
    redl_id = redl.get("id") if isinstance(redl, dict) else None

    def redl_terminal():
        _, d, _ = request("GET", "/fetch/{}".format(redl_id), token=admin)
        if isinstance(d, dict) and d.get("status") in (
            "imported",
            "failed",
            "duplicate_skipped",
        ):
            return d
        return None

    redl_final = wait_for(redl_terminal, timeout=120, interval=5) if redl_id else None
    check(
        "MOO-78/90: re-submitting the same URL ends duplicate_skipped (no re-download)",
        isinstance(redl_final, dict)
        and redl_final.get("status") == "duplicate_skipped"
        and redl_final.get("song_id") == song_id,
        "status={} song_id={}".format(
            redl_final.get("status") if redl_final else None,
            redl_final.get("song_id") if redl_final else None,
        ),
    )

    # ---------- rate limit on request submission (MOO-89: 5/60s) ----------
    codes = []
    for i in range(9):
        status, _, _ = request(
            "POST",
            "/requests",
            token=bob,
            body={"kind": "free_text", "artist": "RL", "title": "burst {}".format(i)},
        )
        codes.append(status)
    check(
        "MOO-89: /requests is rate-limited (429 within a burst)",
        429 in codes,
        "codes={}".format(codes),
    )

    return summary()


if __name__ == "__main__":
    main()
