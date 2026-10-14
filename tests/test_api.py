"""API behaviour, invalid input and failure conditions (TC-07 to TC-31)."""

import os

import numpy as np
import pytest
from sklearn.metrics import f1_score, precision_score, recall_score

from conftest import first_ids


# ------------------------------------------------------------------ expected behaviour
def test_health_ok(client, actual):
    """TC-07 | GET /health with model and database available | status ok, database ok, model_file_found true"""
    r = client.get("/health").json()
    assert r["status"] == "ok" and r["database"] == "ok" and r["model_file_found"] is True
    actual(f"status={r['status']}, database={r['database']}, threshold={r['alert_threshold']}")


def test_list_defaults_to_test_split(client, q, actual):
    """TC-08 | GET /api/transits with no filters | only held-out test-split transits, in pickup-time order"""
    r = client.get("/api/transits?limit=200").json()
    assert r["total"] == q("SELECT COUNT(*) n FROM transit_events WHERE split='test'")[0]["n"]
    ids = [i["transit_id"] for i in r["items"]]
    split = {x["transit_id"]: x["split"] for x in q("SELECT transit_id, split FROM transit_events WHERE transit_id = ANY(%s)", (ids,))}
    assert set(split.values()) == {"test"}
    times = [i["scheduled_pickup_time"] for i in r["items"]]
    assert times == sorted(times)
    actual(f"{r['total']} test transits, all split=test, sorted by pickup time")


def test_filters_and_pagination(client, actual):
    """TC-09 | GET /api/transits with corridor filter and limit/offset | only that corridor, pages do not overlap"""
    first = client.get("/api/transits?limit=200").json()["items"]
    corridor = first[0]["corridor"]
    r = client.get("/api/transits", params={"corridor": corridor, "limit": 5}).json()
    assert r["items"] and all(i["corridor"] == corridor for i in r["items"])
    p1 = client.get("/api/transits?limit=10&offset=0").json()["items"]
    p2 = client.get("/api/transits?limit=10&offset=10").json()["items"]
    assert not {i["transit_id"] for i in p1} & {i["transit_id"] for i in p2}
    actual(f"corridor='{corridor}' returned {len(r['items'])} rows; pages 1 and 2 are disjoint")


def test_score_one(client, q, actual):
    """TC-10 | POST /api/transits/{id}/score for a real transit | probability in 0..1, risk level set, prediction stored"""
    tid = first_ids(client, 1)[0]
    r = client.post(f"/api/transits/{tid}/score")
    assert r.status_code == 200
    body = r.json()
    assert 0 <= body["delay_probability"] <= 1
    assert body["risk_level"] in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    row = q("SELECT * FROM predictions WHERE transit_id=%s", (tid,))
    assert len(row) == 1 and float(row[0]["delay_probability"]) == pytest.approx(body["delay_probability"])
    actual(f"transit {tid}: p={body['delay_probability']}, {body['risk_level']}, stored")


def test_alert_iff_probability_reaches_threshold(client, q, actual):
    """TC-11 | Score 60 transits at the default 0.5 threshold | an open model alert exists exactly when p >= 0.5"""
    ids = first_ids(client, 60)
    client.post("/api/transits/score-batch", json={"transit_ids": ids})
    preds = {r["transit_id"]: float(r["delay_probability"]) for r in q("SELECT transit_id, delay_probability FROM predictions")}
    alerts = {r["transit_id"] for r in q("SELECT transit_id FROM alerts WHERE source='model' AND resolved=FALSE")}
    assert alerts == {t for t, p in preds.items() if p >= 0.5}
    actual(f"{len(alerts)} alerts for {len(preds)} scored transits; alert set equals {{p >= 0.5}}")


def test_rescore_is_idempotent(client, q, actual):
    """TC-12 | Score the same transits twice | no duplicate predictions or alerts"""
    ids = first_ids(client, 40)
    for _ in range(2):
        client.post("/api/transits/score-batch", json={"transit_ids": ids})
    assert q("SELECT COUNT(*) n FROM predictions")[0]["n"] == 40
    assert q("""SELECT COUNT(*) n FROM (SELECT transit_id FROM alerts WHERE source='model'
                GROUP BY transit_id HAVING COUNT(*) > 1) d""")[0]["n"] == 0
    actual("40 predictions and no duplicated model alerts after two passes")


