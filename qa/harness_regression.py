"""Checkpoint-1 regression sweep (QA2, MOO-92).

Confirms the acquisition/accounts block did not break what checkpoint 1 signed
off: core song flows, ingestion/analyzer/dedup, Elasticsearch search, crates,
auth/sessions, and the admin console.
"""
from qa_lib import check, login, request, summary

ADMIN_PW = "QaCheck2!pass"
USER_PW = "QaUser2!pass"


def main():
    admin, meta = login("admin", ADMIN_PW)
    check("auth: admin login", admin is not None, "status={}".format(meta[0]))
    bob, _ = login("qa2_bob", USER_PW)

    # ---------- core song flows ----------
    status, songs, _ = request("GET", "/songs", token=admin)
    items = songs.get("items", []) if isinstance(songs, dict) else []
    check(
        "regression: GET /songs lists the library",
        status == 200 and len(items) > 0,
        "status={} total={}".format(status, songs.get("total")),
    )
    song_id = items[0]["id"] if items else None

    status, detail, _ = request("GET", "/songs/{}".format(song_id), token=admin)
    check(
        "regression: GET /songs/{id} returns song detail",
        status == 200 and isinstance(detail, dict),
        "status={}".format(status),
    )

    # ---------- analyzer / dedup fields survived ----------
    analyzed = [s for s in items if s.get("bpm") or s.get("bpm_detected")]
    check(
        "regression: analyzer fields (bpm/key) still present on library songs",
        len(analyzed) > 0,
        "{} of {} songs carry bpm".format(len(analyzed), len(items)),
    )

    # ---------- Elasticsearch search ----------
    status, res, _ = request("GET", "/search?q=a", token=admin)
    check(
        "regression: ES search responds",
        status == 200 and isinstance(res, dict) and "items" in res,
        "status={} hits={}".format(
            status, len(res.get("items", [])) if isinstance(res, dict) else "?"
        ),
    )
    status, es_status, _ = request("GET", "/admin/search/status", token=admin)
    check(
        "regression: admin search/index status is healthy",
        status == 200,
        "status={} body={}".format(status, str(es_status)[:90]),
    )

    # ---------- crates (checkpoint-1 CRATE surface) ----------
    status, crates, _ = request("GET", "/crates", token=admin)
    check("regression: GET /crates works", status == 200, "status={}".format(status))

    # ---------- jobs / admin console ----------
    status, jobs, _ = request("GET", "/admin/jobs", token=admin)
    check(
        "regression: admin jobs console lists jobs",
        status == 200,
        "status={} n={}".format(
            status, len(jobs.get("items", [])) if isinstance(jobs, dict) else "?"
        ),
    )
    status, settings, _ = request("GET", "/admin/settings", token=admin)
    check(
        "regression: admin settings readable",
        status == 200 and isinstance(settings, dict),
        "status={}".format(status),
    )

    # ---------- authz: a member must not reach admin surfaces ----------
    for path in ("/admin/settings", "/admin/jobs", "/admin/requests", "/admin/fetch"):
        status, _, _ = request("GET", path, token=bob)
        check(
            "regression/MOO-89: member denied on {}".format(path),
            status == 403,
            "status={}".format(status),
        )

    # ---------- sessions / logout ----------
    status, sessions, _ = request("GET", "/users/me/sessions", token=admin)
    check(
        "regression: session list works",
        status == 200,
        "status={}".format(status),
    )
    status, _, _ = request("POST", "/logout", token=admin)
    check("regression: logout works", status in (200, 204), "status={}".format(status))

    # ---------- unauthenticated access is still denied ----------
    for path in ("/songs", "/search?q=a", "/crates", "/admin/settings"):
        status, _, _ = request("GET", path)
        check(
            "regression/MOO-89: {} unauthenticated -> 401".format(path),
            status == 401,
            "status={}".format(status),
        )

    return summary()


if __name__ == "__main__":
    main()
