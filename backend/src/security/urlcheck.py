"""
Provider URL validation and SSRF guard for the music download engine (MOO-78).

This is the platform's primary SSRF surface (SECURITY.md item 9): a user hands
us an arbitrary URL that a worker subprocess will fetch. Every submitted URL
passes through validate_provider_url() before a row is written and again inside
the worker before the tool runs (defense in depth against DB tampering/TOCTOU).

Rules (all violations -> HTTPException 422, never a 500):
  - scheme must be exactly https
  - no userinfo in the netloc (kills https://youtube.com@evil.com/...)
  - no explicit port other than 443
  - hostname must EXACT-match an allowlisted provider host (no suffix or
    substring matching -- kills youtube.com.evil.com)
  - IP-literal hosts are rejected outright
  - URL length <= 2048
  - every address the host resolves to must be public (reject private,
    loopback, link-local, multicast, reserved, unspecified, CGNAT 100.64/10,
    and the 169.254/16 metadata range)
  - per-provider canonicalization to a single-track URL; playlists/albums/sets
    are rejected (v1 is single tracks only)

We never follow redirects ourselves; the tools follow redirects to their own
CDNs (googlevideo.com, sndcdn.com) which is provider-controlled and out of
scope by design (documented in docs/DOWNLOADS.md). URL shorteners
(on.soundcloud.com, youtu.be host aside) are deliberately NOT allowlisted --
users must paste the expanded URL.
"""
import ipaddress
import re
import socket
from collections import namedtuple
from urllib.parse import urlsplit, parse_qs

from fastapi import HTTPException

# Exact-match host allowlist per provider. Membership is by full hostname
# equality only -- never suffix/substring.
PROVIDER_HOSTS = {
    "youtube": {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtu.be",
    },
    "soundcloud": {
        "soundcloud.com",
        "www.soundcloud.com",
        "m.soundcloud.com",
    },
    "spotify": {
        "open.spotify.com",
    },
}

MAX_URL_LENGTH = 2048

ValidatedUrl = namedtuple("ValidatedUrl", ["provider", "external_id", "canonical_url"])

_YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_SPOTIFY_TRACK_PATH = re.compile(r"^(?:/intl-[a-z-]+)?/track/([A-Za-z0-9]{22})$")
_SOUNDCLOUD_PATH = re.compile(r"^/([\w-]+)/([\w-]+)$")


def _reject(detail):
    raise HTTPException(status_code=422, detail=detail)


def _host_of(provider):
    for host, providers in _HOST_INDEX.items():
        if provider in providers:
            yield host


# Reverse index host -> provider for the enable-flag layer (unused here but
# handy for callers); built once.
_HOST_INDEX = {}
for _prov, _hosts in PROVIDER_HOSTS.items():
    for _h in _hosts:
        _HOST_INDEX.setdefault(_h, set()).add(_prov)


def _getaddrinfo(host):
    """
    Resolve a hostname to its addresses. Wrapped so tests can monkeypatch the
    resolution to exercise the private-IP rejection paths without real DNS.
    Returns a list of ip strings.
    """
    infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    return [info[4][0] for info in infos]