def test_rescore_below_threshold_clears_stale_alert(client, q, monkeypatch, actual):
    """TC-13 | A transit with an open alert is re-scored with a higher threshold | the stale alert is auto-resolved"""
    ids = first_ids(client, 60)
    client.post("/api/transits/score-batch", json={"transit_ids": ids})
    assert q("SELECT COUNT(*) n FROM alerts WHERE source='model' AND resolved=FALSE")[0]["n"] > 0
    monkeypatch.setenv("ALERT_THRESHOLD", "0.99")
    client.post("/api/transits/score-batch", json={"transit_ids": ids})
    left = q("SELECT COUNT(*) n FROM alerts WHERE source='model' AND resolved=FALSE")[0]["n"]
    assert left == 0
    actual("Open alerts before: >0, after re-score at threshold 0.99: 0")


def test_batch_counts(client, actual):
    """TC-14 | POST score-batch with 25 ids | scored=25 and alerts_raised equals the number of results flagged"""
    ids = first_ids(client, 25)
    b = client.post("/api/transits/score-batch", json={"transit_ids": ids}).json()
    assert b["scored"] == 25 and b["alerts_raised"] == sum(r["alert_raised"] for r in b["results"])
    assert b["not_found"] == [] and b["failed"] == []
    actual(f"scored={b['scored']}, alerts_raised={b['alerts_raised']}")


def test_open_alerts_ordered_by_probability(client, actual):
    """TC-15 | GET /api/alerts after scoring | open alerts only, highest probability first"""
    client.post("/api/transits/score-batch", json={"transit_ids": first_ids(client, 80)})
    items = client.get("/api/alerts").json()["items"]
    assert items and all(not a["resolved"] for a in items)
    probs = [a["delay_probability"] for a in items]
    assert probs == sorted(probs, reverse=True)
    actual(f"{len(items)} open alerts, top p={probs[0]}")


def test_resolve_alert(client, actual):
    """TC-16 | PATCH /api/alerts/{id}/resolve on an open alert | alert resolved, timestamp set, removed from the open list"""
    client.post("/api/transits/score-batch", json={"transit_ids": first_ids(client, 40)})
    a = client.get("/api/alerts").json()["items"][0]
    r = client.patch(f"/api/alerts/{a['alert_id']}/resolve")
    assert r.status_code == 200 and r.json()["resolved"] and r.json()["resolved_at"]
    assert a["alert_id"] not in [x["alert_id"] for x in client.get("/api/alerts").json()["items"]]
    actual(f"alert {a['alert_id']} resolved and gone from open list")


def test_resolve_is_idempotent_and_survives_rescore(client, actual):
    """TC-17 | Resolve the same alert twice, then re-score its transit | both calls 200, original resolved_at kept, dispatcher decision not reopened"""
    ids = first_ids(client, 40)
    client.post("/api/transits/score-batch", json={"transit_ids": ids})
    a = client.get("/api/alerts").json()["items"][0]
    r1 = client.patch(f"/api/alerts/{a['alert_id']}/resolve").json()
    r2 = client.patch(f"/api/alerts/{a['alert_id']}/resolve").json()
    assert r1["resolved_at"] == r2["resolved_at"]
    client.post(f"/api/transits/{a['transit_id']}/score")
    open_ids = [x["alert_id"] for x in client.get("/api/alerts").json()["items"]]
    assert a["alert_id"] not in open_ids
    actual("Second resolve returned same resolved_at; re-score did not reopen the alert")


def test_summary_matches_independent_metrics(client, q, actual):
    """TC-18 | GET /api/summary replay metrics after scoring 120 test transits | precision, recall and F1 equal scikit-learn computed independently from the database"""
    client.post("/api/transits/score-batch", json={"transit_ids": first_ids(client, 120)})
    s = client.get("/api/summary").json()["replay"]
    rows = q("""SELECT p.predicted_delayed AS yhat, (t.delay_risk_class IN ('HIGH','CRITICAL')) AS y
                FROM predictions p JOIN transit_events t USING (transit_id) WHERE t.split='test'""")
    y = np.array([r["y"] for r in rows]); yh = np.array([r["yhat"] for r in rows])
    assert s["scored_test_transits"] == len(rows)
    assert s["precision"] == pytest.approx(precision_score(y, yh), abs=1e-4)
    assert s["recall"] == pytest.approx(recall_score(y, yh), abs=1e-4)
    assert s["f1"] == pytest.approx(f1_score(y, yh), abs=1e-4)
    actual(f"n={len(rows)}: P={s['precision']}, R={s['recall']}, F1={s['f1']} (matches scikit-learn)")


