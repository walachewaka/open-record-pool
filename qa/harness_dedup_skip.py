"""MOO-90 pre-download dedup skip, end to end (QA2, MOO-92).

The requirement: a request for a track ALREADY in the library at equal/better
quality must not download it again -- the download is skipped and the request
is fulfilled from the library copy.
"""
import time

from qa_lib import check, login, request, summary

FIXTURE_URL = "https://www.youtube.com/watch?v=ORPFIXTURE1"


def wait_for(fn, timeout=150, interval=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = fn()
        if value:
            return value
        time.sleep(interval)
    return None


def main():
    admin, _ = login("admin", "QaCheck2!pass")
    alice, _ = login("qa2_alice", "QaUser2!pass")

    # Baseline: the fixture is already in the library from the chain run.
    _, res, _ = request("GET", "/search?q=ORP%20Fixture%20Track", token=admin)
    lib = [
        i
        for i in (res.get("items", []) if isinstance(res, dict) else [])
        if i.get("title") == "ORP Fixture Track"
    ]
    check(
        "baseline: fixture is in the library exactly once",
        len(lib) == 1,
        "copies={}".format(len(lib)),
    )
    existing_song_id = lib[0]["id"] if lib else None

    _, songs_before, _ = request("GET", "/songs", token=admin)
    total_before = songs_before.get("total") if isinstance(songs_before, dict) else -1

    # 1. A free-text request for a track that is already in the library must be
    #    flagged as a possible/certain duplicate at submission time.
    _, req1, _ = request(
        "POST",
        "/requests",
        token=alice,
        body={"kind": "free_text", "artist": "ORP Test", "title": "ORP Fixture Track"},
    )
    rid = req1.get("id") if isinstance(req1, dict) else None
    dupe_flag = (req1.get("duplicate_of") or req1.get("possible_duplicate_of") or {}) if isinstance(req1, dict) else {}
    check(
        "MOO-90: request for an in-library track is flagged against the library copy "
        "at submission",
        dupe_flag.get("id") == existing_song_id,
        "status={} flagged_song={}".format(req1.get("status"), dupe_flag.get("id")),
    )

    # 2. Approve it with the source URL -> the engine must SKIP the download.
    _, appr, _ = request(
        "POST",
        "/admin/requests/{}/approve".format(rid),
        token=admin,
        body={"source_url": FIXTURE_URL},
    )
    dl_id = appr.get("download_id") if isinstance(appr, dict) else None

    def terminal():
        _, d, _ = request("GET", "/fetch/{}".format(dl_id), token=admin)
        if isinstance(d, dict) and d.get("status") in (
            "imported",
            "failed",
            "duplicate_skipped",
        ):
            return d
        return None

    dl = wait_for(terminal)
    check(
        "MOO-90: download is SKIPPED (duplicate_skipped), not re-fetched",
        isinstance(dl, dict) and dl.get("status") == "duplicate_skipped",
        "download_status={}".format(dl.get("status") if dl else None),
    )
    check(
        "MOO-90: the skipped download points at the existing library song",
        isinstance(dl, dict) and dl.get("song_id") == existing_song_id,
        "song_id={} expected={}".format(
            dl.get("song_id") if dl else None, existing_song_id
        ),
    )

    # 3. The request resolves as fulfilled-from-library.
    def fulfilled():
        _, r, _ = request("GET", "/requests/{}".format(rid), token=alice)
        if isinstance(r, dict) and r.get("status") in (
            "fulfilled",
            "duplicate",
            "failed",
            "rejected",
        ):
            return r
        return None

    final = wait_for(fulfilled)
    check(
        "MOO-90: request is marked fulfilled from the library copy",
        isinstance(final, dict)
        and final.get("status") == "fulfilled"
        and (final.get("fulfilled_song") or {}).get("id") == existing_song_id,
        "status={} fulfilled_song={}".format(
            final.get("status") if final else None,
            (final.get("fulfilled_song") or {}).get("id") if final else None,
        ),
    )

    # 4. No second copy was created anywhere.
    _, songs_after, _ = request("GET", "/songs", token=admin)
    total_after = songs_after.get("total") if isinstance(songs_after, dict) else -2
    check(
        "MOO-87/90: no new song row was created (library total unchanged)",
        total_after == total_before,
        "total before={} after={}".format(total_before, total_after),
    )

    _, res2, _ = request("GET", "/search?q=ORP%20Fixture%20Track", token=admin)
    copies = [
        i
        for i in (res2.get("items", []) if isinstance(res2, dict) else [])
        if i.get("title") == "ORP Fixture Track"
    ]
    check(
        "MOO-79/90: still exactly one copy in Elasticsearch (no duplicate doc)",
        len(copies) == 1,
        "copies={}".format(len(copies)),
    )

    return summary()


if __name__ == "__main__":
    main()
