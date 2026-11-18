-- Sprint III: crew readiness checklist (FR-09) and arrival confirmation (FR-11).
-- The list of tasks lives in code (api/crew_features.py); only the ticks are stored.
CREATE TABLE IF NOT EXISTS transit_checklist (
    item_id    SERIAL PRIMARY KEY,
    transit_id INTEGER NOT NULL REFERENCES transit_events (transit_id) ON DELETE CASCADE,
    task_code  VARCHAR(30) NOT NULL,
    done       BOOLEAN NOT NULL DEFAULT FALSE,
    done_at    TIMESTAMPTZ,
    UNIQUE (transit_id, task_code)
);

CREATE TABLE IF NOT EXISTS transit_arrival (
    transit_id   INTEGER PRIMARY KEY REFERENCES transit_events (transit_id) ON DELETE CASCADE,
    confirmed_by INTEGER REFERENCES users (user_id),
    confirmed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);