def test_no_outcome_columns_used_as_features(actual):
    """TC-19 | Leakage guard: the feature query used for scoring | contains no outcome columns (delay_minutes, delay_risk_class, actual_*, mobilization, alerts)"""
    from api.scoring import FEATURE_SQL
    from ml.preprocessing.load_data import FEATURE_COLS
    sql = FEATURE_SQL.lower()
    banned = ["delay_minutes", "delay_risk_class", "actual", "mobilization", "alerts", "split"]
    hits = [b for b in banned if b in sql]
    assert not hits, hits
    assert not set(FEATURE_COLS) & {"delay_minutes", "delay_risk_class"}
    actual("Feature SQL references none of: " + ", ".join(banned))


# ------------------------------------------------------------------ invalid input
def test_unknown_transit_404(client, actual):
    """TC-20 | Score a transit id that does not exist | 404 with a clear message, nothing stored"""
    r = client.post("/api/transits/99999999/score")
    assert r.status_code == 404 and "not found" in r.json()["detail"].lower()
    actual(f"404: {r.json()['detail']}")


@pytest.mark.parametrize("bad", ["abc", "0", "-5", "1.5"])
def test_bad_transit_id_422(client, bad, actual):
    """TC-21 | Score with a non-integer, zero or negative transit id | 422 validation error"""
    r = client.post(f"/api/transits/{bad}/score")
    assert r.status_code == 422
    actual("422 for ids abc, 0, -5, 1.5")


@pytest.mark.parametrize("body", [{}, {"transit_ids": []}, {"transit_ids": [0]}, {"transit_ids": ["x"]},
                                  {"transit_ids": list(range(1, 202))}])
def test_bad_batch_bodies_422(client, body, actual):
    """TC-22 | score-batch with a missing, empty, non-positive, non-numeric or 201-item list | 422 validation error"""
    assert client.post("/api/transits/score-batch", json=body).status_code == 422
    actual("422 for {}, [], [0], ['x'] and 201 ids")


def test_partial_batch_reports_unknown(client, actual):
    """TC-23 | Batch containing two real ids and one unknown id | real ones scored, unknown listed in not_found, request succeeds"""
    ids = first_ids(client, 2)
    b = client.post("/api/transits/score-batch", json={"transit_ids": ids + [99999999]})
    assert b.status_code == 200
    j = b.json()
    assert j["scored"] == 2 and j["not_found"] == [99999999]
    actual("scored=2, not_found=[99999999]")


def test_resolve_unknown_or_historical_alert_404(client, q, actual):
    """TC-24 | Resolve an unknown alert id, and a historical (non-model) alert | 404 for both; historical data is never modified"""
    assert client.patch("/api/alerts/99999999/resolve").status_code == 404
    hist = q("SELECT alert_id, resolved FROM alerts WHERE source='historical' LIMIT 1")
    assert hist, "dataset should contain historical alerts"
    assert client.patch(f"/api/alerts/{hist[0]['alert_id']}/resolve").status_code == 404
    after = q("SELECT resolved FROM alerts WHERE alert_id=%s", (hist[0]["alert_id"],))[0]["resolved"]
    assert after == hist[0]["resolved"]
    actual("404 for unknown id and for historical alert; historical row unchanged")


@pytest.mark.parametrize("url", ["/api/transits?limit=0", "/api/transits?limit=500", "/api/transits?offset=-1",
                                 "/api/transits?split=banana", "/api/transits?corridor=Nowhere",
                                 "/api/transits?status=weird", "/api/alerts?status=maybe"])
def test_bad_query_params_422(client, url, actual):
    """TC-25 | List endpoints with out-of-range or unknown query values | 422 validation error, not a 500"""
    assert client.get(url).status_code == 422
    actual("422 for limit=0, limit=500, offset=-1, split=banana, corridor=Nowhere, status=weird, alerts status=maybe")


