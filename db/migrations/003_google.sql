-- Sprint III: Google sign-in.
-- A Google account is identified by its stable "sub" id, not by its email address.
-- Accounts created through Google have no password (password_hash stays NULL).
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS google_sub VARCHAR(64);

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_google_sub
    ON users (google_sub) WHERE google_sub IS NOT NULL;