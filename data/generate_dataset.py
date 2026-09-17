"""
Kenya Airways Crew Coordination - Synthetic Dataset Generator
================================================================
Capstone Project: Proactive Crew Coordination (Donell Bikketi, 166604)

Generates a synthetic dataset for the 7-table schema described in the
proposal (Users, Crew_Profiles, Flight_Schedules, Vehicles,
Transit_Events, Mobilization_Log, Alerts), calibrated against publicly
known JKIA operating patterns and Nairobi road-corridor characteristics
(standing in for live OpenSky Network / OpenStreetMap pulls, per the
"Data Requirements" section of the proposal).

Design principle: delay outcomes are NOT random. They are generated as
a function of time-of-day, day-of-week, corridor, weather, and traffic
congestion index — the same features your XGBoost model is meant to
learn from (Chapter 3, Section 3.2.3). This makes the dataset usable
for a real train/test split rather than an unlearnable random target.

Usage:
    python3 generate_dataset.py --n-transit 6000 --seed 42 --outdir ./output

Outputs (CSV, one per schema table) + a data_dictionary.md
"""

import argparse
import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# Reference / calibration constants
# ---------------------------------------------------------------------------
# Nairobi corridors relevant to KQ crew mobilization (from proposal Ch.1/4)
CORRIDORS = [
    {"name": "Mombasa Rd - JKIA",        "base_km": 14.5, "base_congestion": 0.62},
    {"name": "Westlands - JKIA",         "base_km": 24.0, "base_congestion": 0.55},
    {"name": "Embakasi - JKIA",          "base_km": 6.0,  "base_congestion": 0.40},
    {"name": "KQ Training Centre - JKIA","base_km": 4.2,  "base_congestion": 0.30},
    {"name": "Medical Centre - JKIA",    "base_km": 9.8,  "base_congestion": 0.45},
    {"name": "South B - JKIA",           "base_km": 8.5,  "base_congestion": 0.48},
]

VEHICLE_TYPES = ["Crew Van", "Shuttle Bus", "Saloon Car", "Minibus"]
CREW_RANKS = ["Captain", "First Officer", "Senior Cabin Crew", "Cabin Crew"]
EVENT_TYPES = ["DISPATCHED", "EN_ROUTE", "CHECKED_IN", "ARRIVED", "DELAYED_ENROUTE"]
ALERT_TYPES = ["DELAY_WARNING", "NO_SHOW_RISK", "COMPLIANCE_RISK", "VEHICLE_UNAVAILABLE"]

FIRST_NAMES = ["James","Mary","John","Grace","Peter","Faith","David","Ann","Samuel",
    "Joyce","Kevin","Brian","Lucy","Daniel","Esther","Michael","Nancy","Paul",
    "Caroline","Victor","Sarah","Dennis","Mercy","George","Ruth","Felix","Diana",
    "Charles","Agnes","Elijah"]
LAST_NAMES = ["Otieno","Wanjiru","Kamau","Achieng","Mutua","Njoroge","Kariuki",
    "Wafula","Mwangi","Cheruiyot","Omondi","Njeri","Kiptoo","Wambui","Ochieng",
    "Mbeki","Waweru","Akinyi","Kilonzo","Gitau"]

rng = np.random.default_rng(42)  # reseeded in main()


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


# ---------------------------------------------------------------------------
# Table generators
# ---------------------------------------------------------------------------
def gen_users(n_dispatchers, n_crew, rng):
    rows = []
    uid = 1
    for _ in range(n_dispatchers):
        fn, ln = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        rows.append({
            "user_id": uid, "full_name": f"{fn} {ln}", "role": "DISPATCHER",
            "email": f"{fn.lower()}.{ln.lower()}{uid}@kenya-airways.com",
            "phone": f"+2547{rng.integers(10000000,99999999)}",
        })
        uid += 1
    for _ in range(n_crew):
        fn, ln = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        rows.append({
            "user_id": uid, "full_name": f"{fn} {ln}", "role": "CREW",
            "email": f"{fn.lower()}.{ln.lower()}{uid}@kenya-airways.com",
            "phone": f"+2547{rng.integers(10000000,99999999)}",
        })
        uid += 1
    return pd.DataFrame(rows)


def gen_crew_profiles(users_df, rng):
    crew_users = users_df[users_df.role == "CREW"]
    rows = []
    for i, u in enumerate(crew_users.itertuples(), start=1):
        start = datetime(2019, 1, 1) + timedelta(days=int(rng.integers(0, 2200)))
        rows.append({
            "crew_id": i, "user_id": u.user_id,
            "rank": rng.choice(CREW_RANKS, p=[0.12, 0.18, 0.30, 0.40]),
            "base_location": rng.choice(["JKIA Base", "Westlands Base", "Embakasi Base"]),
            "employment_start_date": start.date().isoformat(),
        })
    return pd.DataFrame(rows)


