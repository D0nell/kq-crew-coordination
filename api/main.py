"""
KQ Crew Coordination — Prediction API

Serves the trained XGBoost delay-risk model. Loads the model + encoders
bundle saved by ml/training/train_xgboost.py and exposes a single
prediction endpoint.

Run locally:
    uvicorn api.main:app --reload --port 8000

Then visit http://127.0.0.1:8000/docs for interactive API docs (FastAPI
generates this automatically from the Pydantic models below).
"""

import os
import sys

import joblib
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ml.preprocessing.load_data import FEATURE_COLS, encode_new_record

MODEL_PATH = os.environ.get("MODEL_PATH", "models/xgb_final_v1.pkl")

app = FastAPI(
    title="KQ Crew Coordination — Delay Risk API",
    description="Predicts whether a crew transit is likely to be delayed, "
                 "given time, route, weather, and crew/vehicle context.",
    version="0.1.0",
)

_bundle = None  # loaded lazily on first request, see get_bundle()


def get_bundle():
    global _bundle
    if _bundle is None:
        if not os.path.exists(MODEL_PATH):
            raise HTTPException(
                status_code=503,
                detail=f"Model not found at '{MODEL_PATH}'. Run "
                       f"ml/training/train_xgboost.py first to produce it."
            )
        _bundle = joblib.load(MODEL_PATH)
    return _bundle


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


@app.get("/")
def root():
    return {"status": "ok", "service": "KQ Crew Coordination Delay Risk API"}


@app.get("/health")
def health():
    """Reports whether the model is loaded, without triggering a prediction."""
    model_exists = os.path.exists(MODEL_PATH)
    return {"model_path": MODEL_PATH, "model_file_found": model_exists}


@app.post("/predict-delay-risk", response_model=PredictionResponse)
def predict_delay_risk(request: TransitRequest):
    bundle = get_bundle()
    model = bundle["model"]
    encoders = bundle["encoders"]

    try:
        features = encode_new_record(request.model_dump(), encoders)
    except ValueError as e:
        # Raised by encode_new_record when a categorical value (e.g. an
        # unrecognized corridor name) wasn't seen during training.
        raise HTTPException(status_code=422, detail=str(e))

    proba = model.predict_proba([features])[0][1]  # P(delayed)
    delayed = bool(proba >= 0.5)

    if proba < 0.3:
        risk_level = "LOW"
    elif proba < 0.5:
        risk_level = "MEDIUM"
    elif proba < 0.75:
        risk_level = "HIGH"
    else:
        risk_level = "CRITICAL"

    return PredictionResponse(
        delayed=delayed,
        delay_probability=round(float(proba), 4),
        risk_level=risk_level,
    )