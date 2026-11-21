-- Scheduling sprint migration: dispatcher scheduling board (FR-06).
-- Adds the dispatch status column to transit_events so a crew member can be
-- assigned to a transit and its priority can be reordered.
-- Idempotent: safe to run more than once.

ALTER TABLE transit_events
    ADD COLUMN IF NOT EXISTS schedule_status VARCHAR(20) DEFAULT 'APPROVED'
    CHECK (schedule_status IN ('PROPOSED', 'APPROVED', 'REJECTED'));

UPDATE transit_events
SET schedule_status = 'APPROVED'
WHERE schedule_status IS NULL;
