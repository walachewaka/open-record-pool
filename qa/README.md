# QA harnesses (rebuilt for MOO-92, QA checkpoint 2)

The original harness scripts and the Playwright suite were lost with the
workspace GC (MOO-95). These are the replacements written during QA checkpoint
2. They are **stdlib-only** and drive the live stack over HTTP, so they run
inside the backend container with no extra dependencies.

Nothing here is wired into the image build, so it cannot break `docker compose
build` (the backend Dockerfile only lints `backend/`).

## Running

Copy them into the running backend container and run them:

```sh
docker compose exec -T backend mkdir -p /tmp/qa
docker cp qa/. open-record-pool-backend-1:/tmp/qa/
docker compose exec -T -w /tmp/qa backend python harness_regression.py
```

| Script | Covers |
| --- | --- |
| `harness_regression.py` | checkpoint-1 sweep: songs, search/ES, crates, jobs, sessions, default-deny |
| `harness_playlists.py` | MOO-84 crate CRUD, track add/remove, public vs private, cross-user IDOR |
| `harness_requests.py` | MOO-81 submit/approve/reject/cancel + the request → download → ingest → ES chain |
| `harness_dedup_skip.py` | MOO-90 pre-download dedup: an in-library track is fulfilled from the library, never re-downloaded |
| `harness_downloads.py` | MOO-78 provider status + MOO-89 SSRF/URL rejection over HTTP |
| `harness_providers.py` | MOO-78 scdl/spotDL argv contracts + SSRF resolver tests (no network) |
| `harness_sso.py` | MOO-88 OIDC login against a local Dex IDP (`closed` and `open` provisioning) |
| `harness_enrichment.py` | MOO-85 Beatport enrichment: scoring/normalization units (no network), the mock enrich→apply flow, review workflow (needs_review/reject/accept-subset), field-lock rescan survival, and the disabled-mode contract |
| `harness_export.py` | MOO-86 DJ crate export: key-notation table, path confinement, ID3 rewrite on the copies (GEOB cues survive, originals untouched), the three bundle layouts (Serato `.crate` round-trip-parsed, Traktor NML, rekordbox XML), request guards, IDOR on poll/download, 410 after the artifact is swept |
| `ui_playlists.py` | MOO-84 playlist UI in a real browser (Playwright, run from the host) |

`harness_requests.py` and `harness_dedup_skip.py` expect the two members
`qa2_alice` / `qa2_bob` that `harness_playlists.py` creates; run that one first.

`harness_enrichment.py`'s mock-dependent checks (the enrich→apply flow, review
workflow, and rescan survival) only run meaningfully with `BEATPORT_MOCK=true`
on `backend`/`worker-heavy` (e.g. `BEATPORT_MOCK=true docker compose up -d
backend worker worker-heavy`); with the provider at its default disabled
state the harness instead asserts the clean disabled-mode contract (status
reason, 503 on trigger) and skips the rest. It temporarily edits two existing
songs' artist/title/genre via `PATCH /admin/content/{id}` and restores their
original values when it finishes.

## The QA compose overlay

`docker-compose.qa.yml` is **opt-in** -- it is deliberately not named
`docker-compose.override.yml`, so the normal stack never picks it up:

```sh
docker compose -f docker-compose.yml -f qa/docker-compose.qa.yml up -d
```

It adds two things the tests need and production must never have:

* `ORP_FAKE_DOWNLOADS=true` -- the network-free provider adapter. YouTube
  bot-checks unauthenticated datacenter IPs, so a real yt-dlp fetch cannot
  complete in CI; the fake adapter serves a real parseable MP3 for the fixture
  URL `https://www.youtube.com/watch?v=ORPFIXTURE1`, which lets the whole
  download → import → analyze → dedup → ES chain run for real.
* `dex-oidc` -- a local Dex OpenID Connect provider (`dex-config.yaml`), because
  no real Entra/Google/Okta client registrations exist for this pool. Set
  `OIDC_MOCK_PROVISIONING=closed|open` to exercise both sides of the
  provisioning gate.
