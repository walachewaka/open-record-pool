# Salvage restore notes (MOO-95)

This repo was reconstructed on 2026-07-10 after the Multica daemon GC deleted the
only checkout of `open-record-pool` (branch `dev`, 41 local-only commits ahead of
`origin/dev @ 3079c0b`, never pushed) along with all uncommitted test harnesses.
Source of the restore: the MOO-91 salvage zip (`open-record-pool-salvage-moo91.zip`),
which was recovered from the running Docker images and containerd snapshots.

## What this repo IS
A faithful reconstruction of the **final `dev` HEAD tree** (foundation-block work
MOO-65..MOO-94), including the MOO-91 QA fix to `backend/src/analysis/engine.py::fingerprint`.
It is NOT a continuation of the original `.git` history — that history is gone.

## Recovered verbatim from the salvage
- `backend/` — complete final tree (src, migrations 1–11, pyproject, requirements,
  entrypoints, scripts), copied from the running `backend:latest` image.
- `frontend/` — complete final build context (src, public, package.json + lockfile,
  Dockerfile, nginx.conf, audit-gate.js, audit-ignore.txt), byte-identical to the
  shipped build (containerd snapshot 147 COPY-layer cache hit).
- `CLAUDE.md` — verbatim repo-root copy.
- `docker/nginx-allinone.conf`, `docker/supervisord.conf` — single-image variant helpers.

## Reconstructed (not verbatim — verify before trusting)
- `backend/Dockerfile` — rebuilt from `docker history backend:latest`; layer order
  and commands mirror the running image. The original file was lost.
- `docker-compose.yml` — rebuilt from `docker inspect` of the 8 running containers
  (`compose-inspect.json`): backend, worker, worker-heavy, frontend, db (postgres:14),
  redis, elasticsearch (8.14.3), adminer. Ports/env/mounts/ES healthcheck mirror the
  live stack. DB password + SECRET_KEY are the dev defaults that were baked into the
  running stack — rotate for real deployments.
- `docker-compose.override.example.yml` — documents the (gitignored) local /music bind.

## Permanently lost (no copy existed anywhere)
- `.git` history: the 41 commit messages / diffs / authorship.
- `docs/` (ARCHITECTURE.md, BACKUP_RESTORE.md), root README.md / INSTALL.md /
  CONTRIBUTING.md / SECURITY.md / CHANGELOG.md, `sh_*.sh` helper scripts, `.gitattributes`.
- `docker-compose.singleimage.yml` and the root single-image `Dockerfile`
  (the `docker/` helpers survive; the Dockerfile that used them does not).
- `adminer/` plugin content (placeholder kept so the compose mount stays valid).
- All test harnesses / e2e suites (`harness*.py`, `e2e_*.py`, `fake_es.py`,
  `make_fixtures.py` — ~700+ checks). Re-authoring is tracked separately (out of MOO-95 scope).

## Do NOT destroy the live evidence
The running compose stack (images `backend:latest`/`frontend:latest`, and the
postgres/library/uploads/ES/redis volumes) is the remaining source of truth.
`docker compose down -v`, `docker system prune`, or an image rebuild without this
salvage would destroy it.
