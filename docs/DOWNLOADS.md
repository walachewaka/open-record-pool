# Music download engine (MOO-78)

Pluggable acquisition backends that fetch a track from a public provider URL
into the managed library, capture its source metadata, and run it through the
existing tag-extraction → analyzer → dedup → Elasticsearch pipeline.

Providers:

| Provider | Tool | Notes |
|----------|------|-------|
| YouTube | [yt-dlp](https://github.com/yt-dlp/yt-dlp) | audio extracted to mp3 |
| SoundCloud | [scdl](https://github.com/scdl-org/scdl) | metadata probed via yt-dlp |
| Spotify | [spotDL](https://github.com/spotDL/spotify-downloader) | resolves Spotify **metadata**, fetches matching audio from YouTube Music |

## 1. Disabled by default (operator choice)

All three providers ship **disabled**. The instance owner opts in per provider
in **Admin → Settings → Integrations → Download engine**. The ToS/legality of
ripping varies by source and jurisdiction; this is a self-hosted, operator-choice
integration, surfaced as explicit opt-in toggles — not a policy baked into code.

spotDL never touches Spotify DRM audio: it reads Spotify metadata anonymously and
downloads the matching audio from YouTube Music. No Spotify account, no OAuth, no
DRM circumvention. yt-dlp/scdl fetch from sources whose ToS vary by jurisdiction.

Settings keys (group `integrations`, all default off):
`downloads_enabled`, `downloads_youtube`, `downloads_soundcloud`,
`downloads_spotify`, `downloads_require_approval` (fetched tracks enter the
moderation queue), `downloads_daily_limit` (per-user/UTC-day cap, 0 = unlimited).

## 2. Who can submit

Submission is gated by the existing **`upload_tracks`** permission — fetching a
URL into the library is semantically a remote upload. By default owner/admin/
curator hold it; grant it to members via the Roles matrix if desired. Member
song *requests* with their own moderation flow are a later stage (MOO-81) that
calls the internal `enqueue_download(...)` API.

## 3. Lifecycle & UI

`queued → fetching → postprocessing → imported` (or `duplicate_skipped`,
`failed`, `cancelled`). Progress and the failure reason are surfaced in the
member **Downloads → Fetch** tab and the admin **/admin/downloads** oversight
view. Downloads never block API requests — submission returns `202` immediately
and the work runs on the `worker-heavy` tier.

Downloads **require the worker tier**. With `WORKERS_ENABLED=false` submission
returns `503` (the single-image variant does not offer downloads). Files land in
the sharded managed library (`/library/audio/aa/bb/<sha256>.mp3`), never the
read-only `/music` mount.

## 4. Optional credentials (env only)

None are required for public content. All are passed to the tool subprocess as
argv only and never written to the DB or logs (token values are redacted).

| Env var | Provider | Effect |
|---------|----------|--------|
| `SPOTIFY_CLIENT_ID` + `SPOTIFY_CLIENT_SECRET` | Spotify | a free developer app avoids shared-key rate limiting (both must be set) |
| `SOUNDCLOUD_AUTH_TOKEN` | SoundCloud | OAuth token from the operator's browser session; unlocks higher-quality streams |
| `YTDLP_COOKIES_FILE` | YouTube | path to a mounted Netscape `cookies.txt` for age-restricted content |

Tuning: `DOWNLOAD_TIMEOUT_SECONDS` (900), `DOWNLOAD_MAX_FILE_MB` (200),
`DOWNLOAD_PROVIDER_CONCURRENCY` (2), `DOWNLOAD_PROVIDER_DELAY_SECONDS` (10).

## 5. Security posture (SECURITY.md item 9)

This is the platform's primary SSRF surface. `src/security/urlcheck.py`
validates every submitted URL, at submission and again in the worker:

- scheme must be exactly `https`; no userinfo; no port other than 443
- hostname must **exact-match** an allowlisted provider host (no suffix match,
  so `youtube.com.evil.com` is rejected); IP-literal hosts rejected
- the host is resolved and rejected if **any** address is private, loopback,
  link-local, multicast, reserved, unspecified, CGNAT (`100.64/10`) or the
  `169.254/16` metadata range
- per-provider canonicalization to a single track; playlists/albums/sets → `422`
- URL shorteners (e.g. `on.soundcloud.com`) are **not** allowlisted — paste the
  expanded URL

Tools run as pinned CLI subprocesses in isolated venvs (`/opt/tools/*`), invoked
with argv arrays only (never a shell string), a scrubbed env, a private per-
request workdir, and a hard timeout. We never follow redirects ourselves; the
tools follow redirects to their own CDNs (googlevideo.com, sndcdn.com), which is
provider-controlled and out of allowlist scope by design.

## 6. Tool pins & update cadence

Pins live in `backend/tools/{yt-dlp,scdl,spotdl}.txt` and are installed into
per-tool venvs by the Dockerfile. pip-audit does **not** scan these venvs (they
are subprocess-isolated). **Refresh the pins monthly** and rebuild:

```
# bump the version in backend/tools/<tool>.txt, then
docker compose build backend && docker compose up -d backend worker-heavy
```

yt-dlp in particular will break against YouTube if left stale — a yt-dlp
breakage is a **provider outage, not a security event**. The deployed tool
versions are visible in the admin UI (`GET /fetch/providers`).

Troubleshooting: most `failed` requests with `error_kind=network`/`tool` on
YouTube are a stale yt-dlp pin — bump and rebuild first.
