"""
Sanity-checks the KQ Crew Coordination synthetic dataset.

Usage (from the repo root, with the .venv active):
    python data\\validate_dataset.py --data-dir data\\output

Prints PASS / WARN / FAIL per check and exits non-zero if anything FAILs,
so it can also be dropped into the CI workflow later.
"""
import argparse
import os
import sys

import pandas as pd

TABLES = ["Users", "Crew_Profiles", "Flight_Schedules", "Vehicles",
          "Transit_Events", "Mobilization_Log", "Alerts"]
PKS = {"Users": "user_id", "Crew_Profiles": "crew_id", "Flight_Schedules": "flight_id",
       "Vehicles": "vehicle_id", "Transit_Events": "transit_id",
       "Mobilization_Log": "log_id", "Alerts": "alert_id"}
FKS = [  # (child table, column, parent table, parent column)
    ("Crew_Profiles", "user_id", "Users", "user_id"),
    ("Flight_Schedules", "crew_id", "Crew_Profiles", "crew_id"),
    ("Transit_Events", "crew_id", "Crew_Profiles", "crew_id"),
    ("Transit_Events", "flight_id", "Flight_Schedules", "flight_id"),
    ("Transit_Events", "vehicle_id", "Vehicles", "vehicle_id"),
    ("Mobilization_Log", "transit_id", "Transit_Events", "transit_id"),
    ("Alerts", "transit_id", "Transit_Events", "transit_id"),
]
FEATURES = ["is_weekday", "is_rush_hour", "weather_flag", "traffic_congestion_index",
            "historical_avg_delay_min", "distance_km", "hour_of_day", "day_of_week"]

results = {"PASS": 0, "WARN": 0, "FAIL": 0}


def report(level, msg):
    results[level] += 1
    print(f"[{level}] {msg}")


