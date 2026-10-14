"""Database loader tests (TC-01 to TC-06)."""

import os
import shutil
import subprocess
import sys

import psycopg2
import pytest

from conftest import ROOT

TABLES = ["crew_profiles", "vehicles", "flight_schedules", "transit_events", "alerts", "mobilization_log"]


def test_row_counts_match_csv(q, dataset_dir, actual):
    """TC-01 | Loader: row counts in PostgreSQL equal the rows in each CSV | every table count equals its CSV row count"""
    import csv
    files = {"crew_profiles": "Crew_Profiles.csv", "vehicles": "Vehicles.csv",
             "flight_schedules": "Flight_Schedules.csv", "transit_events": "Transit_Events.csv",
             "mobilization_log": "Mobilization_Log.csv", "users": "Users.csv"}
    seen = {}
    for table, fname in files.items():
        with open(os.path.join(dataset_dir, fname), newline="", encoding="utf-8") as f:
            n_csv = sum(1 for _ in csv.reader(f)) - 1
        n_db = q(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"]
        seen[table] = (n_csv, n_db)
        assert n_csv == n_db, f"{table}: csv {n_csv} vs db {n_db}"
    actual("All 6 tables match: " + ", ".join(f"{t} {b}" for t, (a, b) in seen.items()))


def test_fresh_database_gets_schema_and_migration(test_db_url, dataset_dir, actual):
    """TC-02 | Loader: an empty database gets the schema and the Sprint II migration | tables, predictions table and alert columns exist after loading"""
    import psycopg2.extensions
    from db.load_data import load_all
    dsn = psycopg2.extensions.parse_dsn(test_db_url)
    admin = psycopg2.connect(**dict(dsn, dbname="postgres"))
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute("DROP DATABASE IF EXISTS kq_fresh WITH (FORCE)")
        cur.execute("CREATE DATABASE kq_fresh")
    fresh_url = psycopg2.extensions.make_dsn(**dict(dsn, dbname="kq_fresh"))
    try:
        load_all(fresh_url, dataset_dir, quiet=True)
        conn = psycopg2.connect(fresh_url)
        with conn, conn.cursor() as cur:
            cur.execute("SELECT to_regclass('predictions') IS NOT NULL")
            assert cur.fetchone()[0]
            cur.execute("""SELECT column_name FROM information_schema.columns WHERE table_name='alerts'""")
            cols = {r[0] for r in cur.fetchall()}
        conn.close()
        assert {"delay_probability", "source", "model_version", "resolved_at"} <= cols
        actual("Fresh database created with predictions table and the 4 new alert columns")
    finally:
        with admin.cursor() as cur:
            cur.execute("DROP DATABASE IF EXISTS kq_fresh WITH (FORCE)")
        admin.close()


def test_load_is_repeatable(test_db_url, dataset_dir, q, actual):
    """TC-03 | Loader: running the load twice gives the same counts and new rows still get fresh ids | same counts, no duplicate-key error on insert"""
    from db.load_data import load_all
    first = load_all(test_db_url, dataset_dir, quiet=True)
    second = load_all(test_db_url, dataset_dir, quiet=True)
    assert first == second
    q("""INSERT INTO alerts (transit_id, alert_type, severity, generated_at, resolved, source)
         SELECT transit_id, 'DELAY_WARNING', 'HIGH', NOW(), FALSE, 'historical'
         FROM transit_events LIMIT 1""")
    q("DELETE FROM alerts WHERE alert_id = (SELECT MAX(alert_id) FROM alerts)")
    actual(f"Second load returned identical counts ({sum(second.values())} rows); insert after reload succeeded")


def test_no_orphan_foreign_keys(q, actual):
    """TC-04 | Loader: no child row points at a missing parent | zero orphan rows"""
    checks = {
        "transit->crew": "SELECT COUNT(*) n FROM transit_events t LEFT JOIN crew_profiles c USING (crew_id) WHERE c.crew_id IS NULL",
        "transit->vehicle": "SELECT COUNT(*) n FROM transit_events t LEFT JOIN vehicles v USING (vehicle_id) WHERE v.vehicle_id IS NULL",
        "transit->flight": "SELECT COUNT(*) n FROM transit_events t LEFT JOIN flight_schedules f USING (flight_id) WHERE f.flight_id IS NULL",
        "alert->transit": "SELECT COUNT(*) n FROM alerts a LEFT JOIN transit_events t USING (transit_id) WHERE t.transit_id IS NULL",
    }
    bad = {k: q(sql)[0]["n"] for k, sql in checks.items()}
    assert not any(bad.values()), bad
    actual("0 orphans across 4 relationships")


def test_missing_csv_is_reported(test_db_url, dataset_dir, tmp_path, actual):
    """TC-05 | Loader: a CSV is missing from the data folder | FileNotFoundError naming the file; existing data untouched"""
    from db.load_data import load_all
    broken = tmp_path / "broken"
    shutil.copytree(dataset_dir, broken)
    os.remove(broken / "Vehicles.csv")
    with pytest.raises(FileNotFoundError) as e:
        load_all(test_db_url, str(broken), quiet=True)
    assert "Vehicles.csv" in str(e.value)
    conn = psycopg2.connect(test_db_url)
    with conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM transit_events")
        assert cur.fetchone()[0] > 0
    conn.close()
    actual(f"Raised FileNotFoundError: {e.value}; transit_events still populated")


def test_unreachable_database_exits_cleanly(dataset_dir, actual):
    """TC-06 | Loader CLI: PostgreSQL is not reachable on the given URL | exit code 1 and a one-line 'ERROR:' message, no stack trace"""
    r = subprocess.run([sys.executable, os.path.join(ROOT, "db", "load_data.py"), "--data-dir", dataset_dir,
                        "--database-url", "postgresql://postgres:x@localhost:1/none"],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 1
    assert "ERROR:" in (r.stdout + r.stderr)
    assert "Traceback" not in r.stderr
    actual("Exit code 1; message: " + (r.stdout + r.stderr).strip().splitlines()[-1][:120])
