-- Sprint III: crew GPS location sharing (FR-03).
-- One row per position the crew member's phone sends during a transit.
CREATE TABLE IF NOT EXISTS gps_pings (
    ping_id     BIGSERIAL PRIMARY KEY,
    transit_id  INTEGER NOT NULL REFERENCES transit_events (transit_id) ON DELETE CASCADE,
    user_id     INTEGER NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
    latitude    DOUBLE PRECISION NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude   DOUBLE PRECISION NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    accuracy_m  REAL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gps_transit_time ON gps_pings (transit_id, recorded_at DESC);