-- upgrade --
-- MOO-84: public & private playlists. Crates gain a description and an
-- optional content-addressed cover; visibility is enforced at query level
-- and indexed (owner_id, public) as required by the spec. Existing
-- crate_tracks positions are re-spread to gap-based ordering (steps of
-- 1000) so future single-track moves rarely need a full rebalance.
-- NOTE: never end a comment line with a semicolon -- aerich splits this file
-- on ";\n" and a comment-only chunk crashes asyncpg 0.28

ALTER TABLE "crates" ADD COLUMN "description" TEXT;
ALTER TABLE "crates" ADD COLUMN "cover_path" VARCHAR(1024);

CREATE INDEX IF NOT EXISTS "idx_crates_owner_public" ON "crates" ("owner_id", "public");
CREATE INDEX IF NOT EXISTS "idx_crates_public_id" ON "crates" ("public", "id");
CREATE INDEX IF NOT EXISTS "idx_crates_name_trgm" ON "crates" USING GIN ("name" gin_trgm_ops);
CREATE INDEX IF NOT EXISTS "idx_crates_desc_trgm" ON "crates" USING GIN ("description" gin_trgm_ops);

UPDATE "crate_tracks" SET "position" = "position" * 1000;

-- downgrade --
ALTER TABLE "crates" DROP COLUMN IF EXISTS "description";
ALTER TABLE "crates" DROP COLUMN IF EXISTS "cover_path";
DROP INDEX IF EXISTS "idx_crates_owner_public";
DROP INDEX IF EXISTS "idx_crates_public_id";
DROP INDEX IF EXISTS "idx_crates_name_trgm";
DROP INDEX IF EXISTS "idx_crates_desc_trgm";
