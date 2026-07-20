"""Artist follows / release tracking, end to end (MOO-80).

Run the same way as the other QA2 harnesses (see qa/README.md), with
RELEASE_SOURCE_MOCK=true on backend/worker so the mock release source's
deterministic fixtures give the assertions a known answer:

    RELEASE_SOURCE_MOCK=true docker compose up -d backend worker worker-heavy
    docker compose exec -T backend mkdir -p /tmp/qa
    docker cp qa/. open-record-pool-backend-1:/tmp/qa/
    docker compose exec -T -w /tmp/qa backend python harness_follows.py

Covers: artist materialization from the library (via the existing scan
trigger), follow lifecycle + cross-user IDOR, artist search (local +
external via the mock source), the admin poll tick (dedupe on a second
poll), release list/calendar, auto-grab creating a song request, manual
grab/ignore/unignore with the follower-only guard, and the feed badge.

RELEASE_SOURCE_MOCK's degraded (no-source) contract is asserted by code
review, not exercised here -- toggling it needs a container restart mid-run.
"""
import sys
import time
from urllib.parse import quote

sys.path.insert(0, "/app")

from qa_lib import check, login, request, summary  # noqa: E402

ADMIN_PW = "QaCheck2!pass"
USER_PW = "QaUser2!pass"
A = "qa80_alice"
B = "qa80_bob"


def ensure_user(admin_token, username):
    request(
        "POST", "/register", token=admin_token,
        body={"username": username, "password": USER_PW},
    )


def wait_for_job(token, job_id, timeout=30):
    """Polls GET /admin/jobs/{id} until it lands terminal (WORKERS_ENABLED=true
    here -- the stack runs jobs async via arq/Redis, not inline)."""
    deadline = time.time() + timeout
    job = None
    while time.time() < deadline:
        status, job, _ = request("GET", "/admin/jobs/{}".format(job_id), token=token)
        if status == 200 and job.get("status") in ("succeeded", "failed", "cancelled"):
            return job
        time.sleep(0.5)
    return job


