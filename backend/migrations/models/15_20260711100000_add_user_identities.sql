-- upgrade --
-- MOO-88: linked external IDP identities (OIDC single sign-on). One user owns
-- N identities; a login is matched on (provider, subject) only. NOTE: never end
-- a comment line with a semicolon -- aerich splits this file on ";\n" and a
-- comment-only chunk crashes asyncpg 0.28.

CREATE TABLE IF NOT EXISTS "user_identities" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "provider" VARCHAR(40) NOT NULL,
    "subject" VARCHAR(255) NOT NULL,
    "email" VARCHAR(255),
    "email_verified" BOOL NOT NULL DEFAULT FALSE,
    "display_name" VARCHAR(255),
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "last_login_at" TIMESTAMPTZ,
    "user_id" INT NOT NULL REFERENCES "users" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_user_identities_provider_subject" UNIQUE ("provider", "subject")
);
COMMENT ON TABLE "user_identities" IS 'Linked external IDP identities (MOO-88).';
CREATE INDEX IF NOT EXISTS idx_user_identities_user ON user_identities (user_id);
CREATE INDEX IF NOT EXISTS idx_user_identities_email ON user_identities (LOWER(email));
