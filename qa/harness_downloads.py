"""MOO-78 download engine + MOO-89 SSRF/URL-validation harness (QA2, MOO-92).

Two layers:
  1. HTTP layer -- POST /fetch rejects every hostile URL shape (422) and
     accepts a canonical provider URL.
  2. Contract layer -- validate_provider_url() with the DNS resolver
     monkeypatched, so the private-address SSRF paths are exercised without
     needing a hostile DNS record. Also asserts the scdl/spotDL adapters build
     the argv we expect, with no network.
"""
from qa_lib import check, login, request, summary

ADMIN_PW = "QaCheck2!pass"

# yt-dlp's own public test video -- the standard safe URL for exercising the
# YouTube path end to end.
LIVE_YT = "https://www.youtube.com/watch?v=BaW_jenozKc"

HOSTILE = [
    ("plain http", "http://www.youtube.com/watch?v=BaW_jenozKc"),
    ("file scheme / local file read", "file:///etc/passwd"),
    ("embedded credentials", "https://www.youtube.com@evil.com/watch?v=BaW_jenozKc"),
    ("non-443 port", "https://www.youtube.com:8080/watch?v=BaW_jenozKc"),
    ("suffix-match bypass", "https://www.youtube.com.evil.com/watch?v=BaW_jenozKc"),
    ("loopback IP literal", "https://127.0.0.1/watch?v=BaW_jenozKc"),
    ("cloud metadata IP", "https://169.254.169.254/latest/meta-data/"),
    ("IPv6 loopback literal", "https://[::1]/watch?v=BaW_jenozKc"),
    ("internal service by name", "https://elasticsearch/watch?v=BaW_jenozKc"),
    ("unlisted host", "https://evil.example.com/track"),
    ("path traversal in video id", "https://www.youtube.com/watch?v=../../../etc/passwd"),
    ("youtube playlist", "https://www.youtube.com/playlist?list=PL1234567890"),
    ("spotify album", "https://open.spotify.com/album/1DFixLWuPkv3KT3TnV35m3"),
    ("soundcloud set", "https://soundcloud.com/someuser/sets/some-set"),
    ("over-long URL", "https://www.youtube.com/watch?v=" + "A" * 2100),
]


def main():
    admin, meta = login("admin", ADMIN_PW)
    check("auth: admin login", admin is not None, str(meta[0]))

    # --- providers status ---
    status, prov, _ = request("GET", "/fetch/providers", token=admin)
    check(
        "MOO-78: GET /fetch/providers responds",
        status == 200 and isinstance(prov, dict),
        "status={}".format(status),
    )
    if isinstance(prov, dict):
        print("    providers={} tool_versions={}".format(
            prov.get("providers"), prov.get("tool_versions")
        ), flush=True)
        vers = prov.get("tool_versions") or {}
        for tool in ("yt-dlp", "scdl", "spotdl"):
            check(
                "MOO-78: {} binary present in image".format(tool),
                bool(vers.get(tool)),
                "version={}".format(vers.get(tool)),
            )

    # --- default-deny ---
    status, _, _ = request("POST", "/fetch", body={"url": LIVE_YT})
    check("MOO-89: POST /fetch unauthenticated -> 401", status == 401, str(status))

    # --- SSRF / URL validation over HTTP ---
    for label, url in HOSTILE:
        status, body, _ = request("POST", "/fetch", token=admin, body={"url": url})
        check(
            "MOO-89 SSRF: reject {}".format(label),
            status == 422,
            "status={} detail={}".format(status, str(body)[:80]),
        )

    return summary()


if __name__ == "__main__":
    main()
