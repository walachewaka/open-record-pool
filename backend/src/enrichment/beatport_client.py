"""
Beatport API v4 HTTP client (MOO-85). Only ever constructed inside a worker
job (src/jobs/tasks_enrichment.py) or via src.enrichment.provider.get_client()
-- MOO-77 D2: external HTTP calls happen inside worker jobs, never request
handlers.

- D1 auth: OAuth2 client-credentials against `POST {base}/auth/o/token/`, an
  in-process (per-client-instance) token cache that refreshes before expiry
  and retries exactly once on a 401.
- D2 outbound policy: a hard allowlist to the configured API host (no
  off-host redirects -- follow_redirects=False and any redirect response is
  an error), a request timeout, and an asyncio token-bucket rate limiter
  shared across every call this client instance makes.
- D3 caching: every GET is a Postgres read-through cache
  (BeatportCache, keyed by sha1(method+url+params)) with a long default TTL.

Credentials (BEATPORT_CLIENT_ID / BEATPORT_CLIENT_SECRET) come from the
environment only and are never logged (the auth request body/response are
never printed; failures only ever raise a message built from the status
code, never the response body).

Every method returns tracks already normalized to this payload shape (the
MOO-82 contract -- also documented in the SongEnrichment.payload docstring
in src/database/models.py, and produced identically by
src/enrichment/mock_client.py's fixtures so scoring never has to care which
client answered):

    {
        "beatport_track_id": int, "name": str, "mix_name": str|None,
        "artists": [str, ...], "remixers": [str, ...],
        "genre": str|None, "subgenre": str|None, "label": str|None,
        "catalog_number": str|None, "release_name": str|None,
        "release_id": int|None, "release_date": str|None (ISO date),
        "isrc": str|None, "bpm": float|None, "key": str|None,
        "duration_seconds": float|None, "artwork_url": str|None,
    }
"""
import asyncio
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import httpx

from src.database.models import BeatportCache

logger = logging.getLogger("orp.enrichment.beatport")


class BeatportError(Exception):
    """Any non-recoverable failure talking to the Beatport API."""


def _api_base():
    return os.environ.get("BEATPORT_API_BASE", "https://api.beatport.com/v4").rstrip(
        "/"
    )


def _allowed_host():
    return (urlsplit(_api_base()).hostname or "api.beatport.com").lower()


def _timeout():
    return float(os.environ.get("BEATPORT_TIMEOUT_SECONDS", "15"))


def _rate_limit_rps():
    return float(os.environ.get("BEATPORT_RATE_LIMIT_RPS", "2"))


def _cache_ttl_hours():
    return float(os.environ.get("BEATPORT_CACHE_TTL_HOURS", "720"))


def _client_id():
    return os.environ.get("BEATPORT_CLIENT_ID", "").strip()


def _client_secret():
    return os.environ.get("BEATPORT_CLIENT_SECRET", "").strip()


def artwork_url_ok(url):
    """
    Artwork URLs are only ever accepted (stored) if https and the host is
    beatport.com or a subdomain of it -- an attacker-controlled or
    Beatport-CDN-impersonating URL in a crafted API response is never
    surfaced to the review UI.
    """
    if not url:
        return False
    parts = urlsplit(url)
    if parts.scheme != "https":
        return False
    host = (parts.hostname or "").lower()
    return host == "beatport.com" or host.endswith(".beatport.com")


class _TokenBucket:
    """A tiny asyncio token bucket shared by every call one client makes."""

    def __init__(self, rate_per_second, burst=2):
        self._rate = max(rate_per_second, 0.01)
        self._capacity = max(burst, 1)
        self._tokens = float(self._capacity)
        self._updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self._updated
                self._updated = now
                self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait = (1.0 - self._tokens) / self._rate
                await asyncio.sleep(wait)


def _cache_key(method, url, params):
    normalized = json.dumps(params or {}, sort_keys=True, separators=(",", ":"))
    raw = "{}|{}|{}".format(method.upper(), url, normalized)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