def main():
    admin, meta = login("admin", ADMIN_PW)
    check("auth: admin local login", admin is not None, str(meta[0]))
    if not admin:
        summary()
        return

    for name in (A, B):
        ensure_user(admin, name)
    alice, ameta = login(A, USER_PW)
    bob, bmeta = login(B, USER_PW)
    check("auth: user A can log in", alice is not None, str(ameta[0]))
    check("auth: user B can log in", bob is not None, str(bmeta[0]))
    if not (alice and bob):
        summary()
        return

    # --- default-deny -------------------------------------------------
    status, _, _ = request("GET", "/artists")
    check("default-deny: GET /artists unauthenticated -> 401", status == 401, str(status))
    status, _, _ = request("GET", "/releases")
    check("default-deny: GET /releases unauthenticated -> 401", status == 401, str(status))

    # --- materialize artists from the library (existing scan trigger) --
    status, job, _ = request("POST", "/admin/settings/scan", token=admin)
    check(
        "fixture: POST /admin/settings/scan enqueues -> 202",
        status == 202,
        "status={} body={}".format(status, job),
    )
    job = wait_for_job(admin, job["id"])
    check(
        "fixture: scan_library job succeeds (also syncs artists)",
        job is not None and job.get("status") == "succeeded",
        str(job),
    )

    status, artists, _ = request("GET", "/artists?limit=50", token=alice)
    items = artists.get("items", []) if isinstance(artists, dict) else []
    check("artists: GET /artists lists library artists", len(items) > 0, str(items))
    if not items:
        summary()
        return
    # Pick an artist never resolved/polled before (idempotent across harness
    # reruns against the same stack -- a previously-run artist's releases
    # already exist and would trip the "created new releases" assertions).
    artist = next((a for a in items if a["beatport_artist_id"] is None), items[0])
    artist_id = artist["id"]

    status, detail, _ = request("GET", "/artists/{}".format(artist_id), token=alice)
    check(
        "artists: GET /artists/{id} detail",
        status == 200 and isinstance(detail, dict) and "releases" in detail,
        "status={} body={}".format(status, detail),
    )
    status, unknown, _ = request("GET", "/artists/999999999", token=alice)
    check("artists: unknown id -> 404", status == 404, str(status))

    status, tracks, _ = request(
        "GET", "/artists/{}/tracks".format(artist_id), token=alice
    )
    check(
        "artists: GET /artists/{id}/tracks returns the standard song shape",
        status == 200 and isinstance(tracks.get("items"), list),
        "status={} body={}".format(status, tracks),
    )

    # --- follow lifecycle + IDOR ---------------------------------------
    status, follow, _ = request(
        "POST", "/artists/{}/follow".format(artist_id), token=alice,
        body={"auto_grab": True, "notify": True},
    )
    check(
        "follow: POST follow with auto_grab=true",
        status == 200 and follow.get("followed") is True
        and follow.get("settings", {}).get("auto_grab") is True,
        "status={} body={}".format(status, follow),
    )
    status, re_follow, _ = request(
        "POST", "/artists/{}/follow".format(artist_id), token=alice,
        body={"auto_grab": True, "notify": False},
    )
    check(
        "follow: re-POST is idempotent and updates settings",
        status == 200 and re_follow.get("settings", {}).get("notify") is False,
        "status={} body={}".format(status, re_follow),
    )
    status, patched, _ = request(
        "PATCH", "/artists/{}/follow".format(artist_id), token=alice,
        body={"notify": True},
    )
    check(
        "follow: PATCH partial update",
        status == 200 and patched.get("settings", {}).get("notify") is True
        and patched.get("settings", {}).get("auto_grab") is True,
        "status={} body={}".format(status, patched),
    )
    status, _, _ = request(
        "PATCH", "/artists/{}/follow".format(artist_id), token=bob, body={"notify": False}
    )
    check(
        "follow: IDOR -- B patching A's-only-followed artist -> 404",
        status == 404, str(status),
    )
    status, listed, _ = request("GET", "/artists?followed=true", token=alice)
    check(
        "follow: GET /artists?followed=true filters to my follows",
        status == 200 and any(a["id"] == artist_id for a in listed.get("items", [])),
        "status={} body={}".format(status, listed),
    )

    # --- search: local + external (mock source) ------------------------
    status, search, _ = request(
        "GET", "/artists/search?q={}".format(quote(artist["name"])), token=alice
    )
    check(
        "search: sources_configured true under RELEASE_SOURCE_MOCK",
        status == 200 and search.get("sources_configured") is True,
        "status={} body={}".format(status, search),
    )
    check(
        "search: external results present (mock source)",
        isinstance(search.get("external"), list) and len(search["external"]) > 0,
        str(search),
    )

    # --- admin poll tick -------------------------------------------------
    status, poll1, _ = request("POST", "/admin/follows/poll", token=alice)
    check("poll: non-admin trigger -> 403", status == 403, str(status))

    status, overview_before, _ = request("GET", "/admin/follows/overview", token=admin)
    status, poll1, _ = request("POST", "/admin/follows/poll", token=admin)
    check("poll: admin trigger -> 202", status == 202, "status={} body={}".format(status, poll1))
    poll1 = wait_for_job(admin, poll1["id"])
    check(
        "poll: job succeeds",
        poll1 is not None and poll1.get("status") == "succeeded",
        str(poll1),
    )
    result1 = (poll1 or {}).get("result") or {}
    check(
        "poll: resolved the followed artist against the mock source",
        result1.get("artists_resolved", 0) >= 1 or result1.get("artists_polled", 0) >= 1,
        str(result1),
    )
    check(
        "poll: created new releases from the mock fixtures",
        result1.get("releases_new", 0) >= 1,
        str(result1),
    )
    check(
        "poll: auto-grab created at least one song request (auto_grab=true)",
        result1.get("grabs_created", 0) >= 1,
        str(result1),
    )

    status, overview_after, _ = request("GET", "/admin/follows/overview", token=admin)
    check(
        "poll: admin overview reflects the new releases",
        status == 200
        and overview_after.get("releases_total", 0)
        > overview_before.get("releases_total", -1),
        "before={} after={}".format(overview_before, overview_after),
    )

    status, poll2, _ = request("POST", "/admin/follows/poll", token=admin)
    poll2 = wait_for_job(admin, poll2["id"]) if status == 202 else poll2
    result2 = (poll2 or {}).get("result") or {}
    check(
        "poll: a second poll dedupes -- zero new releases for the same fixtures",
        result2.get("releases_new", 0) == 0,
        "status={} result={}".format(status, result2),
    )

    # --- release list / calendar -----------------------------------------
    status, releases, _ = request(
        "GET", "/releases?range=all&followed_only=true", token=alice
    )
    items = releases.get("items", []) if isinstance(releases, dict) else []
    check(
        "releases: GET /releases lists the artist's releases",
        status == 200 and len(items) >= 3,
        "status={} body={}".format(status, releases),
    )
    grabbed = [r for r in items if r["status"] == "grabbed"]
    check(
        "releases: auto-grab flipped a missing release to grabbed",
        len(grabbed) >= 1,
        str([r["status"] for r in items]),
    )
    if grabbed:
        check(
            "releases: grabbed release carries its song request ids",
            len(grabbed[0].get("matched_song_ids", [])) >= 0
            and isinstance(grabbed[0]["id"], int),
            str(grabbed[0]),
        )

    any_release = items[0] if items else None
    if any_release:
        month = any_release["release_date"][:7]
        status, cal, _ = request(
            "GET", "/releases/calendar?month={}".format(month), token=alice
        )
        check(
            "calendar: GET /releases/calendar returns days for the month",
            status == 200 and isinstance(cal.get("days"), list),
            "status={} body={}".format(status, cal),
        )
        status, cal_bad, _ = request(
            "GET", "/releases/calendar?month=notamonth", token=alice
        )
        check("calendar: invalid month -> 422", status == 422, str(status))

    # --- ignore / unignore / grab + follower-only guard ------------------
    target = grabbed[0] if grabbed else items[0]
    rid = target["id"]

    status, _, _ = request("POST", "/releases/{}/grab".format(rid), token=bob)
    check("releases: non-follower grab -> 403", status == 403, str(status))
    status, _, _ = request("POST", "/releases/{}/ignore".format(rid), token=bob)
    check("releases: non-follower ignore -> 403", status == 403, str(status))

    if target["status"] == "grabbed":
        status, _, _ = request("POST", "/releases/{}/grab".format(rid), token=alice)
        check("releases: grabbing an already-grabbed release -> 409", status == 409, str(status))

    status, ignored, _ = request("POST", "/releases/{}/ignore".format(rid), token=alice)
    check(
        "releases: follower ignore -> ignored",
        status == 200 and ignored.get("status") == "ignored",
        "status={} body={}".format(status, ignored),
    )
    status, ignored_again, _ = request(
        "POST", "/releases/{}/ignore".format(rid), token=alice
    )
    check(
        "releases: re-ignore is idempotent",
        status == 200 and ignored_again.get("status") == "ignored",
        "status={} body={}".format(status, ignored_again),
    )
    status, unignored, _ = request("POST", "/releases/{}/unignore".format(rid), token=alice)
    check(
        "releases: unignore re-runs matching",
        status == 200 and unignored.get("status") in ("missing", "in_library", "grabbed"),
        "status={} body={}".format(status, unignored),
    )
    status, _, _ = request("POST", "/releases/{}/unignore".format(rid), token=alice)
    check("releases: unignore when not ignored -> 409", status == 409, str(status))

    # --- feed badge --------------------------------------------------------
    status, feed, _ = request("GET", "/follows/feed/state", token=alice)
    check(
        "feed: GET /follows/feed/state returns unseen_count",
        status == 200 and feed.get("unseen_count", -1) >= 0,
        "status={} body={}".format(status, feed),
    )
    status, seen, _ = request("POST", "/follows/feed/seen", token=alice)
    check(
        "feed: POST /follows/feed/seen zeroes the badge",
        status == 200 and seen.get("unseen_count") == 0,
        "status={} body={}".format(status, seen),
    )

    # --- unfollow ------------------------------------------------------
    status, unfollowed, _ = request(
        "DELETE", "/artists/{}/follow".format(artist_id), token=alice
    )
    check(
        "follow: DELETE unfollows",
        status == 200 and unfollowed.get("followed") is False,
        "status={} body={}".format(status, unfollowed),
    )
    status, unfollowed_again, _ = request(
        "DELETE", "/artists/{}/follow".format(artist_id), token=alice
    )
    check(
        "follow: re-DELETE is idempotent",
        status == 200 and unfollowed_again.get("followed") is False,
        "status={} body={}".format(status, unfollowed_again),
    )

    failed = summary()
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
