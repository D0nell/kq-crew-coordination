"""
KQ Crew Coordination — Delay Risk API (Sprint II)

Core workflow:
    transits in PostgreSQL -> features -> XGBoost score -> stored prediction
    -> alert when score >= threshold -> dispatcher dashboard -> resolve alert

Run from the repo root:
    uvicorn api.main:app --reload --port 8000

    http://127.0.0.1:8000/dashboard   dispatcher dashboard
    http://127.0.0.1:8000/docs        interactive API documentation
"""

import os
import sys
from typing import List, Literal, Optional

import psycopg2
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, PositiveInt

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ml.preprocessing.load_data import encode_new_record  # noqa: E402

from . import scoring  # noqa: E402
from .config import get_alert_threshold, get_model_path  # noqa: E402
from .db import fetch_all, fetch_one, get_conn  # noqa: E402

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
CORRIDORS = ["Mombasa Rd - JKIA", "Westlands - JKIA", "Embakasi - JKIA",
             "KQ Training Centre - JKIA", "Medical Centre - JKIA", "South B - JKIA"]

app = FastAPI(
    title="KQ Crew Coordination — Delay Risk API",
    description="Scores crew transits for delay risk, stores the scores, and raises "
                 "alerts for dispatchers.",
    version="0.2.0",
)


# --------------------------------------------------------------------------
# Failure handling: a missing model or an unreachable database is a 503
# with a clear message, never an unexplained 500.
# --------------------------------------------------------------------------
@app.exception_handler(scoring.ModelUnavailable)
async def model_unavailable_handler(request: Request, exc: scoring.ModelUnavailable):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(psycopg2.OperationalError)
async def db_unreachable_handler(request: Request, exc: psycopg2.OperationalError):
    return JSONResponse(status_code=503, content={
        "detail": "Database unreachable. Check that PostgreSQL is running and DATABASE_URL is correct."})


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------
class TransitRequest(BaseModel):
    """Raw inputs for one transit — the API encodes categoricals internally."""
    is_weekday: int = Field(..., ge=0, le=1)
    is_rush_hour: int = Field(..., ge=0, le=1)
    weather_flag: int = Field(..., ge=0, le=1)
    traffic_congestion_index: float = Field(..., ge=0, le=1)
    historical_avg_delay_min: float = Field(..., ge=0)
    distance_km: float = Field(..., gt=0)
    hour_of_day: int = Field(..., ge=0, le=23)
    day_of_week: int = Field(..., ge=0, le=6, description="0=Monday .. 6=Sunday")
    capacity: int = Field(..., gt=0)
    corridor: str = Field(..., examples=["Mombasa Rd - JKIA"])
    rank: str = Field(..., examples=["Captain"])
    base_location: str = Field(..., examples=["JKIA Base"])
    vehicle_type: str = Field(..., examples=["Crew Van"])
    destination: str = Field(..., examples=["LHR"])


class PredictionResponse(BaseModel):
    delayed: bool
    delay_probability: float
    risk_level: str


class BatchScoreRequest(BaseModel):
    transit_ids: List[PositiveInt] = Field(..., min_length=1, max_length=200)


# --------------------------------------------------------------------------
# Basic endpoints
# --------------------------------------------------------------------------
@app.get("/")
def root():
    return {"status": "ok", "service": "KQ Crew Coordination Delay Risk API",
            "dashboard": "/dashboard", "docs": "/docs"}


@app.get("/dashboard", include_in_schema=False)
def dashboard():
    return FileResponse(os.path.join(STATIC_DIR, "dashboard.html"), media_type="text/html")


@app.get("/health")
def health():
    """Reports model and database status without scoring anything."""
    model_path = get_model_path()
    info = {"model_path": model_path, "model_file_found": os.path.exists(model_path),
            "alert_threshold": get_alert_threshold()}
    try:
        with get_conn() as conn:
            fetch_one(conn, "SELECT 1 AS ok")
        info["database"] = "ok"
    except psycopg2.OperationalError:
        info["database"] = "unreachable"
    info["status"] = "ok" if info["model_file_found"] and info["database"] == "ok" else "degraded"
    return info