def gen_vehicles(n_vehicles, rng):
    rows = []
    for i in range(1, n_vehicles + 1):
        rows.append({
            "vehicle_id": i,
            "vehicle_type": rng.choice(VEHICLE_TYPES, p=[0.4, 0.25, 0.2, 0.15]),
            "capacity": {"Crew Van": 8, "Shuttle Bus": 20, "Saloon Car": 4, "Minibus": 14},
            "status": rng.choice(["AVAILABLE", "IN_USE", "MAINTENANCE"], p=[0.6, 0.32, 0.08]),
        })
    df = pd.DataFrame(rows)
    df["capacity"] = df.apply(lambda r: r["capacity"][r["vehicle_type"]], axis=1)
    return df


def gen_flight_schedules(crew_df, n_flights, rng, start_date):
    destinations = ["LOS","DXB","AMS","BOM","LHR","JNB","ADD","CDG","GRU","HKG"]
    rows = []
    for i in range(1, n_flights + 1):
        crew_id = int(rng.choice(crew_df.crew_id))
        dep_offset_days = int(rng.integers(0, 90))
        dep_hour = int(rng.integers(0, 24))
        dep_time = start_date + timedelta(days=dep_offset_days, hours=dep_hour,
                                           minutes=int(rng.integers(0, 60)))
        flight_duration_hrs = float(rng.uniform(2, 11))
        rows.append({
            "flight_id": i,
            "crew_id": crew_id,
            "flight_number": f"KQ{rng.integers(100,999)}",
            "scheduled_departure": dep_time.isoformat(sep=" "),
            "scheduled_arrival": (dep_time + timedelta(hours=flight_duration_hrs)).isoformat(sep=" "),
            "origin": "NBO",
            "destination": rng.choice(destinations),
        })
    return pd.DataFrame(rows)


def gen_transit_events(flight_df, crew_df, vehicle_df, n_transit, rng, start_date):
    """
    Core ML table. Delay outcome is a function of engineered features,
    not pure noise, so a model trained on it can actually learn signal.
    """
    rows = []
    for i in range(1, n_transit + 1):
        flight = flight_df.sample(1, random_state=int(rng.integers(0, 1_000_000))).iloc[0]
        corridor = CORRIDORS[rng.integers(0, len(CORRIDORS))]
        vehicle_id = int(rng.choice(vehicle_df.vehicle_id))

        sched_pickup = pd.to_datetime(flight["scheduled_departure"]) - timedelta(
            hours=float(rng.uniform(2.0, 3.5)))
        dow = sched_pickup.dayofweek            # 0=Mon .. 6=Sun
        hour = sched_pickup.hour
        is_weekday = dow < 5

        # --- Feature engineering (mirrors proposal 4.x feature set) ---
        is_rush_hour = int(hour in (6, 7, 8, 9, 16, 17, 18, 19))
        weather_flag = int(rng.random() < (0.28 if hour in range(15, 20) else 0.14))  # more rain in afternoons
        base_congestion = corridor["base_congestion"]
        congestion_index = np.clip(
            base_congestion
            + (0.22 if is_rush_hour else -0.05)
            + (0.10 if is_weekday else -0.08)
            + rng.normal(0, 0.08),
            0.02, 0.99,
        )
        historical_avg_delay_min = np.clip(
            corridor["base_km"] * 0.9 + (10 if is_rush_hour else 2) + rng.normal(0, 4), 0, None
        )

        # --- Delay-generating process (logistic, feature-driven) ---
        z = (
            -3.2
            + 5.2 * congestion_index
            + 1.3 * weather_flag
            + 0.9 * is_rush_hour
            + 0.03 * corridor["base_km"]
            + rng.normal(0, 0.22)
        )
        delay_prob = sigmoid(z)
        is_delayed = rng.random() < delay_prob

        if is_delayed:
            delay_minutes = float(np.clip(rng.gamma(shape=2.2, scale=12) + 5, 3, 180))
        else:
            delay_minutes = float(np.clip(rng.normal(2, 2.5), -5, 8))
        delay_minutes = max(delay_minutes, 0)

        if delay_minutes < 5:
            risk_class = "LOW"
        elif delay_minutes < 20:
            risk_class = "MEDIUM"
        elif delay_minutes < 45:
            risk_class = "HIGH"
        else:
            risk_class = "CRITICAL"

        actual_pickup = sched_pickup + timedelta(minutes=float(rng.normal(0, 3)))
        travel_minutes = corridor["base_km"] * (1.6 + congestion_index * 2.2)
        actual_arrival = actual_pickup + timedelta(minutes=travel_minutes + delay_minutes)
        sched_arrival = sched_pickup + timedelta(minutes=travel_minutes)

        rows.append({
            "transit_id": i,
            "crew_id": int(flight["crew_id"]),
            "flight_id": int(flight["flight_id"]),
            "vehicle_id": vehicle_id,
            "corridor": corridor["name"],
            "pickup_location": corridor["name"].split(" - ")[0],
            "dropoff_location": "JKIA",
            "scheduled_pickup_time": sched_pickup.isoformat(sep=" "),
            "actual_pickup_time": actual_pickup.isoformat(sep=" "),
            "scheduled_arrival_time": sched_arrival.isoformat(sep=" "),
            "actual_arrival_time": actual_arrival.isoformat(sep=" "),
            "distance_km": round(corridor["base_km"], 2),
            "day_of_week": dow,               # 0=Mon
            "hour_of_day": hour,
            "is_weekday": int(is_weekday),
            "is_rush_hour": is_rush_hour,
            "weather_flag": weather_flag,
            "traffic_congestion_index": round(float(congestion_index), 3),
            "historical_avg_delay_min": round(float(historical_avg_delay_min), 2),
            "delay_minutes": round(delay_minutes, 2),
            "delay_risk_class": risk_class,
        })
    return pd.DataFrame(rows)


