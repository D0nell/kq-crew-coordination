-- Sprint III: authentication foundation.
-- Preserve all existing users and their records.
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS password_hash TEXT;
