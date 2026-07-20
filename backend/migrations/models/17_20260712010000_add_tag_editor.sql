-- upgrade --
-- MOO-82: full ID3 metadata editor + album art management. Adds the managed
-- album-art columns (the normalized display copy lives in /library/art -- the
-- /music volume is read-only and is never written), the ISRC tag, and the
-- edit-history / member-proposal tables.
-- NOTE: never end a comment line with a semicolon -- aerich splits
-- this file on ";\n" and a comment-only chunk crashes asyncpg 0.28

ALTER TABLE "songs" ADD "artwork_path" VARCHAR(1024);
ALTER TABLE "songs" ADD "artwork_source" VARCHAR(20);
ALTER TABLE "songs" ADD "artwork_width" INT;
ALTER TABLE "songs" ADD "artwork_height" INT;
ALTER TABLE "songs" ADD "isrc" VARCHAR(15);
CREATE INDEX IF NOT EXISTS "idx_songs_isrc" ON "songs" ("isrc");

CREATE TABLE IF NOT EXISTS "tag_revisions" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "editor_username" VARCHAR(20),
    "source" VARCHAR(20) NOT NULL DEFAULT 'user',
    "changes" JSONB NOT NULL,
    "batch_id" VARCHAR(32),
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "song_id" INT NOT NULL REFERENCES "songs" ("id") ON DELETE CASCADE,
    "editor_id" INT REFERENCES "users" ("id") ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS "idx_tag_revisions_song" ON "tag_revisions" ("song_id", "id");
CREATE INDEX IF NOT EXISTS "idx_tag_revisions_editor" ON "tag_revisions" ("editor_id");
CREATE INDEX IF NOT EXISTS "idx_tag_revisions_batch" ON "tag_revisions" ("batch_id");
COMMENT ON TABLE "tag_revisions" IS 'Append-only metadata edit history (MOO-82).';

CREATE TABLE IF NOT EXISTS "tag_proposals" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "changes" JSONB NOT NULL,
    "note" VARCHAR(500),
    "status" VARCHAR(20) NOT NULL DEFAULT 'pending',
    "reviewed_at" TIMESTAMPTZ,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "song_id" INT NOT NULL REFERENCES "songs" ("id") ON DELETE CASCADE,
    "proposer_id" INT REFERENCES "users" ("id") ON DELETE SET NULL,
    "reviewed_by_id" INT REFERENCES "users" ("id") ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS "idx_tag_proposals_status" ON "tag_proposals" ("status", "id");
CREATE INDEX IF NOT EXISTS "idx_tag_proposals_song" ON "tag_proposals" ("song_id");
CREATE INDEX IF NOT EXISTS "idx_tag_proposals_proposer" ON "tag_proposals" ("proposer_id", "id");
CREATE INDEX IF NOT EXISTS "idx_tag_proposals_reviewer" ON "tag_proposals" ("reviewed_by_id");
COMMENT ON TABLE "tag_proposals" IS 'Member-proposed metadata edits awaiting approval (MOO-82).';
