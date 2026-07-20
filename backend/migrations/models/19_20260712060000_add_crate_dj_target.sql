-- upgrade --
-- MOO-86: DJ crate/playlist export (Serato, Traktor, rekordbox). The crate
-- carries the target DJ software picked at creation; exports themselves reuse
-- the MOO-77 jobs table (kind="export_crate") and keep their artifacts on disk
-- under /library/export/<job_id>, so no new table is needed here.
-- No index: dj_target is never filtered or sorted on, only read off a crate
-- row already fetched by primary key (explicit MOO-77 D6 exemption).
-- NOTE: never end a comment line with a semicolon -- aerich splits
-- this file on ";\n" and a comment-only chunk crashes asyncpg 0.28

ALTER TABLE "crates" ADD COLUMN IF NOT EXISTS "dj_target" VARCHAR(20);

-- downgrade --
ALTER TABLE "crates" DROP COLUMN IF EXISTS "dj_target";
