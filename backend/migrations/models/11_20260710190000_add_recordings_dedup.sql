-- upgrade --
-- MOO-90: recording-level duplicate detection. recordings is the dedup unit
-- (one row per specific mix/edit -- extended vs radio are DIFFERENT rows),
-- each songs row is one version of a recording, duplicate_candidates records
-- every detected pair, recording_links marks related cuts, and
-- fingerprint_ngrams is the local indexed fingerprint-similarity search.
-- NOTE: never end a comment line with a semicolon -- aerich splits this
-- file on ";\n" and a comment-only chunk crashes asyncpg 0.28

CREATE TABLE IF NOT EXISTS "recordings" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "artist_norm" VARCHAR(255) NOT NULL,
    "title_norm" VARCHAR(255) NOT NULL,
    "mix_norm" VARCHAR(100) NOT NULL DEFAULT 'original',
    "duration_seconds" DOUBLE PRECISION,
    "canonical_song_id" INT REFERENCES "songs" ("id") ON DELETE SET NULL,
    "isrc" VARCHAR(15),
    "musicbrainz_id" VARCHAR(36),
    "beatport_id" VARCHAR(32),
    "spotify_id" VARCHAR(32),
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "modified_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Index plan (MOO-77 D6): identity triple for metadata lookups, one index
-- per external-ID lookup key, and the canonical FK
CREATE INDEX IF NOT EXISTS "idx_recordings_identity" ON "recordings" ("artist_norm", "title_norm", "mix_norm");
CREATE UNIQUE INDEX IF NOT EXISTS "idx_recordings_isrc" ON "recordings" ("isrc") WHERE "isrc" IS NOT NULL;
CREATE INDEX IF NOT EXISTS "idx_recordings_mbid" ON "recordings" ("musicbrainz_id");
CREATE INDEX IF NOT EXISTS "idx_recordings_beatport" ON "recordings" ("beatport_id");
CREATE INDEX IF NOT EXISTS "idx_recordings_spotify" ON "recordings" ("spotify_id");
CREATE INDEX IF NOT EXISTS "idx_recordings_canonical" ON "recordings" ("canonical_song_id");

ALTER TABLE "songs" ADD "recording_id" INT REFERENCES "recordings" ("id") ON DELETE SET NULL;
ALTER TABLE "songs" ADD "version_status" VARCHAR(20) NOT NULL DEFAULT 'canonical';
ALTER TABLE "songs" ADD "quality_breakdown" JSONB;
ALTER TABLE "songs" ADD "artist_norm" VARCHAR(255);
ALTER TABLE "songs" ADD "title_norm" VARCHAR(255);

-- version_status composes with the member published-only filter; the norm
-- pair and duration back the D4 candidate prefilter
CREATE INDEX IF NOT EXISTS "idx_songs_recording" ON "songs" ("recording_id");
CREATE INDEX IF NOT EXISTS "idx_songs_version_status" ON "songs" ("status", "version_status", "id");
CREATE INDEX IF NOT EXISTS "idx_songs_artist_norm" ON "songs" ("artist_norm");
CREATE INDEX IF NOT EXISTS "idx_songs_title_norm" ON "songs" ("title_norm");
CREATE INDEX IF NOT EXISTS "idx_songs_duration" ON "songs" ("duration_seconds");

CREATE TABLE IF NOT EXISTS "recording_links" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "recording_a_id" INT NOT NULL REFERENCES "recordings" ("id") ON DELETE CASCADE,
    "recording_b_id" INT NOT NULL REFERENCES "recordings" ("id") ON DELETE CASCADE,
    "kind" VARCHAR(20) NOT NULL DEFAULT 'related_cut',
    "similarity" DOUBLE PRECISION,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "uid_recording_links" UNIQUE ("recording_a_id", "recording_b_id")
);
CREATE INDEX IF NOT EXISTS "idx_recording_links_b" ON "recording_links" ("recording_b_id");

CREATE TABLE IF NOT EXISTS "duplicate_candidates" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "song_a_id" INT NOT NULL REFERENCES "songs" ("id") ON DELETE CASCADE,
    "song_b_id" INT NOT NULL REFERENCES "songs" ("id") ON DELETE CASCADE,
    "recording_id" INT REFERENCES "recordings" ("id") ON DELETE SET NULL,
    "layer" VARCHAR(20) NOT NULL,
    "similarity" DOUBLE PRECISION,
    "confidence" DOUBLE PRECISION NOT NULL,
    "duration_delta" DOUBLE PRECISION,
    "status" VARCHAR(20) NOT NULL DEFAULT 'pending',
    "suggested_winner_id" INT REFERENCES "songs" ("id") ON DELETE SET NULL,
    "resolution" JSONB,
    "resolved_by_id" INT REFERENCES "users" ("id") ON DELETE SET NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "resolved_at" TIMESTAMPTZ,
    CONSTRAINT "uid_duplicate_pair" UNIQUE ("song_a_id", "song_b_id")
);
CREATE INDEX IF NOT EXISTS "idx_dup_status_id" ON "duplicate_candidates" ("status", "id");
CREATE INDEX IF NOT EXISTS "idx_dup_song_b" ON "duplicate_candidates" ("song_b_id");
CREATE INDEX IF NOT EXISTS "idx_dup_recording" ON "duplicate_candidates" ("recording_id");
CREATE INDEX IF NOT EXISTS "idx_dup_winner" ON "duplicate_candidates" ("suggested_winner_id");
CREATE INDEX IF NOT EXISTS "idx_dup_resolved_by" ON "duplicate_candidates" ("resolved_by_id");

CREATE TABLE IF NOT EXISTS "fingerprint_ngrams" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "song_id" INT NOT NULL REFERENCES "songs" ("id") ON DELETE CASCADE,
    "ngram" BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS "idx_fp_ngrams_ngram" ON "fingerprint_ngrams" ("ngram");
CREATE INDEX IF NOT EXISTS "idx_fp_ngrams_song" ON "fingerprint_ngrams" ("song_id");
