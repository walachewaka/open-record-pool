"""
Wait for the PostgreSQL database to accept connections.

Used by the backend Docker entrypoint so that migrations only run once the
database is actually ready (#22).
"""
import asyncio
import os
import sys

import asyncpg

# Strip query params (e.g. Tortoise pool bounds like ?minsize=1&maxsize=20 —
# MOO-77): asyncpg.connect would forward them to the server as unrecognized
# configuration parameters.
DATABASE_URL = (os.environ.get("DATABASE_URL") or "").split("?")[0]
ATTEMPTS = int(os.environ.get("DB_WAIT_ATTEMPTS", "60"))


async def wait() -> None:
    if not DATABASE_URL:
        sys.exit("[wait_for_db] DATABASE_URL is not set")
    last_error = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            conn = await asyncpg.connect(DATABASE_URL)
            await conn.close()
            print(f"[wait_for_db] database is ready (attempt {attempt})")
            return
        except Exception as exc:  # noqa: BLE001 - we retry on any connection error
            last_error = exc
            print(f"[wait_for_db] not ready yet (attempt {attempt}/{ATTEMPTS}): {exc}")
            await asyncio.sleep(1)
    sys.exit(f"[wait_for_db] database did not become ready in time: {last_error}")


if __name__ == "__main__":
    asyncio.run(wait())
