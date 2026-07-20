-- upgrade --
-- MOO-87: the ingestion analyzer. track_analysis holds everything derived
-- from the audio itself -- BPM, key, loudness, waveform, fingerprint and
-- quality -- and songs gains the detected read-model so list/filter queries
-- never join at millions-of-rows scale. Tag values always win over detected
-- ones (D5 precedence), hence the COALESCE expression indexes below.
-- NOTE: never end a comment line with a semicolon -- aerich splits this
-- file on ";\n" and a comment-only chunk crashes asyncpg 0.28

ALTER TABLE "songs" ADD "bpm_detected" DOUBLE PRECISION;
ALTER TABLE "songs" ADD "key_detected" VARCHAR(20);
ALTER TABLE "songs" ADD "waveform_ready" BOOL NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS "idx_songs_bpm_eff" ON "songs" (COALESCE("bpm", "bpm_detected"));
CREATE INDEX IF NOT EXISTS "idx_songs_key_eff" ON "songs" (LOWER(COALESCE("musical_key", "key_detected")));

CREATE TABLE IF NOT EXISTS "track_analysis" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "song_id" INT NOT NULL UNIQUE REFERENCES "songs" ("id") ON DELETE CASCADE,
    "checksum_sha256" VARCHAR(64),
    "analyzer_version" INT NOT NULL DEFAULT 1,
    "field_versions" JSONB NOT NULL DEFAULT '{}',
    "pass1_status" VARCHAR(10) NOT NULL DEFAULT 'pending',
    "pass2_status" VARCHAR(10) NOT NULL DEFAULT 'pending',
    "pass1_at" TIMESTAMPTZ,
    "pass2_at" TIMESTAMPTZ,
    "error" TEXT,
    "codec" VARCHAR(20),
    "container" VARCHAR(20),
    "sample_rate_hz" INT,
    "channels" SMALLINT,
    "bitrate_mode" VARCHAR(8),
    "encoder" VARCHAR(120),
    "art_present" BOOL NOT NULL DEFAULT FALSE,
    "art_format" VARCHAR(10),
    "art_width" INT,
    "art_height" INT,
    "art_bytes" INT,
    "tags_json" JSONB,
    "decode_ok" BOOL,
    "bpm_detected" DOUBLE PRECISION,
    "key_detected" VARCHAR(20),
    "key_confidence" DOUBLE PRECISION,
    "bpm_mismatch" BOOL,
    "key_mismatch" BOOL,
    "loudness_lufs" DOUBLE PRECISION,
    "loudness_range" DOUBLE PRECISION,
    "true_peak_dbtp" DOUBLE PRECISION,
    "cue_in_s" DOUBLE PRECISION,
    "cue_out_s" DOUBLE PRECISION,
    "waveform_peaks_count" INT,
    "fingerprint" TEXT,
    "fingerprint_algo" VARCHAR(30),
    "fingerprint_sha256" VARCHAR(64),
    "pcm_sha256" VARCHAR(64),
    "spectral_cutoff_hz" INT,
    "quality_flags" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "modified_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Index plan (MOO-77 D6): the FK is UNIQUE-indexed already; every filtered
-- column gets one -- pass2_status feeds the backfill/stats scans, the three
-- hashes are MOO-90's dedup lookup keys, checksum is the idempotency key
CREATE INDEX IF NOT EXISTS "idx_track_analysis_pass2" ON "track_analysis" ("pass2_status", "id");
CREATE INDEX IF NOT EXISTS "idx_track_analysis_fp_sha" ON "track_analysis" ("fingerprint_sha256");
CREATE INDEX IF NOT EXISTS "idx_track_analysis_pcm_sha" ON "track_analysis" ("pcm_sha256");
CREATE INDEX IF NOT EXISTS "idx_track_analysis_checksum" ON "track_analysis" ("checksum_sha256");