class BeatportClient:
    """
    A per-instance Beatport API v4 client. The token cache and rate limiter
    are stateful and process-local by design (D1/D2) -- construct one per
    worker task, or reuse one across a batch of calls in the same job (the
    backfill walker does the latter).
    """

    def __init__(self):
        self._token = None
        self._token_expires_at = 0.0
        self._bucket = _TokenBucket(_rate_limit_rps())

    async def _fetch_token(self):
        client_id = _client_id()
        client_secret = _client_secret()
        if not client_id or not client_secret:
            raise BeatportError("Beatport credentials are not configured")
        url = "{}/auth/o/token/".format(_api_base())
        async with httpx.AsyncClient(
            timeout=_timeout(), follow_redirects=False
        ) as client:
            response = await client.post(
                url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
            )
        if response.is_redirect:
            raise BeatportError("Beatport auth endpoint returned a redirect")
        if response.status_code != 200:
            # Never include the response body: it could echo request
            # parameters back, and we must never risk logging a secret.
            raise BeatportError(
                "Beatport auth failed with status {}".format(response.status_code)
            )
        data = response.json()
        token = data.get("access_token")
        if not token:
            raise BeatportError("Beatport auth response had no access_token")
        expires_in = float(data.get("expires_in") or 3600)
        self._token = token
        self._token_expires_at = time.monotonic() + expires_in - 60  # refresh early
        return token

    async def _ensure_token(self):
        if self._token is None or time.monotonic() >= self._token_expires_at:
            await self._fetch_token()
        return self._token

    def _assert_allowed(self, url):
        host = (urlsplit(url).hostname or "").lower()
        if host != _allowed_host():
            raise BeatportError("Refusing to call disallowed host: {}".format(host))

    async def _request(self, method, url, params=None, retry_on_401=True):
        self._assert_allowed(url)
        await self._bucket.acquire()
        token = await self._ensure_token()
        async with httpx.AsyncClient(
            timeout=_timeout(), follow_redirects=False
        ) as client:
            response = await client.request(
                method,
                url,
                params=params,
                headers={"Authorization": "Bearer {}".format(token)},
            )
        if response.is_redirect:
            raise BeatportError("Beatport API returned an off-host redirect")
        if response.status_code == 401 and retry_on_401:
            self._token = None  # force a fresh token, single retry (D1)
            return await self._request(method, url, params=params, retry_on_401=False)
        if response.status_code >= 400:
            raise BeatportError(
                "Beatport API {} {} failed with status {}".format(
                    method, url, response.status_code
                )
            )
        return response.json()

    async def _cached_get(self, path, params=None):
        url = "{}{}".format(_api_base(), path)
        self._assert_allowed(url)
        key = _cache_key("GET", url, params)
        row = await BeatportCache.get_or_none(cache_key=key)
        now = datetime.now(timezone.utc)
        if row is not None and row.expires_at > now:
            return row.response
        data = await self._request("GET", url, params=params)
        expires_at = now + timedelta(hours=_cache_ttl_hours())
        await BeatportCache.update_or_create(
            cache_key=key,
            defaults={"url": url, "response": data, "expires_at": expires_at},
        )
        return data

    async def search_tracks(self, query, per_page=25):
        """Beatport track search, normalized. Empty list on zero hits."""
        data = await self._cached_get(
            "/catalog/search",
            params={"type": "tracks", "q": query, "per_page": per_page},
        )
        raw_tracks = data.get("results") or data.get("tracks") or []
        return [_normalize_track(raw) for raw in raw_tracks]

    async def get_track(self, track_id):
        """One Beatport track by id, normalized."""
        raw = await self._cached_get("/catalog/tracks/{}".format(track_id))
        return _normalize_track(raw)


def _artist_names(raw_artists):
    names = []
    for artist in raw_artists or []:
        name = artist.get("name") if isinstance(artist, dict) else artist
        if name:
            names.append(name)
    return names


def _normalize_track(raw):
    """
    Map a raw Beatport v4 track dict onto the MOO-85 payload shape (module
    docstring). Never raises on a missing/renamed upstream field -- an
    unexpected shape degrades to None values rather than breaking a whole
    search.
    """
    release = raw.get("release") or {}
    label = release.get("label") or {}
    genre = raw.get("genre") or {}
    sub_genre = raw.get("sub_genre") or raw.get("subgenre") or {}
    key = raw.get("key") or {}
    image = raw.get("image") or release.get("image") or {}
    artwork_url = (
        image.get("uri") or image.get("url") if isinstance(image, dict) else None
    )
    if not artwork_url_ok(artwork_url):
        artwork_url = None

    duration_seconds = raw.get("duration_seconds")
    length_ms = raw.get("length_ms")
    if duration_seconds is None and length_ms is not None:
        try:
            duration_seconds = float(length_ms) / 1000.0
        except (TypeError, ValueError):
            duration_seconds = None

    return {
        "beatport_track_id": raw.get("id"),
        "name": raw.get("name") or raw.get("title"),
        "mix_name": raw.get("mix_name"),
        "artists": _artist_names(raw.get("artists")),
        "remixers": _artist_names(raw.get("remixers")),
        "genre": genre.get("name") if isinstance(genre, dict) else genre,
        "subgenre": sub_genre.get("name") if isinstance(sub_genre, dict) else sub_genre,
        "label": label.get("name") if isinstance(label, dict) else label,
        "catalog_number": release.get("catalog_number") or raw.get("catalog_number"),
        "release_name": release.get("name"),
        "release_id": release.get("id"),
        "release_date": raw.get("publish_date") or raw.get("release_date"),
        "isrc": raw.get("isrc"),
        "bpm": raw.get("bpm"),
        "key": key.get("name") if isinstance(key, dict) else key,
        "duration_seconds": duration_seconds,
        "artwork_url": artwork_url,
    }
