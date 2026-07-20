-- upgrade --
-- MOO-85: Beatport API v4 metadata enrichment. Adds songs.beatport_track_id
-- (denormalized for fast joins) + songs.field_locks (which fields are
-- DB-owned by a manual edit or an applied enrichment -- a /music rescan
-- skips locked fields, fixing the MOO-71/72 quirk where DB edits were
-- silently reverted by the next scan), the song_enrichment table (one row
-- per song+provider: normalized payload, scored candidates, match state,
-- applied fields, pre-apply snapshot), and beatport_cache (a read-through
-- response cache, Postgres not Redis -- MOO-77 declared Redis wipeable
-- transport and cached responses must survive a redis restart at library
-- scale). NOTE: never end a comment line with a semicolon -- aerich splits
-- this file on ";\n" and a comment-only chunk crashes asyncpg 0.28

ALTER TABLE "songs" ADD "beatport_track_id" BIGINT;
ALTER TABLE "songs" ADD "field_locks" JSONB;
CREATE INDEX IF NOT EXISTS "idx_songs_beatport_track" ON "songs" ("beatport_track_id");

CREATE TABLE IF NOT EXISTS "song_enrichment" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "provider" VARCHAR(20) NOT NULL DEFAULT 'beatport',
    "status" VARCHAR(20) NOT NULL DEFAULT 'pending',
    "match_method" VARCHAR(10),
    "confidence" DOUBLE PRECISION,
    "beatport_track_id" BIGINT,
    "beatport_release_id" BIGINT,
    "beatport_artist_ids" JSONB,
    "payload" JSONB,
    "candidates" JSONB,
    "fields_applied" JSONB,
    "tag_snapshot" JSONB,
    "error" TEXT,
    "matched_at" TIMESTAMPTZ,
    "applied_at" TIMESTAMPTZ,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "modified_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "song_id" INT NOT NULL REFERENCES "songs" ("id") ON DELETE CASCADE,
    "reviewed_by_id" INT REFERENCES "users" ("id") ON DELETE SET NULL,
    CONSTRAINT "uid_song_enrichment_song_provider" UNIQUE ("song_id", "provider")
);
COMMENT ON TABLE "song_enrichment" IS 'Per song+provider metadata enrichment (MOO-85).';

-- Index plan (MOO-77 D6): one per FK, plus the (status, id) keyset pair the
-- review queue paginates on and the beatport_track_id lookup for re-sync
CREATE INDEX IF NOT EXISTS "idx_song_enrichment_status_id" ON "song_enrichment" ("status", "id");
CREATE INDEX IF NOT EXISTS "idx_song_enrichment_song" ON "song_enrichment" ("song_id");
CREATE INDEX IF NOT EXISTS "idx_song_enrichment_bp_track" ON "song_enrichment" ("beatport_track_id");
CREATE INDEX IF NOT EXISTS "idx_song_enrichment_reviewed_by" ON "song_enrichment" ("reviewed_by_id");

CREATE TABLE IF NOT EXISTS "beatport_cache" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "cache_key" VARCHAR(40) NOT NULL UNIQUE,
    "url" VARCHAR(1024) NOT NULL,
    "response" JSONB NOT NULL,
    "fetched_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "expires_at" TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS "idx_beatport_cache_expires" ON "beatport_cache" ("expires_at");
