-- KQ Crew Coordination — PostgreSQL schema
-- Mirrors Proposal Section 4.6 (Database Schema): 7 core tables.
-- Column names match data/generate_dataset.py so synthetic CSVs load in directly.

CREATE TABLE users (
    user_id     SERIAL PRIMARY KEY,
    full_name   VARCHAR(120) NOT NULL,
    role        VARCHAR(20)  NOT NULL CHECK (role IN ('DISPATCHER', 'CREW')),
    email       VARCHAR(160) UNIQUE NOT NULL,
    phone       VARCHAR(20)
);

CREATE TABLE crew_profiles (
    crew_id                SERIAL PRIMARY KEY,
    user_id                INT REFERENCES users(user_id),
    rank                   VARCHAR(40),
    base_location           VARCHAR(80),
    employment_start_date  DATE
);

CREATE TABLE vehicles (
    vehicle_id      SERIAL PRIMARY KEY,
    vehicle_type    VARCHAR(40),
    capacity        INT,
    status          VARCHAR(20) CHECK (status IN ('AVAILABLE','IN_USE','MAINTENANCE'))
);

CREATE TABLE flight_schedules (
    flight_id            SERIAL PRIMARY KEY,
    crew_id              INT REFERENCES crew_profiles(crew_id),
    flight_number        VARCHAR(10),
    scheduled_departure  TIMESTAMP,
    scheduled_arrival    TIMESTAMP,
    origin                VARCHAR(5),
    destination           VARCHAR(5)
);

CREATE TABLE transit_events (
    transit_id                 SERIAL PRIMARY KEY,
    crew_id                    INT REFERENCES crew_profiles(crew_id),
    flight_id                  INT REFERENCES flight_schedules(flight_id),
    vehicle_id                 INT REFERENCES vehicles(vehicle_id),
    corridor                   VARCHAR(60),
    pickup_location             VARCHAR(60),
    dropoff_location            VARCHAR(60),
    scheduled_pickup_time       TIMESTAMP,
    actual_pickup_time          TIMESTAMP,
    scheduled_arrival_time      TIMESTAMP,
    actual_arrival_time         TIMESTAMP,
    distance_km                 NUMERIC(6,2),
    day_of_week                 SMALLINT,
    hour_of_day                 SMALLINT,
    is_weekday                  BOOLEAN,
    is_rush_hour                BOOLEAN,
    weather_flag                BOOLEAN,
    traffic_congestion_index    NUMERIC(4,3),
    historical_avg_delay_min    NUMERIC(6,2),
    delay_minutes                NUMERIC(6,2),
    delay_risk_class            VARCHAR(10) CHECK (delay_risk_class IN ('LOW','MEDIUM','HIGH','CRITICAL')),
    split                        VARCHAR(5)  CHECK (split IN ('train','val','test'))
);

CREATE TABLE mobilization_log (
    log_id            SERIAL PRIMARY KEY,
    transit_id        INT REFERENCES transit_events(transit_id),
    event_type        VARCHAR(20),
    event_timestamp   TIMESTAMP
);

CREATE TABLE alerts (
    alert_id       SERIAL PRIMARY KEY,
    transit_id     INT REFERENCES transit_events(transit_id),
    alert_type     VARCHAR(30),
    severity       VARCHAR(10),
    generated_at    TIMESTAMP,
    resolved       BOOLEAN DEFAULT FALSE
);

-- Indexes for the spatial-temporal queries mentioned in Proposal Section 4.6
CREATE INDEX idx_transit_scheduled_pickup ON transit_events (scheduled_pickup_time);
CREATE INDEX idx_transit_corridor ON transit_events (corridor);
CREATE INDEX idx_alerts_transit ON alerts (transit_id);
