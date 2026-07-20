#!/bin/sh
# Entrypoint for the arq worker service (MOO-77). Waits for Postgres, then
# runs the command from docker-compose.yml (arq src.worker.WorkerSettings).
# Deliberately NO aerich here: only the backend migrates, avoiding a
# concurrent-aerich race on fresh databases.
set -e

python wait_for_db.py

exec "$@"
