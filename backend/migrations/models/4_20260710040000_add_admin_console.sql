-- upgrade --
-- Admin console foundations (MOO-71): user roles/plan/status/email,
-- song moderation status + upload provenance, the role permission matrix,
-- and the instance settings key/value store.

ALTER TABLE "users" ADD COLUMN "email" VARCHAR(255);
ALTER TABLE "users" ADD COLUMN "role" VARCHAR(20) NOT NULL DEFAULT 'member';
ALTER TABLE "users" ADD COLUMN "plan" VARCHAR(20) NOT NULL DEFAULT 'free';
ALTER TABLE "users" ADD COLUMN "status" VARCHAR(20) NOT NULL DEFAULT 'active';
CREATE INDEX IF NOT EXISTS "idx_users_role" ON "users" ("role");
CREATE INDEX IF NOT EXISTS "idx_users_status" ON "users" ("status");

-- Existing library rows are already published; new uploads may be pending.
ALTER TABLE "songs" ADD COLUMN "status" VARCHAR(20) NOT NULL DEFAULT 'published';
ALTER TABLE "songs" ADD COLUMN "source" VARCHAR(20) NOT NULL DEFAULT 'library';
ALTER TABLE "songs" ADD COLUMN "uploaded_by_id" INT REFERENCES "users" ("id") ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS "idx_songs_status" ON "songs" ("status");
CREATE INDEX IF NOT EXISTS "idx_songs_source" ON "songs" ("source");
CREATE INDEX IF NOT EXISTS "idx_songs_uploaded_by" ON "songs" ("uploaded_by_id");

CREATE TABLE IF NOT EXISTS "role_permissions" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "role" VARCHAR(20) NOT NULL UNIQUE,
    "permissions" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "modified_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE "role_permissions" IS 'The persisted permission matrix, one row per non-owner role (MOO-71).';

CREATE TABLE IF NOT EXISTS "instance_settings" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "key" VARCHAR(128) NOT NULL UNIQUE,
    "value" TEXT,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "modified_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE "instance_settings" IS 'Persisted instance settings as a flat JSON key/value store (MOO-71).';
