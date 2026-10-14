-- Sprint II migration: support model scoring and alert workflow.
-- Idempotent: safe to run more than once.

-- 1. Alerts raised by the model carry the score that triggered them.
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS delay_probability NUMERIC(5,4);
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS source VARCHAR(12) NOT NULL DEFAULT 'historical';
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS model_version VARCHAR(40);
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMP;

-- One live model alert per transit: re-scoring updates it instead of duplicating it.
CREATE UNIQUE INDEX IF NOT EXISTS uq_alerts_model_transit
    ON alerts (transit_id) WHERE source = 'model';

-- 2. Every score the model produces is stored, alert or not (FR-04).
CREATE TABLE IF NOT EXISTS predictions (
    prediction_id      SERIAL PRIMARY KEY,
    transit_id         INT NOT NULL UNIQUE REFERENCES transit_events(transit_id),
    delay_probability  NUMERIC(5,4) NOT NULL CHECK (delay_probability BETWEEN 0 AND 1),
    predicted_delayed  BOOLEAN NOT NULL,
    risk_level         VARCHAR(10) NOT NULL CHECK (risk_level IN ('LOW','MEDIUM','HIGH','CRITICAL')),
    model_version      VARCHAR(40) NOT NULL,
    scored_at          TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_transit_split ON transit_events (split);
CREATE INDEX IF NOT EXISTS idx_alerts_open ON alerts (resolved, source);
