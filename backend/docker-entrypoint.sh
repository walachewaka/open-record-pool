#!/bin/sh
#
# Backend container entrypoint.
#
# Runs the SQL migrations automatically before starting the app, so that a plain
# `docker compose up` is all that is needed -- no manual `aerich upgrade` step
# (#22).
set -e

echo "[entrypoint] waiting for the database..."
python wait_for_db.py

# aerich 0.6.x reads its config from pyproject.toml and refuses to run against the
# old aerich.ini ("You need run aerich init again when upgrade to 0.6.0+"). Running
# `aerich init` regenerates that config; it is non-destructive to existing
# migration files and safe to run on every start.
echo "[entrypoint] configuring aerich..."
aerich init -t src.database.config.TORTOISE_ORM || true

echo "[entrypoint] applying database migrations (aerich upgrade)..."
# Applies any pending migration files. On a fresh database this creates the
# schema and the aerich bookkeeping table; on later starts it is a no-op
# ("No upgrade items found").
aerich upgrade

echo "[entrypoint] starting backend: $*"
exec "$@"