@app.post("/predict-delay-risk", response_model=PredictionResponse)
def predict_delay_risk(request: TransitRequest):
    """Stateless scoring of a transit described in the request body (no database)."""
    bundle = scoring.load_bundle()
    try:
        features = encode_new_record(request.model_dump(), bundle["encoders"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    p = round(float(bundle["model"].predict_proba([features])[0][1]), 4)
    return PredictionResponse(delayed=p >= get_alert_threshold(), delay_probability=p,
                              risk_level=scoring.risk_level(p))


# --------------------------------------------------------------------------
# Dispatcher workflow: list -> score -> alerts -> resolve
# --------------------------------------------------------------------------
TRANSIT_SELECT = """
SELECT t.transit_id, t.corridor, t.scheduled_pickup_time, t.split,
       c.rank, v.vehicle_type, f.destination,
       t.traffic_congestion_index::float AS traffic_congestion_index,
       t.weather_flag, t.is_rush_hour,
       t.delay_minutes::float AS actual_delay_minutes, t.delay_risk_class AS actual_risk_class,
       p.delay_probability::float AS delay_probability, p.predicted_delayed, p.risk_level, p.scored_at,
       EXISTS (SELECT 1 FROM alerts a WHERE a.transit_id = t.transit_id
               AND a.source = 'model' AND a.resolved = FALSE) AS open_alert
FROM transit_events t
JOIN crew_profiles c    ON c.crew_id = t.crew_id
JOIN vehicles v         ON v.vehicle_id = t.vehicle_id
JOIN flight_schedules f ON f.flight_id = t.flight_id
LEFT JOIN predictions p ON p.transit_id = t.transit_id
"""


@app.get("/api/transits")
def list_transits(
    split: Literal["train", "val", "test"] = "test",
    corridor: Optional[Literal[tuple(CORRIDORS)]] = None,  # type: ignore[valid-type]
    status: Literal["all", "scored", "unscored", "alert"] = "all",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """
    Transits for the dispatcher. Defaults to the held-out TEST split so a live demo
    never scores data the model was trained on. 'actual_*' fields are the recorded
    outcome, shown for replay evaluation only.
    """
    where, params = ["t.split = %(split)s"], {"split": split, "limit": limit, "offset": offset}
    if corridor:
        where.append("t.corridor = %(corridor)s")
        params["corridor"] = corridor
    if status == "scored":
        where.append("p.transit_id IS NOT NULL")
    elif status == "unscored":
        where.append("p.transit_id IS NULL")
    elif status == "alert":
        where.append("""EXISTS (SELECT 1 FROM alerts a WHERE a.transit_id = t.transit_id
                         AND a.source = 'model' AND a.resolved = FALSE)""")
    clause = " WHERE " + " AND ".join(where)
    with get_conn() as conn:
        total = fetch_one(conn, "SELECT COUNT(*) AS n FROM transit_events t "
                                "LEFT JOIN predictions p ON p.transit_id = t.transit_id" + clause, params)["n"]
        items = fetch_all(conn, TRANSIT_SELECT + clause +
                          " ORDER BY t.scheduled_pickup_time, t.transit_id LIMIT %(limit)s OFFSET %(offset)s", params)
    return {"total": total, "limit": limit, "offset": offset, "items": items}


@app.post("/api/transits/score-batch")
def score_batch(body: BatchScoreRequest):
    """Scores up to 200 transits. Unknown ids are reported, not fatal."""
    with get_conn() as conn:
        out = scoring.score_transits(conn, body.transit_ids)
    out["scored"] = len(out["results"])
    out["alerts_raised"] = sum(1 for r in out["results"] if r["alert_raised"])
    return out


@app.post("/api/transits/{transit_id}/score")
def score_one(transit_id: PositiveInt):
    with get_conn() as conn:
        out = scoring.score_transits(conn, [transit_id])
    if out["not_found"]:
        raise HTTPException(status_code=404, detail=f"Transit {transit_id} not found")
    if out["failed"]:
        raise HTTPException(status_code=422, detail=out["failed"][0]["reason"])
    return out["results"][0]


@app.get("/api/alerts")
def list_alerts(status: Literal["open", "resolved", "all"] = "open",
                limit: int = Query(100, ge=1, le=500)):
    where = {"open": "AND a.resolved = FALSE", "resolved": "AND a.resolved = TRUE", "all": ""}[status]
    with get_conn() as conn:
        items = fetch_all(conn, f"""
            SELECT a.alert_id, a.transit_id, a.alert_type, a.severity,
                   a.delay_probability::float AS delay_probability, a.generated_at,
                   a.resolved, a.resolved_at, a.model_version,
                   t.corridor, t.scheduled_pickup_time, c.rank, f.destination
            FROM alerts a
            JOIN transit_events t   ON t.transit_id = a.transit_id
            JOIN crew_profiles c    ON c.crew_id = t.crew_id
            JOIN flight_schedules f ON f.flight_id = t.flight_id
            WHERE a.source = 'model' {where}
            ORDER BY a.resolved, a.delay_probability DESC, a.alert_id
            LIMIT %s""", (limit,))
    return {"count": len(items), "items": items}


@app.patch("/api/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: PositiveInt):
    """Marks a model alert as resolved. Resolving twice is harmless."""
    with get_conn() as conn:
        row = fetch_one(conn, """
            UPDATE alerts SET resolved = TRUE, resolved_at = COALESCE(resolved_at, NOW())
            WHERE alert_id = %s AND source = 'model'
            RETURNING alert_id, transit_id, resolved, resolved_at""", (alert_id,))
    if row is None:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    return row


@app.get("/api/summary")
def summary():
    """
    Dashboard totals plus replay evaluation: of the held-out TEST transits that have
    been scored, how do predictions compare with the recorded outcome?
    """
    with get_conn() as conn:
        counts = fetch_one(conn, """
            SELECT (SELECT COUNT(*) FROM transit_events WHERE split = 'test') AS test_transits,
                   (SELECT COUNT(*) FROM predictions) AS scored,
                   (SELECT COUNT(*) FROM alerts WHERE source = 'model' AND resolved = FALSE) AS open_alerts,
                   (SELECT COUNT(*) FROM alerts WHERE source = 'model') AS total_alerts""")
        m = fetch_one(conn, """
            SELECT COUNT(*)::int AS n,
                   COALESCE(SUM((p.predicted_delayed AND a.actual)::int), 0)::int AS tp,
                   COALESCE(SUM((p.predicted_delayed AND NOT a.actual)::int), 0)::int AS fp,
                   COALESCE(SUM((NOT p.predicted_delayed AND a.actual)::int), 0)::int AS fn,
                   COALESCE(SUM((NOT p.predicted_delayed AND NOT a.actual)::int), 0)::int AS tn
            FROM predictions p
            JOIN (SELECT transit_id, delay_risk_class IN ('HIGH','CRITICAL') AS actual
                  FROM transit_events WHERE split = 'test') a ON a.transit_id = p.transit_id""")
    tp, fp, fn = m["tp"], m["fp"], m["fn"]
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else None
    rnd = lambda x: None if x is None else round(x, 4)  # noqa: E731
    return {**counts, "alert_threshold": get_alert_threshold(), "model_version": scoring.model_version(),
            "replay": {"scored_test_transits": m["n"], "tp": tp, "fp": fp, "fn": fn, "tn": m["tn"],
                       "precision": rnd(precision), "recall": rnd(recall), "f1": rnd(f1)}}
