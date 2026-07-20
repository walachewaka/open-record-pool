-- upgrade --
-- MOO-79: extended ID3 columns on songs (full-fidelity metadata for the
-- Elasticsearch index) and the transactional search outbox that keeps ES in
-- sync with PostgreSQL. ES itself is never migrated by aerich: versioned
-- indices behind the orp-tracks alias + the reindex job are the ES migration
-- story. NOTE: never end a comment line with a semicolon -- aerich splits
-- this file on ";\n" and a comment-only chunk crashes asyncpg 0.28

ALTER TABLE "songs" ADD "album_artist" VARCHAR(255);
ALTER TABLE "songs" ADD "composer" VARCHAR(255);
ALTER TABLE "songs" ADD "comment" TEXT;
ALTER TABLE "songs" ADD "disc_number" INT;
ALTER TABLE "songs" ADD "codec" VARCHAR(20);
ALTER TABLE "songs" ADD "has_artwork" BOOL NOT NULL DEFAULT FALSE;
ALTER TABLE "songs" ADD "txxx_frames" JSONB;

CREATE TABLE IF NOT EXISTS "search_outbox" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "song_id" INT NOT NULL,
    "op" VARCHAR(10) NOT NULL,
    "attempts" INT NOT NULL DEFAULT 0,
    "last_error" TEXT,
    "enqueued_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "processed_at" TIMESTAMPTZ
);
COMMENT ON TABLE "search_outbox" IS 'Transactional outbox for the Elasticsearch sync (MOO-79).';

-- Index plan (MOO-77 rule): the drain claims WHERE processed_at IS NULL
-- ORDER BY id, so a partial index keeps the hot set tiny even when millions
-- of processed rows accumulate
CREATE INDEX IF NOT EXISTS "idx_search_outbox_pending"
    ON "search_outbox" ("id") WHERE "processed_at" IS NULL;
