-- upgrade --
-- MOO-78: music download engine. songs.source_url captures the provider URL a
-- fetched track came from; download_requests is one row per acquisition
-- attempt-series (queued -> fetching -> postprocessing -> imported/
-- duplicate_skipped/failed/cancelled), linking user/provider/job/song and
-- carrying the extracted source metadata.
-- NOTE: never end a comment line with a semicolon -- aerich splits this file
-- on ";\n" and a comment-only chunk crashes asyncpg 0.28

ALTER TABLE "songs" ADD COLUMN "source_url" VARCHAR(2048);

CREATE TABLE IF NOT EXISTS "download_requests" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "provider" VARCHAR(20) NOT NULL,
    "url" VARCHAR(2048) NOT NULL,
    "external_id" VARCHAR(128),
    "status" VARCHAR(20) NOT NULL DEFAULT 'queued',
    "origin" VARCHAR(20) NOT NULL DEFAULT 'member',
    "origin_ref" VARCHAR(64),
    "priority" VARCHAR(10) NOT NULL DEFAULT 'normal',
    "requested_by_id" INT REFERENCES "users" ("id") ON DELETE SET NULL,
    "job_id" BIGINT REFERENCES "jobs" ("id") ON DELETE SET NULL,
    "song_id" INT REFERENCES "songs" ("id") ON DELETE SET NULL,
    "source_metadata" JSONB,
    "progress" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "attempts" INT NOT NULL DEFAULT 0,
    "error" TEXT,
    "error_kind" VARCHAR(30),
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "started_at" TIMESTAMPTZ,
    "finished_at" TIMESTAMPTZ
);

-- Index plan (MOO-77 D6): every FK plus every filtered/sorted column. The
-- (status, id) and (requested_by_id, id) pairs back the keyset list queries
-- and (provider, external_id) backs the duplicate-active lookup
CREATE INDEX IF NOT EXISTS "idx_dlreq_status_id" ON "download_requests" ("status", "id");
CREATE INDEX IF NOT EXISTS "idx_dlreq_user_id" ON "download_requests" ("requested_by_id", "id");
CREATE INDEX IF NOT EXISTS "idx_dlreq_provider_status" ON "download_requests" ("provider", "status");
CREATE INDEX IF NOT EXISTS "idx_dlreq_provider_ext" ON "download_requests" ("provider", "external_id");
CREATE INDEX IF NOT EXISTS "idx_dlreq_song" ON "download_requests" ("song_id");
CREATE INDEX IF NOT EXISTS "idx_dlreq_job" ON "download_requests" ("job_id");
CREATE INDEX IF NOT EXISTS "idx_dlreq_user_created" ON "download_requests" ("requested_by_id", "created_at");

-- downgrade --
DROP TABLE IF EXISTS "download_requests";
ALTER TABLE "songs" DROP COLUMN IF EXISTS "source_url";
