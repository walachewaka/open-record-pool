-- upgrade --
-- Scale baseline indexes (MOO-77): every filtered/sorted column on the hot
-- member paths gets an index, and pg_trgm GIN indexes serve the interim
-- free-text search (icontains/ILIKE) until Elasticsearch lands (MOO-79).
-- pg_trgm is a trusted extension on postgres:14, so the compose DB owner can
-- create it without superuser. Hand-written SQL on purpose: expression and
-- GIN indexes cannot be expressed in Tortoise Meta, and aerich 0.6 diffs
-- models against its snapshot, so it neither recreates nor drops these.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- songs: browse/filter/sort paths (status is always ANDed in member queries)
CREATE INDEX IF NOT EXISTS idx_songs_status_artist_id ON songs (status, artist, id);
CREATE INDEX IF NOT EXISTS idx_songs_status_created_id ON songs (status, created_at, id);
CREATE INDEX IF NOT EXISTS idx_songs_genre ON songs (genre);
CREATE INDEX IF NOT EXISTS idx_songs_genre_lower ON songs (LOWER(genre));
CREATE INDEX IF NOT EXISTS idx_songs_key_lower ON songs (LOWER(musical_key));
CREATE INDEX IF NOT EXISTS idx_songs_bpm ON songs (bpm);

-- interim free-text search until MOO-79 (pg_trgm serves icontains).
-- Tortoise 0.19 compiles icontains to UPPER(CAST(col AS VARCHAR)) LIKE
-- UPPER('%q%'), so the GIN indexes must be on that exact expression — a
-- plain (col gin_trgm_ops) index is never matched. The /songs?q= filter ORs
-- FIVE icontains columns and every one needs an index, because a single
-- unindexable OR branch forces a full seq scan instead of a bitmap OR.
CREATE INDEX IF NOT EXISTS idx_songs_title_trgm ON songs USING GIN (UPPER(CAST(title AS VARCHAR)) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_songs_artist_trgm ON songs USING GIN (UPPER(CAST(artist AS VARCHAR)) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_songs_album_trgm ON songs USING GIN (UPPER(CAST(album AS VARCHAR)) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_songs_genre_trgm ON songs USING GIN (UPPER(CAST(genre AS VARCHAR)) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_songs_label_trgm ON songs USING GIN (UPPER(CAST(label AS VARCHAR)) gin_trgm_ops);

-- FK/hot-path indexes Postgres does not create automatically
CREATE INDEX IF NOT EXISTS idx_crate_tracks_crate_pos ON crate_tracks (crate_id, position);
CREATE INDEX IF NOT EXISTS idx_crate_tracks_song ON crate_tracks (song_id);
CREATE INDEX IF NOT EXISTS idx_favorites_user_created ON favorites (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_favorites_song ON favorites (song_id);
CREATE INDEX IF NOT EXISTS idx_play_events_song ON play_events (song_id);
CREATE INDEX IF NOT EXISTS idx_play_events_user_played ON play_events (user_id, played_at DESC);
CREATE INDEX IF NOT EXISTS idx_downloads_song ON downloads (song_id);
CREATE INDEX IF NOT EXISTS idx_downloads_user_downloaded ON downloads (user_id, downloaded_at DESC);
CREATE INDEX IF NOT EXISTS idx_downloads_user_song ON downloads (user_id, song_id);
