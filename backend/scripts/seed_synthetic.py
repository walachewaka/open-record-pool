"""
Synthetic scale seeder (MOO-77): bulk-load 1-5M deterministic song rows
straight into Postgres via asyncpg COPY, for the scale test harness.

Runs inside the backend container:

    docker compose exec backend python scripts/seed_synthetic.py --count 1000000

Deterministic (seeded random): the same count always produces the same rows.
Synthetic rows are recognizable by dedup_key "syn:<i>" and file paths under
/music/synthetic/, so they can be wiped with:

    DELETE FROM songs WHERE dedup_key LIKE 'syn:%';
"""
import argparse
import asyncio
import os
import random
import time

import asyncpg

GENRES = [
    "House",
    "Deep House",
    "Tech House",
    "Progressive House",
    "Electro House",
    "Techno",
    "Melodic Techno",
    "Minimal",
    "Trance",
    "Psytrance",
    "Drum & Bass",
    "Jungle",
    "Dubstep",
    "Garage",
    "Bass",
    "Breakbeat",
    "Hip-Hop",
    "Trap",
    "R&B",
    "Funk",
    "Soul",
    "Disco",
    "Nu-Disco",
    "Indie Dance",
    "Pop",
    "Latin",
    "Reggaeton",
    "Afro House",
    "Amapiano",
    "Ambient",
]

WORDS_A = [
    "Midnight",
    "Neon",
    "Electric",
    "Golden",
    "Silent",
    "Burning",
    "Crystal",
    "Endless",
    "Hidden",
    "Distant",
    "Velvet",
    "Broken",
    "Rising",
    "Falling",
    "Secret",
    "Wild",
]

WORDS_B = [
    "Sunrise",
    "Horizon",
    "Echo",
    "Pulse",
    "Groove",
    "Motion",
    "Dream",
    "Fire",
    "Rhythm",
    "Shadow",
    "Signal",
    "Voltage",
    "Mirage",
    "Current",
    "Drift",
    "Bloom",
]

ARTIST_A = [
    "DJ",
    "MC",
    "Luna",
    "Nova",
    "Kaya",
    "Rex",
    "Mara",
    "Otto",
    "Zara",
    "Finn",
    "Iris",
    "Milo",
    "Nia",
    "Theo",
    "Vera",
    "Yuri",
]

ARTIST_B = [
    "Waves",
    "Karma",
    "Vibes",
    "Static",
    "Orbit",
    "Prism",
    "Flux",
    "Ember",
    "Nomad",
    "Atlas",
    "Riven",
    "Solace",
    "Tundra",
    "Umbra",
    "Vandal",
    "Zephyr",
]

# The Camelot wheel, both raw notations and codes the app understands.
CAMELOT_KEYS = [
    "{}{}".format(number, letter) for number in range(1, 13) for letter in "AB"
]


def make_rows(start, count, rng):
    """[count] deterministic song tuples starting at synthetic index [start]."""
    rows = []
    for i in range(start, start + count):
        artist = "{} {}".format(rng.choice(ARTIST_A), rng.choice(ARTIST_B))
        title = "{} {}".format(rng.choice(WORDS_A), rng.choice(WORDS_B))
        album = "{} {} EP".format(rng.choice(WORDS_A), rng.choice(WORDS_B))
        genre = rng.choice(GENRES)
        year = rng.randint(1985, 2026)
        bpm = float(rng.randint(60, 180))
        musical_key = rng.choice(CAMELOT_KEYS)
        duration = round(rng.uniform(120.0, 480.0), 3)
        size = rng.randint(3_000_000, 20_000_000)
        rows.append(
            (
                "{} #{}".format(title, i),
                artist,
                album,
                genre,
                year,
                rng.randint(1, 12),
                bpm,
                musical_key,
                duration,
                320,
                "/music/synthetic/{}/{}.mp3".format(i // 4096, i),
                size,
                "syn:{}".format(i),
                "published",
                "library",
            )
        )
    return rows


COLUMNS = [
    "title",
    "artist",
    "album",
    "genre",
    "year",
    "track_number",
    "bpm",
    "musical_key",
    "duration_seconds",
    "bitrate_kbps",
    "file_path",
    "file_size_bytes",
    "dedup_key",
    "status",
    "source",
]


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dsn",
        default=os.environ.get("DATABASE_URL", ""),
        help="Postgres DSN (default: DATABASE_URL)",
    )
    parser.add_argument("--count", type=int, default=1_000_000)
    parser.add_argument("--batch", type=int, default=10_000)
    args = parser.parse_args()

    # Tortoise DSNs may carry pool params asyncpg.connect does not know.
    dsn = args.dsn.split("?")[0]
    if not dsn:
        raise SystemExit("No DSN: pass --dsn or set DATABASE_URL")

    connection = await asyncpg.connect(dsn)
    rng = random.Random(20260710)
    started = time.time()
    inserted = 0
    try:
        # Re-runnable: skip past whatever synthetic rows already exist.
        existing = await connection.fetchval(
            "SELECT COUNT(*) FROM songs WHERE dedup_key LIKE 'syn:%'"
        )
        # Deterministic rows: replay the RNG up to the resume point.
        if existing:
            make_rows(0, existing, rng)
        for start in range(existing, args.count, args.batch):
            batch = make_rows(start, min(args.batch, args.count - start), rng)
            await connection.copy_records_to_table(
                "songs", records=batch, columns=COLUMNS
            )
            inserted += len(batch)
            if inserted % 100_000 < args.batch and inserted:
                rate = inserted / max(time.time() - started, 0.001)
                print(
                    "seeded {} rows ({:.0f} rows/s)".format(existing + inserted, rate),
                    flush=True,
                )
        # Bulk COPY leaves the planner with stale statistics AND parks every
        # new GIN entry in the indexes' pending lists (linear-scanned on
        # every search until vacuum merges them): VACUUM ANALYZE does both —
        # without it, searches stay slow until autovacuum catches up.
        if inserted:
            print("vacuum-analyzing songs ...", flush=True)
            await connection.execute("VACUUM ANALYZE songs")
    finally:
        await connection.close()

    elapsed = max(time.time() - started, 0.001)
    total = existing + inserted
    print(
        "done: {} synthetic rows present ({} inserted at {:.0f} rows/s)".format(
            total, inserted, inserted / elapsed
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
