"""
Scoring service: turns transits stored in PostgreSQL into delay-risk scores,
stores every score, and raises an alert when the score reaches the threshold.

Only information known BEFORE the trip is used as model input (time, route,
weather, congestion, crew rank, vehicle, destination). The recorded outcome
columns (delay_minutes, delay_risk_class) are never read as features.
"""

import os
from typing import Dict, List

import joblib
import numpy as np
from psycopg2.extras import execute_values

from ml.preprocessing.load_data import encode_new_record

from .config import get_alert_threshold, get_model_path
from .db import fetch_all


class ModelUnavailable(Exception):
    """The model file is missing or cannot be loaded."""


_cache: Dict[str, tuple] = {}


def load_bundle():
    """Loads {model, encoders, params}. Reloads automatically if the file changes."""
    path = get_model_path()
    if not os.path.exists(path):
        raise ModelUnavailable(
            f"Model not found at '{path}'. Run ml/training/train_xgboost.py first to produce it.")
    mtime = os.path.getmtime(path)
    hit = _cache.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        bundle = joblib.load(path)
        bundle["model"], bundle["encoders"]  # noqa: B018 - shape check
    except Exception as e:  # corrupt or wrong file
        raise ModelUnavailable(f"Model file at '{path}' could not be loaded: {e}") from e
    _cache[path] = (mtime, bundle)
    return bundle


def model_version() -> str:
    return os.path.splitext(os.path.basename(get_model_path()))[0]


def risk_level(p: float) -> str:
    if p < 0.3:
        return "LOW"
    if p < 0.5:
        return "MEDIUM"
    if p < 0.75:
        return "HIGH"
    return "CRITICAL"


FEATURE_SQL = """
SELECT t.transit_id,
       t.is_weekday::int AS is_weekday, t.is_rush_hour::int AS is_rush_hour,
       t.weather_flag::int AS weather_flag,
       t.traffic_congestion_index::float AS traffic_congestion_index,
       t.historical_avg_delay_min::float AS historical_avg_delay_min,
       t.distance_km::float AS distance_km, t.hour_of_day, t.day_of_week,
       v.capacity, t.corridor, c.rank, c.base_location, v.vehicle_type, f.destination
FROM transit_events t
JOIN crew_profiles c    ON c.crew_id = t.crew_id
JOIN vehicles v         ON v.vehicle_id = t.vehicle_id
JOIN flight_schedules f ON f.flight_id = t.flight_id
WHERE t.transit_id = ANY(%s)
"""


def score_transits(conn, transit_ids: List[int]) -> dict:
    """
    Scores the given transits, stores predictions, and creates/updates/closes alerts.

    Returns {"results": [...], "not_found": [...], "failed": [...]}.
    Raises ModelUnavailable if the model can't be loaded.
    """
    bundle = load_bundle()
    model, encoders = bundle["model"], bundle["encoders"]
    threshold = get_alert_threshold()
    version = model_version()

    ids = sorted(set(transit_ids))
    rows = {r["transit_id"]: r for r in fetch_all(conn, FEATURE_SQL, (ids,))}
    not_found = [i for i in ids if i not in rows]

    ok_ids, vectors, failed = [], [], []
    for tid in ids:
        if tid not in rows:
            continue
        try:
            vectors.append(encode_new_record(rows[tid], encoders))
            ok_ids.append(tid)
        except ValueError as e:
            failed.append({"transit_id": tid, "reason": str(e)})

    results = []
    if ok_ids:
        probs = model.predict_proba(np.asarray(vectors, dtype=float))[:, 1]
        for tid, p in zip(ok_ids, probs):
            p = round(float(p), 4)
            results.append({"transit_id": tid, "delay_probability": p,
                            "predicted_delayed": p >= threshold, "risk_level": risk_level(p),
                            "alert_raised": p >= threshold})

        with conn.cursor() as cur:
            execute_values(cur, """
                INSERT INTO predictions (transit_id, delay_probability, predicted_delayed, risk_level, model_version)
                VALUES %s
                ON CONFLICT (transit_id) DO UPDATE SET
                    delay_probability = EXCLUDED.delay_probability,
                    predicted_delayed = EXCLUDED.predicted_delayed,
                    risk_level = EXCLUDED.risk_level,
                    model_version = EXCLUDED.model_version,
                    scored_at = NOW()
            """, [(r["transit_id"], r["delay_probability"], r["predicted_delayed"],
                   r["risk_level"], version) for r in results])

            raised = [r for r in results if r["alert_raised"]]
            if raised:
                # Re-scoring updates the live alert; a dispatcher's "resolved" is left alone.
                execute_values(cur, """
                    INSERT INTO alerts (transit_id, alert_type, severity, generated_at, resolved,
                                        delay_probability, source, model_version)
                    VALUES %s
                    ON CONFLICT (transit_id) WHERE source = 'model' DO UPDATE SET
                        severity = EXCLUDED.severity,
                        delay_probability = EXCLUDED.delay_probability,
                        model_version = EXCLUDED.model_version,
                        generated_at = NOW()
                """, [(r["transit_id"], "DELAY_WARNING", r["risk_level"], False,
                       r["delay_probability"], "model", version) for r in raised],
                    template="(%s, %s, %s, NOW(), %s, %s, %s, %s)")

            # A transit that no longer reaches the threshold must not keep a stale open alert.
            cleared = [r["transit_id"] for r in results if not r["alert_raised"]]
            if cleared:
                cur.execute("""UPDATE alerts SET resolved = TRUE, resolved_at = NOW()
                               WHERE source = 'model' AND resolved = FALSE AND transit_id = ANY(%s)""",
                            (cleared,))

    return {"results": results, "not_found": not_found, "failed": failed}
