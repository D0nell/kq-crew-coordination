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
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel, Field, PositiveInt, field_validator

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ml.preprocessing.load_data import CATEGORICAL_COLS, encode_new_record  # noqa: E402

from . import scoring  # noqa: E402
from .config import (  # noqa: E402
    get_alert_threshold, get_model_path,
    get_session_secret, session_https_only,
)
from .auth import authenticate_user, get_current_user, require_dispatcher  # noqa: E402
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

app.add_middleware(
    SessionMiddleware,
    secret_key=get_session_secret(),
    session_cookie="kq_session",
    max_age=60 * 60 * 8,
    same_site="lax",
    https_only=session_https_only(),
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


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
class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=160)
    password: str = Field(..., min_length=1, max_length=256)


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


@app.get("/login", include_in_schema=False)
def login_page(request: Request):
    try:
        user = get_current_user(request)
        destination = "/dashboard" if user["role"] == "DISPATCHER" else "/predict"
        return RedirectResponse(destination, status_code=303)
    except HTTPException:
        return FileResponse(os.path.join(STATIC_DIR, "login.html"), media_type="text/html")


@app.post("/login")
def login(body: LoginRequest, request: Request):
    user = authenticate_user(body.email, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    request.session.clear()
    request.session["user_id"] = user["user_id"]
    destination = "/dashboard" if user["role"] == "DISPATCHER" else "/predict"
    return {"ok": True, "role": user["role"], "redirect": destination}


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@app.get("/api/me")
def current_account(user: dict = Depends(get_current_user)):
    """Return the identity of the authenticated account."""
    return {
        "user_id": user["user_id"],
        "full_name": user["full_name"],
        "role": user["role"],
        "email": user["email"],
    }


@app.get("/dashboard", include_in_schema=False)
def dashboard(request: Request):
    try:
        user = get_current_user(request)
    except HTTPException:
        return RedirectResponse("/login", status_code=303)
    if user["role"] != "DISPATCHER":
        return RedirectResponse("/predict", status_code=303)
    return FileResponse(os.path.join(STATIC_DIR, "dashboard.html"), media_type="text/html")


@app.get("/predict", include_in_schema=False)
def predict_page(request: Request):
    try:
        get_current_user(request)
    except HTTPException:
        return RedirectResponse("/login", status_code=303)
    return FileResponse(os.path.join(STATIC_DIR, "predict.html"), media_type="text/html")


@app.get("/alerts", include_in_schema=False)
def alerts_page(request: Request):
    try:
        get_current_user(request)
    except HTTPException:
        return RedirectResponse("/login", status_code=303)
    return FileResponse(os.path.join(STATIC_DIR, "alerts.html"), media_type="text/html")


@app.get("/api/options", dependencies=[Depends(get_current_user)])
def options():
    """
    The exact category values the model was trained on, read from its encoders, so the
    prediction form's dropdowns can never drift from what the model accepts.
    """
    encoders = scoring.load_bundle()["encoders"]
    return {col: [str(c) for c in encoders[col].classes_] for col in CATEGORICAL_COLS}


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


@app.post("/predict-delay-risk", response_model=PredictionResponse, dependencies=[Depends(get_current_user)])
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


@app.get("/api/transits", dependencies=[Depends(require_dispatcher)])
def list_transits(
    split: Literal["train", "val", "test"] = "test",
    corridor: Optional[Literal[tuple(CORRIDORS)]] = None,  # type: ignore[valid-type]
    status: Literal["all", "scored", "unscored", "alert"] = "all",
    risk: Literal["all", "critical"] = "all",
    sort: Literal["pickup_time", "probability"] = "pickup_time",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    q: Optional[str] = Query(None, max_length=20),
):
    """
    Transits for the dispatcher. Defaults to the held-out TEST split so a live demo
    never scores data the model was trained on. 'actual_*' fields are the recorded
    outcome, shown for replay evaluation only.

    risk=critical keeps only scored transits whose model risk is HIGH or CRITICAL.
    sort=probability orders by delay_probability DESC (unscored/NULL last); the
    default sort=pickup_time preserves prior behaviour.
    """
    where, params = ["t.split = %(split)s"], {"split": split, "limit": limit, "offset": offset}
    if corridor:
        where.append("t.corridor = %(corridor)s")
        params["corridor"] = corridor
    if q and q.strip():
        term = q.strip().lstrip("#")
        if not term.isdigit():
            return {"total": 0, "limit": limit, "offset": offset, "items": []}
        where.append("t.transit_id = %(q)s")
        params["q"] = int(term)
    if status == "scored":
        where.append("p.transit_id IS NOT NULL")
    elif status == "unscored":
        where.append("p.transit_id IS NULL")
    elif status == "alert":
        where.append("""EXISTS (SELECT 1 FROM alerts a WHERE a.transit_id = t.transit_id
                         AND a.source = 'model' AND a.resolved = FALSE)""")
    if risk == "critical":
        where.append("p.risk_level IN ('HIGH', 'CRITICAL')")
    clause = " WHERE " + " AND ".join(where)
    if sort == "probability":
        order_by = ("(p.delay_probability IS NULL) ASC, p.delay_probability DESC, "
                    "t.scheduled_pickup_time, t.transit_id")
    else:
        order_by = "t.scheduled_pickup_time, t.transit_id"
    with get_conn() as conn:
        total = fetch_one(conn, "SELECT COUNT(*) AS n FROM transit_events t "
                                "LEFT JOIN predictions p ON p.transit_id = t.transit_id" + clause, params)["n"]
        items = fetch_all(conn, TRANSIT_SELECT + clause +
                          " ORDER BY " + order_by + " LIMIT %(limit)s OFFSET %(offset)s", params)
    return {"total": total, "limit": limit, "offset": offset, "items": items}


@app.post("/api/transits/score-batch", dependencies=[Depends(require_dispatcher)])
def score_batch(body: BatchScoreRequest):
    """Scores up to 200 transits. Unknown ids are reported, not fatal."""
    with get_conn() as conn:
        out = scoring.score_transits(conn, body.transit_ids)
    out["scored"] = len(out["results"])
    out["alerts_raised"] = sum(1 for r in out["results"] if r["alert_raised"])
    return out


@app.post("/api/transits/{transit_id}/score", dependencies=[Depends(require_dispatcher)])
def score_one(transit_id: PositiveInt):
    with get_conn() as conn:
        out = scoring.score_transits(conn, [transit_id])
    if out["not_found"]:
        raise HTTPException(status_code=404, detail=f"Transit {transit_id} not found")
    if out["failed"]:
        raise HTTPException(status_code=422, detail=out["failed"][0]["reason"])
    return out["results"][0]


@app.get("/api/alerts", dependencies=[Depends(require_dispatcher)])
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


@app.patch("/api/alerts/{alert_id}/resolve", dependencies=[Depends(require_dispatcher)])
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


class BulkResolveRequest(BaseModel):
    """Body for POST /api/alerts/bulk-resolve.

    A non-empty, bounded, unique list of positive model alert ids. Validation is
    defensive: the server trusts neither the client's view of which alerts are
    open, nor that the ids even exist.
    """

    alert_ids: List[PositiveInt] = Field(
        ..., min_length=1, max_length=500, description="Unique model alert ids to resolve."
    )

    @field_validator("alert_ids")
    @classmethod
    def _unique_ids(cls, v: List[int]) -> List[int]:
        if len(set(v)) != len(v):
            raise ValueError("alert_ids must be unique")
        return v


@app.post("/api/alerts/bulk-resolve", dependencies=[Depends(require_dispatcher)])
def bulk_resolve(body: BulkResolveRequest):
    """Mark several model alerts resolved in one request (one transaction).

    Each alert_id is re-validated against the database, so the client's selection
    is never trusted:

      * an open model alert is marked resolved. resolved_at is set only where a
        row is newly resolved; already-resolved rows are left untouched;
      * an already-resolved model alert is confirmed without touching
        resolved_at;
      * an unknown id is reported as not_found;
      * a row that exists but is not a model alert (e.g. historical) is reported
        as ineligible and never modified.

    Expected per-id outcomes are always returned, so an already-resolved or
    unknown id never aborts the batch. An unexpected database error rolls the
    whole batch back (get_conn rolls back on exception).
    """
    alert_ids = sorted(set(body.alert_ids))
    resolved, already_resolved, not_found, ineligible, failed = [], [], [], [], []

    with get_conn() as conn:
        for alert_id in alert_ids:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """UPDATE alerts
                           SET resolved = TRUE, resolved_at = NOW()
                           WHERE alert_id = %s AND source = 'model' AND resolved = FALSE
                           RETURNING alert_id""",
                        (alert_id,),
                    )
                    if cur.fetchone():
                        resolved.append(alert_id)
                        continue

                # No row was updated. Classify against authoritative state, which is
                # the only place that decides whether this id is ours to touch.
                row = fetch_one(
                    conn,
                    "SELECT source, resolved FROM alerts WHERE alert_id = %s",
                    (alert_id,),
                )
                if row is None:
                    not_found.append(alert_id)
                elif row["source"] != "model":
                    ineligible.append(alert_id)
                elif row["resolved"]:
                    already_resolved.append(alert_id)
                else:
                    # An open model alert that the conditional UPDATE did not match:
                    # inconsistent state on a single connection. Surface it instead of
                    # guessing.
                    failed.append(alert_id)
            except Exception as exc:  # pragma: no cover - unexpected DB error
                failed.append(alert_id)
                # get_conn rolls back the whole batch when this propagates.
                raise HTTPException(
                    status_code=503,
                    detail=f"bulk resolve failed for alert {alert_id}: {exc}",
                ) from exc

    return {
        "counts": {
            "total": len(alert_ids),
            "resolved": len(resolved),
            "already_resolved": len(already_resolved),
            "not_found": len(not_found),
            "ineligible": len(ineligible),
            "failed": len(failed),
        },
        "resolved_alert_ids": resolved,
        "already_resolved_alert_ids": already_resolved,
        "not_found_alert_ids": not_found,
        "ineligible_alert_ids": ineligible,
        "failed_alert_ids": failed,
        "successfully_affected_alert_ids": resolved + already_resolved,
    }


@app.get("/api/summary", dependencies=[Depends(require_dispatcher)])
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
