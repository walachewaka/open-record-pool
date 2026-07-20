# Telemetry & dashboards (MOO-83)

Open Record Pool records what happens in the pool as Elasticsearch documents and
charts them with four Grafana dashboards embedded in the admin panel
(**Admin → Insights**, `/admin/insights`).

Two promises shape the whole design:

1. **Telemetry never degrades the app.** Emitting an event is a dict build and a
   deque append — no network call, no await, no Redis. If Elasticsearch is down,
   slow, or absent, users notice nothing at all; the events are buffered, then
   dropped (oldest first, with a counter) if the buffer fills.
2. **PostgreSQL stays authoritative.** Play counts, downloads, quota and the
   security audit log are still PG rows and are still what the app reads.
   Telemetry is an additive projection for analytics. Nothing reconciles the two,
   by design.

## What is collected

Every document carries `@timestamp`, `event`, `user_id`, `username`,
`hour_of_day` and `day_of_week`. Track events also carry `song_id`,
`song_label` ("Artist - Title"), `artist`, `genre` and `duration_ms`.

| event | emitted when | notable fields |
|---|---|---|
| `play.start` | a member starts a track | — |
| `play.complete` / `play.skip` | the player beacon reports the end of a play | `position_ms`, `listened_ms`, `completion_pct` |
| `download` | a track is downloaded | `format`, `attrs.counted_against_quota` |
| `search.query` | `/search` or a filtered `/songs` listing | `query`, `filters`, `result_count`, `zero_results`, `engine` (`es`\|`pg`) |
| `import.track` | a song row is created | `source` (`library-scan` \| `upload`) |
| `enrichment.applied` | Beatport metadata is written onto a song | `source`, `fields` |
| `export.crate` | a DJ bundle or M3U is exported | `crate_id`, `format`, `track_count` |
| `request.created` / `.approved` / `.rejected` / `.fulfilled` | the song-request funnel | `request_id`, `source` |
| `job.finished` | any background job reaches a terminal state | `job_kind`, `job_status`, `queue`, `duration_ms`, `error` |
| `api.request` | sampled API calls (5xx always) | `method`, `route` (template, never the raw path), `status_code`, `duration_ms` |
| `auth.login` | shipped from the audit log | `success`, `ip` |
| `audit.*` | every other audit row | `audit_event`, `target_type`, `target_id`, `ip` |

A play counts as **complete** when the player reached the end or got past 85% of
the track; otherwise it is a **skip**. That classification needs the browser
(only it knows how far the user actually got), which is what
`POST /telemetry/beacon` is for.

## Privacy / consent

`TELEMETRY_LEVEL` is the operator's lever:

- `off` — nothing is collected at all.
- `basic` — business events only: no `api.request`, and `search.query` keeps the
  result count and the zero-result flag but **not** the raw query string.
- `detailed` (default) — everything in the table above.

Telemetry is also automatically inert wherever `ELASTICSEARCH_URL` is unset (the
single-image build, for instance). Events are **not** pseudonymized: this is a
self-hosted tool, the operator already owns the authoritative user table in
Postgres, and per-user panels ("top listeners") are a stated goal. If that is not
wanted, `basic` — or `off` — is the answer, not hashing.

## Retention

Raw events live in monthly indices `orp-events-YYYY.MM`. The ILM policy
`orp-events-retention` deletes an index `TELEMETRY_RETENTION_DAYS` (default
**180**) after it is created. Because a monthly index ages from its creation
date rather than rolling over, effective raw retention is 180–210 days.

## Grafana

Grafana runs in the compose stack and is **deliberately not published — not even
on 127.0.0.1**. It uses `auth.proxy`, which means *anything that can reach port
3000 can impersonate any user by setting a header*. Publishing that port would
hand out admin access to every process on the host.

The only supported way in is the backend's authenticated reverse proxy:

```
browser → GET /admin/grafana/... (ORP backend, requires the view_reports permission)
        → strips every client-supplied X-WEBAUTH-* header
        → injects X-WEBAUTH-USER: <caller>, X-WEBAUTH-ROLE: Admin|Viewer
        → grafana:3000 (docker-internal)
```

Owners get Grafana's `Admin` role, everyone else who has `view_reports` gets
`Viewer`. The ORP session cookie is never forwarded upstream.

Dashboards and the Elasticsearch datasource are provisioned **as code** from
`docker/grafana/` (`orp-listening`, `orp-library`, `orp-engagement`,
`orp-system`); UI edits are disabled so a dashboard cannot drift away from the
repository.

If you really need raw Grafana access (to build a new panel interactively), add a
local `docker-compose.override.yml`:

```yaml
services:
  grafana:
    ports:
      - "127.0.0.1:3000:3000"
```

...log in with `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD`, and **remove the
override again** — while it is in place, any local process can impersonate any
user through the auth-proxy header.

## Configuration

| variable | default | meaning |
|---|---|---|
| `TELEMETRY_ENABLED` | `true` | master switch |
| `TELEMETRY_LEVEL` | `detailed` | `off` \| `basic` \| `detailed` |
| `TELEMETRY_BUFFER_MAX` | `5000` | per-process event buffer; overflow drops the oldest |
| `TELEMETRY_FLUSH_INTERVAL_SECONDS` | `2` | flush cadence |
| `TELEMETRY_FLUSH_MAX_BATCH` | `500` | documents per `_bulk` |
| `TELEMETRY_API_SAMPLE_RATE` | `0.1` | share of `api.request` events kept (5xx always kept) |
| `TELEMETRY_RETENTION_DAYS` | `180` | ILM delete age |
| `GRAFANA_URL` | `http://grafana:3000` | upstream for the proxy |
| `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD` | `admin` / `grafana-dev` | Grafana's own admin account |

**In production** (`ORP_ENV=production`) the backend refuses to boot unless
`GRAFANA_ADMIN_PASSWORD` is set, at least 12 characters, and not the committed
dev value.

## Operating it

- **Health:** Admin → Insights shows chips for telemetry level, Elasticsearch,
  Grafana, buffer depth, dropped events and retention. The same data is at
  `GET /admin/telemetry/status`.
- **Events are missing:** check `es_reachable` on that card. Nothing is lost
  while the buffer holds; beyond `TELEMETRY_BUFFER_MAX` events the oldest are
  dropped and `events_dropped` climbs.
- **Dashboards are blank:** they only show what has happened *since telemetry was
  switched on* — there is no backfill from the PG history (deliberately: the two
  stores are independent).
- **Verify the pipeline:** `qa/harness_telemetry.py`, run inside the backend
  container against the live stack like the other harnesses.
