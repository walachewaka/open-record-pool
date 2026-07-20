-- upgrade --
-- Search by label (MOO-94): the record label / publisher extracted from the
-- ID3 TPUB tag. Nullable -- most home-ripped files carry no publisher tag.

ALTER TABLE "songs" ADD COLUMN "label" VARCHAR(255);
