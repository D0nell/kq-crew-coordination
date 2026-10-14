"""
Loads the 7 synthetic CSVs into PostgreSQL.

What it does, in order:
  1. Creates the tables from db/schema.sql if they don't exist yet.
  2. Applies db/migrations/*.sql (idempotent).
  3. Empties the tables (TRUNCATE ... RESTART IDENTITY CASCADE) so the load is repeatable.
  4. Bulk-loads each CSV with COPY, parents before children.
  5. Resets the id sequences and checks row counts against the CSVs.

Usage (from the repo root, .venv active):
    python db/load_data.py --data-dir data/output

The connection string comes from --database-url or the DATABASE_URL
environment variable (a .env file in the repo root is read automatically):
    DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/kq_crew_coordination
"""

import argparse
import glob
import os
import sys

import psycopg2

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from api.config import get_database_url  # noqa: E402

# (table, csv file, id column) — parents before children so foreign keys hold.
LOAD_ORDER = [
    ("users", "Users.csv", "user_id"),
    ("crew_profiles", "Crew_Profiles.csv", "crew_id"),
    ("vehicles", "Vehicles.csv", "vehicle_id"),
    ("flight_schedules", "Flight_Schedules.csv", "flight_id"),
    ("transit_events", "Transit_Events.csv", "transit_id"),
    ("mobilization_log", "Mobilization_Log.csv", "log_id"),
    ("alerts", "Alerts.csv", "alert_id"),
]


def table_exists(cur, name):
    cur.execute("SELECT to_regclass(%s) IS NOT NULL", (f"public.{name}",))
    return cur.fetchone()[0]


def run_sql_file(cur, path):
    with open(path, encoding="utf-8") as f:
        cur.execute(f.read())


def load_all(database_url: str, data_dir: str, quiet: bool = False) -> dict:
    """Loads every CSV. Returns {table: row_count}. Raises on any mismatch."""
    log = (lambda *a: None) if quiet else print

    for _, csv_name, _ in LOAD_ORDER:
        path = os.path.join(data_dir, csv_name)
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"{path} not found. Generate the data first: "
                f"python data/generate_dataset.py --outdir {data_dir}")

    counts = {}
    conn = psycopg2.connect(database_url)
    try:
        with conn, conn.cursor() as cur:
            if not table_exists(cur, "users"):
                log("Creating tables from db/schema.sql ...")
                run_sql_file(cur, os.path.join(ROOT, "db", "schema.sql"))
            for mig in sorted(glob.glob(os.path.join(ROOT, "db", "migrations", "*.sql"))):
                log(f"Applying {os.path.basename(mig)} ...")
                run_sql_file(cur, mig)

            cur.execute("TRUNCATE predictions, alerts, mobilization_log, transit_events, "
                        "flight_schedules, vehicles, crew_profiles, users RESTART IDENTITY CASCADE")

            for table, csv_name, id_col in LOAD_ORDER:
                path = os.path.join(data_dir, csv_name)
                with open(path, encoding="utf-8") as f:
                    header = f.readline().strip().split(",")
                    cols = ", ".join(header)
                    f.seek(0)
                    cur.copy_expert(f"COPY {table} ({cols}) FROM STDIN WITH (FORMAT csv, HEADER true)", f)
                cur.execute(f"SELECT setval(pg_get_serial_sequence('{table}', '{id_col}'), "
                            f"COALESCE((SELECT MAX({id_col}) FROM {table}), 1))")
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                counts[table] = cur.fetchone()[0]
                with open(path, encoding="utf-8") as f:
                    expected = sum(1 for _ in f) - 1
                if counts[table] != expected:
                    raise RuntimeError(f"{table}: loaded {counts[table]} rows, CSV has {expected}")
                log(f"  {table:<18} {counts[table]:>7} rows")
    finally:
        conn.close()
    return counts


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", default="data/output")
    ap.add_argument("--database-url", default=None)
    args = ap.parse_args()
    try:
        counts = load_all(args.database_url or get_database_url(), args.data_dir)
    except (psycopg2.OperationalError, FileNotFoundError) as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    print(f"\nDone. {sum(counts.values())} rows loaded across {len(counts)} tables.")


if __name__ == "__main__":
    main()
