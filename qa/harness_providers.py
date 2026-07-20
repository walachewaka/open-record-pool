"""MOO-78 provider contract tests with NO network + MOO-89 SSRF resolver tests.

The yt-dlp path is exercised live against YouTube elsewhere. SoundCloud (scdl)
and Spotify (spotDL) have no usable live credentials/URLs in this environment,
so they are contract-tested here: the argv each adapter builds, the secret
redaction, the URL canonicalization, and -- with the DNS resolver monkeypatched
-- the private-address SSRF rejections that a real hostile DNS record would
trigger.
"""
import asyncio

from qa_lib import check, summary

from src.downloads.providers import get_adapter, reset_registry
from src.downloads.providers.base import redact_argv
from src.downloads.providers.soundcloud import SoundCloudAdapter
from src.downloads.providers.spotify import SpotifyAdapter
from src.security import urlcheck


def main():
    reset_registry()

    # ---------- canonicalization (no network) ----------
    cases = [
        (
            "https://m.youtube.com/watch?v=dQw4w9WgXcQ&feature=share",
            "youtube",
            "dQw4w9WgXcQ",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        ),
        (
            "https://youtu.be/dQw4w9WgXcQ",
            "youtube",
            "dQw4w9WgXcQ",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        ),
        (
            "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT?si=abc",
            "spotify",
            "4cOdK2wGLETKBW3PvgPWqT",
            "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT",
        ),
        (
            "https://soundcloud.com/some-artist/some-track?in=x/sets/y",
            "soundcloud",
            "some-artist/some-track",
            "https://soundcloud.com/some-artist/some-track",
        ),
    ]
    for url, provider, external_id, canonical in cases:
        try:
            got = urlcheck.validate_provider_url(url)
            ok = (
                got.provider == provider
                and got.external_id == external_id
                and got.canonical_url == canonical
            )
            detail = "{} -> {} {}".format(url[:38], got.provider, got.canonical_url)
        except Exception as exc:  # noqa: BLE001
            ok, detail = False, "raised {}".format(exc)
        check("MOO-78: canonicalize {} URL".format(provider), ok, detail)

    # ---------- SSRF: hostile DNS (resolver monkeypatched, no network) ----------
    original = urlcheck._getaddrinfo
    hostile = {
        "loopback": ["127.0.0.1"],
        "private 10/8": ["10.0.0.5"],
        "private 192.168/16": ["192.168.1.10"],
        "link-local metadata 169.254/16": ["169.254.169.254"],
        "CGNAT 100.64/10": ["100.64.0.1"],
        "IPv6 loopback": ["::1"],
        "IPv6 unique-local": ["fc00::1"],
        "mixed public+private (DNS rebinding)": ["142.250.1.1", "10.1.2.3"],
    }
    try:
        for label, addresses in hostile.items():
            urlcheck._getaddrinfo = lambda host, _a=addresses: list(_a)
            try:
                urlcheck.validate_provider_url(
                    "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
                )
                ok, detail = False, "ACCEPTED a host resolving to {}".format(addresses)
            except Exception as exc:  # noqa: BLE001 - HTTPException(422) expected
                ok = getattr(exc, "status_code", None) == 422
                detail = "422: {}".format(getattr(exc, "detail", exc))[:70]
            check("MOO-89 SSRF: host resolving to {} rejected".format(label), ok, detail)

        # a genuinely public address still passes
        urlcheck._getaddrinfo = lambda host: ["142.250.185.78"]
        try:
            got = urlcheck.validate_provider_url(
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
            )
            ok, detail = got.provider == "youtube", got.canonical_url
        except Exception as exc:  # noqa: BLE001
            ok, detail = False, str(exc)
        check("MOO-89 SSRF: a public address is still accepted", ok, detail)
    finally:
        urlcheck._getaddrinfo = original

    # ---------- scdl argv contract (no network) ----------
    sc = SoundCloudAdapter()
    argv = sc.fetch_argv("https://soundcloud.com/a/b", "/tmp/wd")
    check(
        "MOO-78: scdl argv downloads a single track to the workdir as mp3",
        argv[0].endswith("scdl")
        and "-l" in argv
        and "https://soundcloud.com/a/b" in argv
        and "--path" in argv
        and "/tmp/wd" in argv
        and "--onlymp3" in argv,
        " ".join(argv[:8]),
    )
    check(
        "MOO-78: scdl argv carries no auth token when none is configured",
        "--auth-token" not in argv,
        "",
    )
    redacted = redact_argv(
        argv + ["--auth-token", "SUPERSECRET"], redact=("--auth-token",)
    )
    check(
        "MOO-89: the SoundCloud auth token is redacted from tool logging",
        "SUPERSECRET" not in " ".join(redacted),
        " ".join(redacted[-2:]),
    )

    # ---------- spotDL argv contract (no network) ----------
    sp = SpotifyAdapter()
    argv = sp.fetch_argv("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT", "/tmp/wd")
    check(
        "MOO-78: spotDL argv downloads the requested track into the workdir",
        argv[0].endswith("spotdl")
        and any("open.spotify.com/track" in part for part in argv),
        " ".join(argv[:6]),
    )
    check(
        "MOO-78: spotDL argv omits client credentials when unset "
        "(anonymous metadata client)",
        "--client-id" not in argv,
        "",
    )

    # ---------- the registry maps providers to the right adapters ----------
    check(
        "MOO-78: provider registry binds youtube/soundcloud/spotify adapters",
        get_adapter("soundcloud").name == "soundcloud"
        and get_adapter("spotify").name == "spotify"
        and get_adapter("youtube") is not None
        and get_adapter("bogus") is None,
        "",
    )

    return summary()


if __name__ == "__main__":
    asyncio.get_event_loop_policy()
    main()
