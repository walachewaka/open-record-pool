-- upgrade --
-- MOO-81: song request system. song_requests is one row per member request
-- (free-text artist/title or a provider URL), moderated (or auto-approved)
-- then fulfilled through the MOO-78 download engine. download_id is a soft
-- reference to download_requests.id (no DB-level FK by design -- see D3.4)
-- NOTE: never end a comment line with a semicolon -- aerich splits this file
-- on ";\n" and a comment-only chunk crashes asyncpg 0.28

CREATE TABLE IF NOT EXISTS "song_requests" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "user_id" INT NOT NULL REFERENCES "users" ("id") ON DELETE CASCADE,
    "kind" VARCHAR(10) NOT NULL,
    "artist" VARCHAR(255),
    "title" VARCHAR(255),
    "mix_name" VARCHAR(120),
    "source_url" VARCHAR(2048),
    "provider" VARCHAR(20),
    "notes" VARCHAR(500),
    "normalized_key" VARCHAR(2048),
    "status" VARCHAR(20) NOT NULL DEFAULT 'pending',
    "reason" VARCHAR(500),
    "duplicate_of_id" INT REFERENCES "songs" ("id") ON DELETE SET NULL,
    "possible_duplicate_of_id" INT REFERENCES "songs" ("id") ON DELETE SET NULL,
    "fulfilled_song_id" INT REFERENCES "songs" ("id") ON DELETE SET NULL,
    "download_id" INT,
    "decided_by_id" INT REFERENCES "users" ("id") ON DELETE SET NULL,
    "decided_at" TIMESTAMPTZ,
    "resolved_seen" BOOL NOT NULL DEFAULT FALSE,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "modified_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Index plan (D6): every FK plus every filtered/sorted column. (status, id)
-- and (user_id, id) back the keyset list queries; normalized_key backs the
-- open-duplicate guard; download_id backs the read-repair sync sweep
CREATE INDEX IF NOT EXISTS "idx_songreq_status_id" ON "song_requests" ("status", "id");
CREATE INDEX IF NOT EXISTS "idx_songreq_user_id" ON "song_requests" ("user_id", "id");
CREATE INDEX IF NOT EXISTS "idx_songreq_user_status" ON "song_requests" ("user_id", "status");
CREATE INDEX IF NOT EXISTS "idx_songreq_user_created" ON "song_requests" ("user_id", "created_at");
CREATE INDEX IF NOT EXISTS "idx_songreq_normkey" ON "song_requests" ("normalized_key");
CREATE INDEX IF NOT EXISTS "idx_songreq_download" ON "song_requests" ("download_id");
CREATE INDEX IF NOT EXISTS "idx_songreq_dup_of" ON "song_requests" ("duplicate_of_id");
CREATE INDEX IF NOT EXISTS "idx_songreq_possdup_of" ON "song_requests" ("possible_duplicate_of_id");
CREATE INDEX IF NOT EXISTS "idx_songreq_fulfilled" ON "song_requests" ("fulfilled_song_id");
CREATE INDEX IF NOT EXISTS "idx_songreq_decided_by" ON "song_requests" ("decided_by_id");

-- downgrade --
DROP TABLE IF EXISTS "song_requests";
