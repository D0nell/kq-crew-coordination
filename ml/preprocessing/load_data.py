"""
Loads and preprocesses the KQ Crew Coordination dataset for model
training. Mirrors the logic from ml/training/train_xgboost.ipynb, but
as a reusable script rather than notebook cells, so it can run outside
Colab (e.g. from the API, or a retraining job) and be imported cleanly.

Usage:
    from ml.preprocessing.load_data import load_and_preprocess
    train_df, val_df, test_df, encoders = load_and_preprocess("data/output")
"""

import os
import pandas as pd
from sklearn.preprocessing import LabelEncoder

FEATURE_COLS = [
    "is_weekday", "is_rush_hour", "weather_flag",
    "traffic_congestion_index", "historical_avg_delay_min",
    "distance_km", "hour_of_day", "day_of_week", "capacity",
    "corridor_enc", "rank_enc", "base_location_enc",
    "vehicle_type_enc", "destination_enc",
]

CATEGORICAL_COLS = ["corridor", "rank", "base_location", "vehicle_type", "destination"]

DATETIME_COLS = [
    "scheduled_pickup_time", "actual_pickup_time",
    "scheduled_arrival_time", "actual_arrival_time",
]


def load_and_preprocess(data_dir: str):
    """
    Loads the 7 CSVs from data_dir, merges in crew/vehicle/flight
    features, encodes categoricals, and builds the binary delay target.

    Returns: (train_df, val_df, test_df, encoders)
    where each df has FEATURE_COLS + 'delay_binary' + 'delay_risk_class'.
    encoders is a dict of {column_name: fitted LabelEncoder} — reuse
    these at inference time so category codes stay consistent.
    """
    transit = pd.read_csv(os.path.join(data_dir, "Transit_Events.csv"))
    crew = pd.read_csv(os.path.join(data_dir, "Crew_Profiles.csv"))
    vehicles = pd.read_csv(os.path.join(data_dir, "Vehicles.csv"))
    flights = pd.read_csv(os.path.join(data_dir, "Flight_Schedules.csv"))

    for col in DATETIME_COLS:
        transit[col] = pd.to_datetime(transit[col])

    df = (transit
          .merge(crew[["crew_id", "rank", "base_location"]], on="crew_id", how="left")
          .merge(vehicles[["vehicle_id", "vehicle_type", "capacity"]], on="vehicle_id", how="left")
          .merge(flights[["flight_id", "destination"]], on="flight_id", how="left"))

    encoders = {}
    for col in CATEGORICAL_COLS:
        le = LabelEncoder()
        df[col + "_enc"] = le.fit_transform(df[col])
        encoders[col] = le

    df["delay_binary"] = df["delay_risk_class"].isin(["HIGH", "CRITICAL"]).astype(int)

    train_df = df[df["split"] == "train"].reset_index(drop=True)
    val_df = df[df["split"] == "val"].reset_index(drop=True)
    test_df = df[df["split"] == "test"].reset_index(drop=True)

    return train_df, val_df, test_df, encoders


def encode_new_record(record: dict, encoders: dict) -> list:
    """
    Encodes a single new transit record (e.g. from an API request) into
    the feature vector order the model expects. `record` must contain
    all FEATURE_COLS' raw equivalents (corridor, rank, etc. as strings,
    not yet encoded) plus the numeric fields directly.

    Raises ValueError if a categorical value wasn't seen during training
    (LabelEncoder can't encode unseen categories) — the caller should
    catch this and return a clear error rather than crash.
    """
    row = dict(record)
    for col in CATEGORICAL_COLS:
        le = encoders[col]
        if record[col] not in le.classes_:
            raise ValueError(f"Unseen value for '{col}': {record[col]!r}")
        row[col + "_enc"] = le.transform([record[col]])[0]

    return [row[c] for c in FEATURE_COLS]


if __name__ == "__main__":
    train_df, val_df, test_df, encoders = load_and_preprocess("data/output")
    print(f"train={len(train_df)} val={len(val_df)} test={len(test_df)}")
    print(f"Delay rate (train): {train_df['delay_binary'].mean():.3f}")