def check(cond, ok_msg, bad_msg, level_if_bad="FAIL"):
    report("PASS" if cond else level_if_bad, ok_msg if cond else bad_msg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data/output")
    args = ap.parse_args()

    dfs = {}
    for t in TABLES:
        path = os.path.join(args.data_dir, f"{t}.csv")
        if not os.path.exists(path):
            report("FAIL", f"{t}.csv missing in {args.data_dir}")
            continue
        dfs[t] = pd.read_csv(path)
        report("PASS", f"{t}.csv loaded ({len(dfs[t])} rows, {dfs[t].shape[1]} cols)")

    print("\n-- Keys --")
    for t, pk in PKS.items():
        if t in dfs:
            d = dfs[t][pk].duplicated().sum()
            check(d == 0, f"{t}.{pk} unique", f"{t}.{pk} has {d} duplicate ids")
    for child, col, parent, pcol in FKS:
        if child in dfs and parent in dfs:
            orphans = (~dfs[child][col].isin(dfs[parent][pcol])).sum()
            check(orphans == 0, f"{child}.{col} -> {parent}.{pcol} all resolve",
                  f"{child}.{col} has {orphans} orphan rows")

    print("\n-- Nulls --")
    for t, df in dfs.items():
        n = int(df.isna().sum().sum())
        check(n == 0, f"{t}: no nulls", f"{t}: {n} null cells", "WARN")

    if "Transit_Events" not in dfs:
        return finish()
    te = dfs["Transit_Events"]

    print("\n-- Transit_Events values --")
    for col in ["is_weekday", "is_rush_hour", "weather_flag"]:
        check(set(te[col].unique()) <= {0, 1}, f"{col} is 0/1", f"{col} has values outside 0/1")
    check(te.traffic_congestion_index.between(0, 1).all(), "congestion index within 0-1",
          "congestion index outside 0-1")
    check(te.hour_of_day.between(0, 23).all(), "hour_of_day within 0-23", "hour_of_day out of range")
    check(te.day_of_week.between(0, 6).all(), "day_of_week within 0-6", "day_of_week out of range")
    check((te.delay_minutes >= 0).all(), "delay_minutes never negative", "negative delay_minutes found")

    cls = pd.cut(te.delay_minutes, [-1e-9, 5 - 1e-9, 20 - 1e-9, 45 - 1e-9, 1e9],
                 labels=["LOW", "MEDIUM", "HIGH", "CRITICAL"], right=True).astype(str)
    mismatch = (cls != te.delay_risk_class).sum()
    check(mismatch == 0, "delay_risk_class matches delay_minutes thresholds (5/20/45)",
          f"{mismatch} rows where delay_risk_class disagrees with delay_minutes")

    print("\n-- Timestamps --")
    for c in ["scheduled_pickup_time", "actual_pickup_time", "scheduled_arrival_time", "actual_arrival_time"]:
        te[c] = pd.to_datetime(te[c], errors="coerce")
    check(te[["scheduled_pickup_time", "actual_pickup_time", "scheduled_arrival_time",
              "actual_arrival_time"]].notna().all().all(), "all timestamps parse", "unparseable timestamps")
    check((te.scheduled_arrival_time > te.scheduled_pickup_time).all(),
          "scheduled arrival always after scheduled pickup", "scheduled arrival not after pickup in some rows")
    check((te.actual_arrival_time > te.actual_pickup_time).all(),
          "actual arrival always after actual pickup", "actual arrival not after pickup in some rows")

    print("\n-- Cross-table consistency --")
    if "Flight_Schedules" in dfs:
        fl = dfs["Flight_Schedules"].set_index("flight_id").crew_id
        bad = (te.crew_id != te.flight_id.map(fl)).sum()
        check(bad == 0, "transit crew_id matches the crew assigned to that flight",
              f"{bad} transits whose crew_id differs from their flight's crew_id", "WARN")
    if "Alerts" in dfs:
        sev = te.set_index("transit_id").delay_risk_class
        bad = (~dfs["Alerts"].transit_id.map(sev).isin(["HIGH", "CRITICAL"])).sum()
        check(bad == 0, "alerts exist only for HIGH/CRITICAL transits", f"{bad} alerts on LOW/MEDIUM transits")

    print("\n-- Class balance and splits --")
    share = te.delay_risk_class.value_counts(normalize=True).round(3)
    print("      class share:", share.to_dict())
    check(share.min() >= 0.05, "every class has >= 5% of rows", "a class is under 5% of rows", "WARN")
    binary = te.delay_risk_class.isin(["HIGH", "CRITICAL"])
    print(f"      DELAYED (HIGH+CRITICAL) rate: {binary.mean():.3f}")
    sp = te.split.value_counts(normalize=True).round(3)
    print("      split share:", sp.to_dict())
    check(abs(sp.get("train", 0) - 0.8) < 0.02 and abs(sp.get("val", 0) - 0.1) < 0.02,
          "split is ~80/10/10", "split proportions are off from 80/10/10")
    by_split = pd.crosstab(te.split, te.delay_risk_class, normalize="index")
    drift = (by_split - by_split.mean()).abs().max().max()
    check(drift < 0.03, f"class mix stable across splits (max drift {drift:.3f})",
          f"class mix differs across splits (max drift {drift:.3f})", "WARN")

    print("\n-- Leakage and signal --")
    corr = te[FEATURES].corrwith(binary.astype(int)).abs().sort_values(ascending=False)
    print("      |corr| with DELAYED:", corr.round(3).to_dict())
    check(corr.max() < 0.8, "no feature is near-perfectly correlated with the target",
          f"{corr.idxmax()} correlates {corr.max():.2f} with the target - possible leakage")
    check(corr.max() > 0.1, "at least one feature carries real signal",
          "no feature correlates with the target - labels may be unlearnable", "WARN")
    dup = te.drop(columns=["transit_id"]).duplicated().sum()
    check(dup == 0, "no duplicate transit rows", f"{dup} duplicate transit rows", "WARN")

    finish()


def finish():
    print(f"\nSUMMARY: {results['PASS']} pass, {results['WARN']} warn, {results['FAIL']} fail")
    sys.exit(1 if results["FAIL"] else 0)


if __name__ == "__main__":
    main()