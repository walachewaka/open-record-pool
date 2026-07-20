-- upgrade --
CREATE TABLE IF NOT EXISTS "songs" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "title" VARCHAR(255),
    "artist" VARCHAR(255),
    "album" VARCHAR(255),
    "genre" VARCHAR(100),
    "year" INT,
    "track_number" INT,
    "bpm" DOUBLE PRECISION,
    "musical_key" VARCHAR(20),
    "duration_seconds" DOUBLE PRECISION,
    "bitrate_kbps" INT,
    "file_path" VARCHAR(1024) NOT NULL UNIQUE,
    "file_size_bytes" BIGINT,
    "checksum_md5" VARCHAR(32),
    "dedup_key" VARCHAR(64) NOT NULL UNIQUE,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "modified_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE "songs" IS 'One row per unique song found on the music volume (#5, #9).';