def gen_mobilization_log(transit_df, rng):
    rows = []
    log_id = 1
    for t in transit_df.itertuples():
        n_events = int(rng.integers(3, 6))
        chosen = ["DISPATCHED"] + list(
            rng.choice([e for e in EVENT_TYPES if e != "DISPATCHED"],
                       size=n_events - 1, replace=False)
        )
        base_time = pd.to_datetime(t.scheduled_pickup_time) - timedelta(minutes=15)
        for j, ev in enumerate(chosen):
            rows.append({
                "log_id": log_id,
                "transit_id": t.transit_id,
                "event_type": ev,
                "event_timestamp": (base_time + timedelta(minutes=8 * j)).isoformat(sep=" "),
            })
            log_id += 1
    return pd.DataFrame(rows)


def gen_alerts(transit_df, rng):
    rows = []
    alert_id = 1
    high_risk = transit_df[transit_df.delay_risk_class.isin(["HIGH", "CRITICAL"])]
    for t in high_risk.itertuples():
        if rng.random() < 0.85:  # not every high-risk transit generates a logged alert
            rows.append({
                "alert_id": alert_id,
                "transit_id": t.transit_id,
                "alert_type": "DELAY_WARNING" if t.delay_risk_class == "HIGH" else rng.choice(
                    ["NO_SHOW_RISK", "COMPLIANCE_RISK", "DELAY_WARNING"], p=[0.3, 0.2, 0.5]),
                "severity": t.delay_risk_class,
                "generated_at": (pd.to_datetime(t.scheduled_pickup_time)
                                  - timedelta(minutes=int(rng.integers(10, 40)))).isoformat(sep=" "),
                "resolved": bool(rng.random() < 0.7),
            })
            alert_id += 1
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-transit", type=int, default=6000,
                     help="Number of Transit_Events rows (the ML training table)")
    ap.add_argument("--n-flights", type=int, default=1500)
    ap.add_argument("--n-crew", type=int, default=180)
    ap.add_argument("--n-dispatchers", type=int, default=15)
    ap.add_argument("--n-vehicles", type=int, default=40)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--outdir", type=str, default="./output")
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    os.makedirs(args.outdir, exist_ok=True)
    start_date = datetime(2025, 1, 1)

    print("Generating Users...")
    users_df = gen_users(args.n_dispatchers, args.n_crew, rng)

    print("Generating Crew_Profiles...")
    crew_df = gen_crew_profiles(users_df, rng)

    print("Generating Vehicles...")
    vehicle_df = gen_vehicles(args.n_vehicles, rng)

    print("Generating Flight_Schedules...")
    flight_df = gen_flight_schedules(crew_df, args.n_flights, rng, start_date)

    print("Generating Transit_Events (ML table)...")
    transit_df = gen_transit_events(flight_df, crew_df, vehicle_df, args.n_transit, rng, start_date)

    print("Generating Mobilization_Log...")
    mob_log_df = gen_mobilization_log(transit_df, rng)

    print("Generating Alerts...")
    alerts_df = gen_alerts(transit_df, rng)

    # --- Train/val/test split (80/10/10, stratified on delay_risk_class) ---
    from math import floor
    transit_df = transit_df.sample(frac=1, random_state=args.seed).reset_index(drop=True)
    splits = []
    for cls, group in transit_df.groupby("delay_risk_class"):
        n = len(group)
        n_train = floor(n * 0.8)
        n_val = floor(n * 0.1)
        g = group.reset_index(drop=True)
        g_train = g.iloc[:n_train].copy(); g_train["split"] = "train"
        g_val = g.iloc[n_train:n_train + n_val].copy(); g_val["split"] = "val"
        g_test = g.iloc[n_train + n_val:].copy(); g_test["split"] = "test"
        splits.extend([g_train, g_val, g_test])
    transit_df = pd.concat(splits, ignore_index=True)

    # --- Save ---
    tables = {
        "Users": users_df,
        "Crew_Profiles": crew_df,
        "Flight_Schedules": flight_df,
        "Vehicles": vehicle_df,
        "Transit_Events": transit_df,
        "Mobilization_Log": mob_log_df,
        "Alerts": alerts_df,
    }
    for name, df in tables.items():
        path = os.path.join(args.outdir, f"{name}.csv")
        df.to_csv(path, index=False)
        print(f"  wrote {path}  ({len(df)} rows)")

    print("\nClass balance in Transit_Events:")
    print(transit_df["delay_risk_class"].value_counts(normalize=True).round(3))
    print("\nSplit sizes:")
    print(transit_df["split"].value_counts())


if __name__ == "__main__":
    main()
