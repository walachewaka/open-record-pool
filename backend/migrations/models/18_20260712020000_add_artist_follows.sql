-- upgrade --
-- MOO-80: follow artists, release tracking & calendar (Sonarr/Radarr concept).
-- Adds artists (materialized from the library), per-user follows, the shared
-- releases table (source-agnostic, deduped by (source, external_id)), and
-- the per-user feed "seen" marker.
-- NOTE: never end a comment line with a semicolon -- aerich splits
-- this file on ";\n" and a comment-only chunk crashes asyncpg 0.28

CREATE TABLE IF NOT EXISTS "artists" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "name" VARCHAR(255) NOT NULL,
    "name_norm" VARCHAR(255) NOT NULL UNIQUE,
    "track_count" INT NOT NULL DEFAULT 0,
    "beatport_artist_id" VARCHAR(64) UNIQUE,
    "musicbrainz_id" VARCHAR(36),
    "image_url" VARCHAR(1024),
    "last_polled_at" TIMESTAMPTZ,
    "last_release_seen_at" TIMESTAMPTZ,
    "resolve_attempted_at" TIMESTAMPTZ,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "modified_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS "idx_artists_name_id" ON "artists" ("name", "id");
CREATE INDEX IF NOT EXISTS "idx_artists_last_polled" ON "artists" ("last_polled_at");
COMMENT ON TABLE "artists" IS 'Artists materialized from the library, one row per distinct name (MOO-80).';

CREATE TABLE IF NOT EXISTS "artist_follows" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "settings" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "user_id" INT NOT NULL REFERENCES "users" ("id") ON DELETE CASCADE,
    "artist_id" INT NOT NULL REFERENCES "artists" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_artist_follows_user_artist" UNIQUE ("user_id", "artist_id")
);
CREATE INDEX IF NOT EXISTS "idx_artist_follows_artist" ON "artist_follows" ("artist_id");
COMMENT ON TABLE "artist_follows" IS 'A member follows an artist, deduped onto the shared artists row (MOO-80).';

CREATE TABLE IF NOT EXISTS "releases" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "source" VARCHAR(20) NOT NULL DEFAULT 'beatport',
    "external_id" VARCHAR(64) NOT NULL,
    "title" VARCHAR(255) NOT NULL,
    "release_date" DATE NOT NULL,
    "label" VARCHAR(255),
    "artwork_url" VARCHAR(1024),
    "source_url" VARCHAR(1024),
    "track_count" INT NOT NULL DEFAULT 0,
    "tracks" JSONB NOT NULL DEFAULT '[]',
    "status" VARCHAR(20) NOT NULL DEFAULT 'missing',
    "matched_song_ids" JSONB NOT NULL DEFAULT '[]',
    "matched_count" INT NOT NULL DEFAULT 0,
    "grab_request_ids" JSONB NOT NULL DEFAULT '[]',
    "ignored_at" TIMESTAMPTZ,
    "first_seen_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "modified_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "artist_id" INT NOT NULL REFERENCES "artists" ("id") ON DELETE CASCADE,
    "ignored_by_id" INT REFERENCES "users" ("id") ON DELETE SET NULL,
    CONSTRAINT "uid_releases_source_external" UNIQUE ("source", "external_id")
);
CREATE INDEX IF NOT EXISTS "idx_releases_artist_date" ON "releases" ("artist_id", "release_date");
CREATE INDEX IF NOT EXISTS "idx_releases_date_id" ON "releases" ("release_date", "id");
CREATE INDEX IF NOT EXISTS "idx_releases_status" ON "releases" ("status");
CREATE INDEX IF NOT EXISTS "idx_releases_first_seen" ON "releases" ("first_seen_at", "id");
COMMENT ON TABLE "releases" IS 'Releases surfaced by a release source for a followed artist, shared/global (MOO-80).';

CREATE TABLE IF NOT EXISTS "follow_feed_state" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "seen_at" TIMESTAMPTZ NOT NULL,
    "user_id" INT NOT NULL UNIQUE REFERENCES "users" ("id") ON DELETE CASCADE
);
COMMENT ON TABLE "follow_feed_state" IS 'Per-user last-seen marker for the release feed badge (MOO-80).';