def _is_forbidden_address(ip_str):
    """Whether a resolved IP falls in any range we must never fetch from."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        # An address we cannot parse is not one we will trust.
        return True
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return True
    # CGNAT / carrier space (100.64.0.0/10) is not flagged is_private by the
    # stdlib; block it explicitly along with the IPv4 link-local metadata range.
    if isinstance(ip, ipaddress.IPv4Address):
        if ip in ipaddress.ip_network("100.64.0.0/10"):
            return True
        if ip in ipaddress.ip_network("169.254.0.0/16"):
            return True
    return False


def _assert_resolves_public(host):
    """Resolve the host and reject if ANY address is non-public (SSRF)."""
    try:
        addresses = _getaddrinfo(host)
    except socket.gaierror:
        _reject("Could not resolve the host for that URL")
    if not addresses:
        _reject("Could not resolve the host for that URL")
    for address in addresses:
        if _is_forbidden_address(address):
            _reject("That URL resolves to a disallowed (private) address")


def _match_provider(host):
    for provider, hosts in PROVIDER_HOSTS.items():
        if host in hosts:
            return provider
    return None


def _canonical_youtube(host, path, query):
    """Extract the 11-char video id and rebuild a clean watch URL."""
    if "list" in parse_qs(query) or path.startswith("/playlist"):
        _reject("Playlists are not supported yet -- submit a single track URL")
    video_id = None
    if host == "youtu.be":
        candidate = path.lstrip("/").split("/")[0]
        video_id = candidate
    elif path == "/watch":
        values = parse_qs(query).get("v")
        video_id = values[0] if values else None
    elif path.startswith("/shorts/"):
        video_id = path.split("/shorts/", 1)[1].split("/")[0]
    if not video_id or not _YOUTUBE_ID.match(video_id):
        _reject("That does not look like a YouTube track URL")
    return video_id, "https://www.youtube.com/watch?v={}".format(video_id)


def _canonical_spotify(path, query):
    match = _SPOTIFY_TRACK_PATH.match(path)
    if not match:
        if any(seg in path for seg in ("/album/", "/playlist/", "/artist/")):
            _reject("Only single Spotify track URLs are supported")
        _reject("That does not look like a Spotify track URL")
    track_id = match.group(1)
    return track_id, "https://open.spotify.com/track/{}".format(track_id)


def _canonical_soundcloud(path):
    if "/sets/" in path or path.endswith("/sets"):
        _reject(
            "SoundCloud sets/playlists are not supported -- submit a single track URL"
        )
    match = _SOUNDCLOUD_PATH.match(path.rstrip("/"))
    if not match:
        _reject("That does not look like a SoundCloud track URL")
    user, slug = match.group(1), match.group(2)
    external_id = "{}/{}".format(user, slug)
    return external_id, "https://soundcloud.com/{}".format(external_id)


def validate_provider_url(url):
    """
    Validate and canonicalize a user-submitted provider URL.

    Returns a ValidatedUrl(provider, external_id, canonical_url) on success;
    raises HTTPException(422) on any violation. Resolves the host and rejects
    non-public addresses -- callers must be prepared for the DNS lookup.
    """
    if not isinstance(url, str) or not url:
        _reject("A URL is required")
    url = url.strip()
    if len(url) > MAX_URL_LENGTH:
        _reject("URL is too long")

    parts = urlsplit(url)
    if parts.scheme != "https":
        _reject("Only https URLs are accepted")
    if "@" in parts.netloc:
        _reject("URLs with embedded credentials are not accepted")
    if parts.port is not None and parts.port != 443:
        _reject("Only the default https port is accepted")

    host = (parts.hostname or "").lower()
    if not host:
        _reject("The URL has no host")
    # Reject IP-literal hosts (both v4 and v6) up front.
    try:
        ipaddress.ip_address(host)
        _reject("IP-address URLs are not accepted -- use a provider URL")
    except ValueError:
        pass

    provider = _match_provider(host)
    if provider is None:
        _reject(
            "Unsupported host. Paste a full youtube.com, soundcloud.com or "
            "open.spotify.com track URL (short links are not accepted)"
        )

    path = parts.path or "/"
    query = parts.query or ""
    if provider == "youtube":
        external_id, canonical = _canonical_youtube(host, path, query)
    elif provider == "spotify":
        external_id, canonical = _canonical_spotify(path, query)
    else:
        external_id, canonical = _canonical_soundcloud(path)

    # DNS/SSRF check last: only after we know it is a well-formed provider URL.
    _assert_resolves_public(host)

    return ValidatedUrl(
        provider=provider, external_id=external_id, canonical_url=canonical
    )
