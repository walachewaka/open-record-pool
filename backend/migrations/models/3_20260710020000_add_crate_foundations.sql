-- upgrade --
CREATE TABLE IF NOT EXISTS "crates" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "name" VARCHAR(100) NOT NULL,
    "color" VARCHAR(16),
    "public" BOOL NOT NULL DEFAULT FALSE,
    "share_token" VARCHAR(64) NOT NULL UNIQUE,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "modified_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "owner_id" INT NOT NULL REFERENCES "users" ("id") ON DELETE CASCADE
);
COMMENT ON TABLE "crates" IS 'A crate is a user-owned playlist (MOO-65).';
CREATE INDEX IF NOT EXISTS "idx_crates_owner" ON "crates" ("owner_id");
CREATE TABLE IF NOT EXISTS "crate_tracks" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "position" INT NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "crate_id" INT NOT NULL REFERENCES "crates" ("id") ON DELETE CASCADE,
    "song_id" INT NOT NULL REFERENCES "songs" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_crate_track" UNIQUE ("crate_id", "song_id")
);
COMMENT ON TABLE "crate_tracks" IS 'Ordered song membership of a crate (MOO-65).';
CREATE INDEX IF NOT EXISTS "idx_crate_tracks_crate" ON "crate_tracks" ("crate_id");
CREATE INDEX IF NOT EXISTS "idx_crate_tracks_song" ON "crate_tracks" ("song_id");
CREATE TABLE IF NOT EXISTS "favorites" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "song_id" INT NOT NULL REFERENCES "songs" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "users" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_favorite_user_song" UNIQUE ("user_id", "song_id")
);
COMMENT ON TABLE "favorites" IS 'Per-user song favorites (MOO-65).';
CREATE INDEX IF NOT EXISTS "idx_favorites_user" ON "favorites" ("user_id");
CREATE INDEX IF NOT EXISTS "idx_favorites_song" ON "favorites" ("song_id");
CREATE TABLE IF NOT EXISTS "play_events" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "played_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "song_id" INT NOT NULL REFERENCES "songs" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "users" ("id") ON DELETE CASCADE
);
COMMENT ON TABLE "play_events" IS 'One row per playback start of a song by a user (MOO-65).';
CREATE INDEX IF NOT EXISTS "idx_play_events_song" ON "play_events" ("song_id");
CREATE INDEX IF NOT EXISTS "idx_play_events_user" ON "play_events" ("user_id");
CREATE TABLE IF NOT EXISTS "downloads" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "format" VARCHAR(10) NOT NULL DEFAULT 'mp3',
    "counted_against_quota" BOOL NOT NULL DEFAULT TRUE,
    "downloaded_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "song_id" INT NOT NULL REFERENCES "songs" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "users" ("id") ON DELETE CASCADE
);
COMMENT ON TABLE "downloads" IS 'One row per download of a song by a user (MOO-65).';
CREATE INDEX IF NOT EXISTS "idx_downloads_song" ON "downloads" ("song_id");
CREATE INDEX IF NOT EXISTS "idx_downloads_user_time" ON "downloads" ("user_id", "downloaded_at");