def test_stateless_predict_validation(client, actual):
    """TC-26 | POST /predict-delay-risk with an out-of-range value, a missing field and an unseen category | 422 each time; a valid body returns a probability"""
    from api.scoring import load_bundle
    enc = load_bundle()["encoders"]
    good = {"is_weekday": 1, "is_rush_hour": 1, "weather_flag": 0, "traffic_congestion_index": 0.6,
            "historical_avg_delay_min": 12.0, "distance_km": 20.0, "hour_of_day": 8, "day_of_week": 1,
            "capacity": 14, **{k: str(enc[k].classes_[0]) for k in
                               ["corridor", "rank", "base_location", "vehicle_type", "destination"]}}
    ok = client.post("/predict-delay-risk", json=good)
    assert ok.status_code == 200 and 0 <= ok.json()["delay_probability"] <= 1
    assert client.post("/predict-delay-risk", json={**good, "traffic_congestion_index": 7}).status_code == 422
    assert client.post("/predict-delay-risk", json={k: v for k, v in good.items() if k != "rank"}).status_code == 422
    assert client.post("/predict-delay-risk", json={**good, "destination": "ZZZ"}).status_code == 422
    actual(f"valid body p={ok.json()['delay_probability']}; congestion=7, missing rank, destination=ZZZ all 422")


# ------------------------------------------------------------------ failure conditions
def test_missing_model_503(client, monkeypatch, tmp_path, actual):
    """TC-27 | Model file is missing | scoring returns 503 with an instruction to train the model; /health reports degraded"""
    monkeypatch.setenv("MODEL_PATH", str(tmp_path / "nope.pkl"))
    tid = first_ids(client, 1)[0]
    r = client.post(f"/api/transits/{tid}/score")
    assert r.status_code == 503 and "train" in r.json()["detail"].lower()
    h = client.get("/health").json()
    assert h["status"] == "degraded" and h["model_file_found"] is False
    actual("503: " + r.json()["detail"][:80])


def test_corrupt_model_503(client, monkeypatch, tmp_path, actual):
    """TC-28 | Model file exists but is corrupt | 503 saying the model could not be loaded, not a 500 crash"""
    bad = tmp_path / "bad.pkl"
    bad.write_bytes(b"this is not a model")
    monkeypatch.setenv("MODEL_PATH", str(bad))
    tid = first_ids(client, 1)[0]
    r = client.post(f"/api/transits/{tid}/score")
    assert r.status_code == 503 and "could not be loaded" in r.json()["detail"]
    actual("503: " + r.json()["detail"][:80])


def test_database_down_503(client, monkeypatch, actual):
    """TC-29 | PostgreSQL is unreachable | data endpoints return 503 'Database unreachable'; /health still answers with status degraded"""
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres:x@localhost:1/none")
    r = client.get("/api/transits")
    assert r.status_code == 503 and "unreachable" in r.json()["detail"].lower()
    h = client.get("/health")
    assert h.status_code == 200 and h.json()["status"] == "degraded" and h.json()["database"] == "unreachable"
    actual("/api/transits 503; /health 200 with database=unreachable")


def test_dashboard_and_root_served(client, actual):
    """TC-30 | GET /dashboard and GET / | dashboard HTML is served; root identifies the service"""
    d = client.get("/dashboard")
    assert d.status_code == 200 and "text/html" in d.headers["content-type"] and "<title>" in d.text
    assert client.get("/").status_code == 200
    actual("dashboard 200 text/html; root 200")


def test_unseen_category_fails_only_that_transit(client, q, actual):
    """TC-31 | One transit has a destination the model never saw | that transit is listed in 'failed' with a reason, the others in the batch still score"""
    ids = first_ids(client, 3)
    flight = q("SELECT flight_id, destination FROM transit_events JOIN flight_schedules USING (flight_id) WHERE transit_id=%s", (ids[0],))[0]
    q("UPDATE flight_schedules SET destination='ZZZ' WHERE flight_id=%s", (flight["flight_id"],))
    try:
        b = client.post("/api/transits/score-batch", json={"transit_ids": ids}).json()
    finally:
        q("UPDATE flight_schedules SET destination=%s WHERE flight_id=%s", (flight["destination"], flight["flight_id"]))
    failed_ids = [f["transit_id"] for f in b["failed"]]
    assert ids[0] in failed_ids and b["scored"] == len(ids) - len(failed_ids) and b["scored"] >= 1
    actual(f"failed={failed_ids} with reason '{b['failed'][0]['reason'][:60]}'; scored={b['scored']}")
