-- upgrade --
-- MOO-77: content-addressed storage fields on songs, and the jobs table that
-- backs the async worker tier (Postgres is the source of truth for job
-- state, Redis/arq is transport only). NOTE: never end a comment line with
-- a semicolon -- aerich splits this file on ";\n", and a comment-only chunk
-- crashes asyncpg 0.28 with an AttributeError.

ALTER TABLE "songs" ADD COLUMN "checksum_sha256" VARCHAR(64);
ALTER TABLE "songs" ADD COLUMN "file_mtime" DOUBLE PRECISION;
CREATE INDEX IF NOT EXISTS idx_songs_sha256 ON songs (checksum_sha256);

CREATE TABLE IF NOT EXISTS "jobs" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "kind" VARCHAR(50) NOT NULL,
    "status" VARCHAR(20) NOT NULL DEFAULT 'queued',
    "queue" VARCHAR(20) NOT NULL DEFAULT 'orp:default',
    "payload" JSONB NOT NULL,
    "result" JSONB,
    "error" TEXT,
    "progress" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "arq_job_id" VARCHAR(64),
    "created_by_id" INT REFERENCES "users" ("id") ON DELETE SET NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "started_at" TIMESTAMPTZ,
    "finished_at" TIMESTAMPTZ
);
COMMENT ON TABLE "jobs" IS 'One row per background job (MOO-77).';
CREATE INDEX IF NOT EXISTS idx_jobs_status_id ON jobs (status, id);
CREATE INDEX IF NOT EXISTS idx_jobs_kind_id ON jobs (kind, id);
CREATE INDEX IF NOT EXISTS idx_jobs_created_by ON jobs (created_by_id, id);
