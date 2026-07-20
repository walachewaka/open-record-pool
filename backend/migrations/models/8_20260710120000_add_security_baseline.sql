-- upgrade --
-- MOO-89: server-side sessions (revocable cookie-JWT) and the append-only
-- security audit log. NOTE: never end a comment line with a semicolon -- aerich
-- splits this file on ";\n" and a comment-only chunk crashes asyncpg 0.28.

CREATE TABLE IF NOT EXISTS "auth_sessions" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "jti" VARCHAR(32) NOT NULL UNIQUE,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "last_seen_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "expires_at" TIMESTAMPTZ NOT NULL,
    "revoked_at" TIMESTAMPTZ,
    "ip" VARCHAR(45),
    "user_agent" VARCHAR(255),
    "user_id" INT NOT NULL REFERENCES "users" ("id") ON DELETE CASCADE
);
COMMENT ON TABLE "auth_sessions" IS 'Server-side session records backing the cookie-JWT (MOO-89).';
CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires ON auth_sessions (expires_at);

CREATE TABLE IF NOT EXISTS "audit_log" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "event" VARCHAR(50) NOT NULL,
    "actor_username" VARCHAR(20),
    "target_type" VARCHAR(20),
    "target_id" VARCHAR(64),
    "ip" VARCHAR(45),
    "user_agent" VARCHAR(255),
    "detail" JSONB,
    "actor_id" INT REFERENCES "users" ("id") ON DELETE SET NULL
);
COMMENT ON TABLE "audit_log" IS 'Append-only security audit log (MOO-89).';
CREATE INDEX IF NOT EXISTS idx_audit_log_created ON audit_log (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_event ON audit_log (event);
CREATE INDEX IF NOT EXISTS idx_audit_log_actor ON audit_log (actor_id);
