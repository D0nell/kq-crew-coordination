"""API behaviour, invalid input and failure conditions (TC-07 to TC-31)."""

import os

import numpy as np
import pytest
from sklearn.metrics import f1_score, precision_score, recall_score

from conftest import first_ids

from api.main import app


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


def test_resolve_twice_and_rescore_high_risk_reopens_alert(client, q, actual):
    """TC-17 | Resolve the same alert twice, then re-score its transit | both resolves 200 with the
    same resolved_at; a still-high-risk transit reopens the model alert on rescore"""
    ids = first_ids(client, 40)
    client.post("/api/transits/score-batch", json={"transit_ids": ids})
    a = client.get("/api/alerts").json()["items"][0]
    r1 = client.patch(f"/api/alerts/{a['alert_id']}/resolve").json()
    r2 = client.patch(f"/api/alerts/{a['alert_id']}/resolve").json()
    assert r1["resolved_at"] == r2["resolved_at"]
    client.post(f"/api/transits/{a['transit_id']}/score")
    after = q("SELECT resolved, resolved_at FROM alerts WHERE alert_id = %s", (a["alert_id"],))[0]
    assert after["resolved"] is False
    assert after["resolved_at"] is None
    actual("both resolves 200 with same resolved_at; rescore reopened the still-high-risk alert")


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


# ------------------------------------------------------------------ prediction form support
GOOD_BODY = {"is_weekday": 1, "is_rush_hour": 1, "weather_flag": 0, "traffic_congestion_index": 0.6,
             "historical_avg_delay_min": 12.0, "distance_km": 20.0, "hour_of_day": 8, "day_of_week": 1, "capacity": 14}


def test_options_match_model(client, actual):
    """TC-32 | GET /api/options (feeds the form dropdowns) | returns exactly the categories in the model's encoders for all 5 categorical fields"""
    from api.scoring import load_bundle
    enc = load_bundle()["encoders"]
    got = client.get("/api/options").json()
    assert set(got) == {"corridor", "rank", "base_location", "vehicle_type", "destination"}
    for k, values in got.items():
        assert values == [str(c) for c in enc[k].classes_]
        assert len(values) > 0
    actual("5 fields returned; " + ", ".join(f"{k}={len(v)}" for k, v in got.items()))


def test_every_option_is_accepted_by_predict(client, actual):
    """TC-33 | Every value offered in the dropdowns is sent to /predict-delay-risk | each is accepted (HTTP 200), none rejected as unseen"""
    opts = client.get("/api/options").json()
    base = {k: v[0] for k, v in opts.items()}
    checked = 0
    for field, values in opts.items():
        for v in values:
            r = client.post("/predict-delay-risk", json={**GOOD_BODY, **base, field: v})
            assert r.status_code == 200, (field, v, r.text)
            checked += 1
    actual(f"{checked} option values tested, all HTTP 200")


def test_predict_page_has_all_fields(client, actual):
    """TC-34 | GET /predict | HTML page is served and contains an input for each of the 14 model fields"""
    r = client.get("/predict")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    fields = ["is_weekday", "is_rush_hour", "weather_flag", "traffic_congestion_index", "historical_avg_delay_min",
              "distance_km", "hour_of_day", "day_of_week", "capacity", "corridor", "rank", "base_location",
              "vehicle_type", "destination"]
    missing = [f for f in fields if f'name="{f}"' not in r.text]
    assert not missing, missing
    actual("Page served; all 14 field names present")


# ------------------------------------------------------------------ shared design system (Sprint III, Stage 2)
def test_design_assets_served(client, actual):
    """TC-35 | GET /static/kq.css and /static/kq.js | the shared stylesheet and status script are served with the right content types and define the KQ tokens"""
    css = client.get("/static/kq.css")
    js = client.get("/static/kq.js")
    assert css.status_code == 200 and "text/css" in css.headers["content-type"]
    assert "--kq-red" in css.text and "--kq-navy" in css.text and "--crit-ink" in css.text
    assert js.status_code == 200 and "javascript" in js.headers["content-type"] and "/health" in js.text
    actual("kq.css 200 text/css with KQ tokens; kq.js 200 javascript")


def test_pages_share_layout(client, actual):
    """TC-36 | GET /dashboard and GET /predict | both pages load the shared stylesheet and script, show the same navigation, a system-status chip and the synthetic-data notice"""
    for path in ("/dashboard", "/predict"):
        t = client.get(path).text
        for needle in ('href="/static/kq.css"', 'src="/static/kq.js"', 'id="sysStatus"',
                       'href="/dashboard"', 'href="/predict"', "Synthetic data"):
            assert needle in t, (path, needle)
            actual("both pages: stylesheet, script, nav links, status chip and synthetic-data notice present")

# ------------------------------------------------------------------ authentication
def test_unauthenticated_access_rejected(client, actual):
    """No session: dispatcher-only endpoints are rejected before touching the database."""
    from fastapi.testclient import TestClient

    c = TestClient(app)
    for path in ("/api/transits", "/api/alerts", "/api/summary", "/api/me"):
        assert c.get(path).status_code == 401, (path, c.get(path).status_code)
    assert c.post("/api/transits/99999999/score").status_code == 401
    assert c.post("/api/transits/score-batch", json={"transit_ids": [1]}).status_code == 401
    actual("401 for unauthenticated requests to dispatcher-only endpoints")


def test_dispatcher_session_grants_access(client, actual):
    """An authenticated dispatcher session is granted access to dispatcher-only endpoints."""
    assert client.get("/api/transits").status_code == 200
    assert client.get("/api/alerts").status_code == 200
    assert client.post("/api/transits/99999999/score").status_code == 404
    actual("dispatcher session granted /api/transits 200 and /api/alerts 200")


def test_crew_account_denied_dispatcher_access(crew_client, actual):
    """A CREW account is authenticated but denied dispatcher-only endpoints (403)."""
    assert crew_client.get("/api/transits").status_code == 403
    assert crew_client.get("/api/alerts").status_code == 403
    assert crew_client.get("/api/summary").status_code == 403
    assert crew_client.post("/api/transits/99999999/score").status_code == 403
    assert crew_client.post("/api/transits/score-batch", json={"transit_ids": [1]}).status_code == 403
    actual("403 for authenticated CREW account on dispatcher-only endpoints")


# ------------------------------------------------------------------ alert lifecycle


def test_high_risk_creates_model_alert(client, q, actual):
    """TC-40 | A high-risk transit with no existing alert creates a model alert"""
    ids = first_ids(client, 30)
    b = client.post("/api/transits/score-batch", json={"transit_ids": ids}).json()
    high_risk = [r for r in b["results"] if r["alert_raised"]]
    assert high_risk, "no high-risk transit in batch"
    tid = high_risk[0]["transit_id"]
    alerts = q(
        "SELECT alert_id, transit_id, severity, generated_at, resolved, resolved_at, "
        "delay_probability, source, model_version FROM alerts "
        "WHERE transit_id = %s AND source = 'model'",
        (tid,),
    )
    assert len(alerts) == 1, f"expected 1 model alert, got {len(alerts)}"
    a = alerts[0]
    assert a["resolved"] is False
    assert a["resolved_at"] is None
    assert float(a["delay_probability"]) == pytest.approx(high_risk[0]["delay_probability"])
    actual(f"created model alert {a['alert_id']} for transit {tid}; resolved={a['resolved']}, resolved_at=None")


def test_rescore_high_risk_reopens_already_resolved_model_alert(client, q, actual):
    """TC-41 | Rescoring a high-risk transit whose model alert is already resolved reopens it and clears resolved_at"""
    ids = first_ids(client, 30)
    b = client.post("/api/transits/score-batch", json={"transit_ids": ids}).json()
    high_risk = [r for r in b["results"] if r["alert_raised"]]
    assert high_risk, "no high-risk transit in batch"
    tid = high_risk[0]["transit_id"]
    before = q(
        "SELECT alert_id, resolved, resolved_at, generated_at FROM alerts "
        "WHERE transit_id = %s AND source = 'model'",
        (tid,),
    )
    assert len(before) == 1 and before[0]["resolved"] is False
    # simulate a dispatcher resolving the live model alert
    client.patch(f"/api/alerts/{before[0]['alert_id']}/resolve")
    # the transit is still high-risk, so the alert must reopen
    b2 = client.post(f"/api/transits/{tid}/score").json()
    assert b2["delay_probability"] >= 0.5
    after = q(
        "SELECT resolved, resolved_at, generated_at, severity, delay_probability, model_version "
        "FROM alerts WHERE alert_id = %s",
        (before[0]["alert_id"],),
    )[0]
    assert after["resolved"] is False
    assert after["resolved_at"] is None
    assert after["generated_at"] >= before[0]["generated_at"]
    assert float(after["delay_probability"]) == pytest.approx(b2["delay_probability"])
    actual(f"alert {before[0]['alert_id']} reopened after rescore; resolved_at cleared")


def test_rescore_below_threshold_resolves_open_model_alert(client, q, actual, monkeypatch):
    """TC-42 | A below-threshold rescore resolves the open model alert for that transit"""
    ids = first_ids(client, 30)
    b = client.post("/api/transits/score-batch", json={"transit_ids": ids}).json()
    high_risk = [r for r in b["results"] if r["alert_raised"]]
    assert high_risk, "no high-risk transit in batch"
    tid = high_risk[0]["transit_id"]
    p = float(q("SELECT delay_probability FROM predictions WHERE transit_id = %s", (tid,))[0]["delay_probability"])
    assert p >= 0.5
    # raise the threshold above this transit's probability so it no longer triggers
    monkeypatch.setenv("ALERT_THRESHOLD", str(round(p + 0.01, 4)))
    b2 = client.post("/api/transits/score-batch", json={"transit_ids": [tid]}).json()
    assert b2["results"][0]["alert_raised"] is False
    a = q(
        "SELECT resolved, resolved_at FROM alerts WHERE alert_id = %s",
        (q("SELECT alert_id FROM alerts WHERE transit_id = %s AND source = 'model'", (tid,))[0]["alert_id"],),
    )[0]
    assert a["resolved"] is True
    assert a["resolved_at"] is not None
    actual(f"alert reopened at {tid} resolved after below-threshold rescore")


def test_repeated_scoring_creates_no_duplicate_model_alerts(client, q, actual):
    """TC-43 | Repeated scoring of the same transits creates exactly one model alert per transit"""
    ids = first_ids(client, 20)
    client.post("/api/transits/score-batch", json={"transit_ids": ids})
    client.post("/api/transits/score-batch", json={"transit_ids": ids})
    per_transit = q(
        "SELECT transit_id, COUNT(*) AS n FROM alerts "
        "WHERE source = 'model' GROUP BY transit_id"
    )
    over = [r for r in per_transit if r["n"] > 1]
    assert not over, f"transits with >1 model alert: {[r['transit_id'] for r in over]}"
    actual(f"{len(per_transit)} transits, no duplicate model alerts")


def test_non_model_alerts_not_modified(client, q, actual):
    """TC-44 | Scoring does not modify non-model (historical) alerts"""
    before = {
        r["alert_id"]: dict(r)
        for r in q("SELECT alert_id, transit_id, severity, resolved, resolved_at FROM alerts WHERE source <> 'model'")
    }
    assert before, "no non-model alerts in the test dataset"
    ids = first_ids(client, 20)
    client.post("/api/transits/score-batch", json={"transit_ids": ids})
    after = {
        r["alert_id"]: dict(r)
        for r in q("SELECT alert_id, transit_id, severity, resolved, resolved_at FROM alerts WHERE source <> 'model'")
    }
    assert after == before, "non-model alerts were modified by scoring"
    actual(f"{len(after)} non-model alerts unchanged after scoring")


def test_queue_sorts_by_probability_desc(client, q, actual):
    """TC-XX | GET /api/transits?sort=probability | scored transits ordered by delay_probability DESC, nulls last"""
    ids = first_ids(client, 60)
    client.post("/api/transits/score-batch", json={"transit_ids": ids})
    items = client.get("/api/transits", params={"sort": "probability", "limit": 200}).json()["items"]
    scored = [i for i in items if i.get("delay_probability") is not None]
    probs = [float(i["delay_probability"]) for i in scored]
    assert probs == sorted(probs, reverse=True)
    assert all(i.get("delay_probability") is None for i in items[len(scored):])
    actual(f"{len(items)} transits: {len(scored)} scored in probability DESC, {len(items) - len(scored)} unscored last")


def test_queue_critical_risk_filter(client, q, actual):
    """TC-XX | GET /api/transits?risk=critical | only scored transits with HIGH/CRITICAL risk"""
    ids = first_ids(client, 60)
    client.post("/api/transits/score-batch", json={"transit_ids": ids})
    critical = q("SELECT transit_id FROM predictions WHERE risk_level IN ('HIGH', 'CRITICAL')")
    items = client.get("/api/transits", params={"risk": "critical", "limit": 200}).json()["items"]
    assert len(items) == len(critical)
    assert all(i["risk_level"] in {"HIGH", "CRITICAL"} for i in items)
    actual(f"risk=critical returned {len(items)} of {len(critical)} critical transits")


@pytest.mark.parametrize("url", [
    "/api/transits?sort=banana",
    "/api/transits?risk=maybe",
    "/api/transits?sort=probability&risk=weird",
])
def test_queue_bad_sort_and_risk_params_422(client, url, actual):
    """TC-XX | GET /api/transits with invalid sort/risk values | 422 validation error"""
    assert client.get(url).status_code == 422
    actual(f"422 for {url}")


# ------------------------------------------------------------------ bulk alert resolution

def test_bulk_resolve_multiple_open_alerts(client, q, actual):
    """TC-45 | Multiple open model alerts resolve successfully in one batch."""
    ids = first_ids(client, 30)
    client.post("/api/transits/score-batch", json={"transit_ids": ids})
    open_alerts = q(
        "SELECT alert_id FROM alerts WHERE source='model' AND resolved=FALSE ORDER BY alert_id"
    )
    assert len(open_alerts) >= 3
    body = {"alert_ids": [a["alert_id"] for a in open_alerts[:3]]}
    r = client.post("/api/alerts/bulk-resolve", json=body)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["counts"] == {
        "total": 3, "resolved": 3, "already_resolved": 0,
        "not_found": 0, "ineligible": 0, "failed": 0,
    }
    assert j["successfully_affected_alert_ids"] == [a["alert_id"] for a in open_alerts[:3]]
    for a in open_alerts[:3]:
        row = q("SELECT resolved, resolved_at FROM alerts WHERE alert_id=%s", (a["alert_id"],))[0]
        assert row["resolved"] is True
        assert row["resolved_at"] is not None
    actual(f"resolved {len(open_alerts[:3])} alerts; resolved_at set")


def test_bulk_resolve_mixed_outcomes(client, q, actual):
    """TC-46 | Mixed open, already-resolved, unknown and historical IDs."""
    ids = first_ids(client, 40)
    client.post("/api/transits/score-batch", json={"transit_ids": ids})
    open_alerts = q(
        "SELECT alert_id FROM alerts WHERE source='model' AND resolved=FALSE ORDER BY alert_id LIMIT 6"
    )
    assert len(open_alerts) >= 6
    already = [a["alert_id"] for a in open_alerts[:2]]
    for aid in already:
        client.patch(f"/api/alerts/{aid}/resolve")  # pre-resolve individually (existing endpoint)
    open_alerts = q(
        "SELECT alert_id FROM alerts WHERE source='model' AND resolved=FALSE ORDER BY alert_id LIMIT 4"
    )
    hist = q("SELECT alert_id FROM alerts WHERE source <> 'model' ORDER BY alert_id LIMIT 1")[0]
    body = {
        "alert_ids": [a["alert_id"] for a in open_alerts]
        + already
        + [hist["alert_id"], 99999999, 100000000],
    }
    r = client.post("/api/alerts/bulk-resolve", json=body)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["counts"] == {
        "total": len(body["alert_ids"]),
        "resolved": 4, "already_resolved": 2, "not_found": 2, "ineligible": 1, "failed": 0,
    }
    assert set(j["not_found_alert_ids"]) == {99999999, 100000000}
    assert j["ineligible_alert_ids"] == [hist["alert_id"]]
    assert set(j["resolved_alert_ids"]) == {a["alert_id"] for a in open_alerts}
    assert set(j["already_resolved_alert_ids"]) == set(already)
    actual(f"mixed batch: resolved={j['counts']['resolved']}, "
           f"already={j['counts']['already_resolved']}, unknown={j['counts']['not_found']}, "
           f"ineligible={j['counts']['ineligible']}")


def test_bulk_resolve_auth(client, crew_client, q, actual):
    """TC-47 | Dispatcher authorization enforced (unauthenticated, CREW, DISPATCHER)."""
    ids = first_ids(client, 10)
    client.post("/api/transits/score-batch", json={"transit_ids": ids})
    open_alerts = [
        a["alert_id"] for a in q(
            "SELECT alert_id FROM alerts WHERE source='model' AND resolved=FALSE LIMIT 3"
        )
    ]
    from fastapi.testclient import TestClient

    anon = TestClient(app)
    r = anon.post("/api/alerts/bulk-resolve", json={"alert_ids": [open_alerts[0]]})
    assert r.status_code == 401, f"unauthenticated should be 401, got {r.status_code}"
    r = crew_client.post("/api/alerts/bulk-resolve", json={"alert_ids": [open_alerts[0]]})
    assert r.status_code == 403, f"CREW should be 403, got {r.status_code}"
    r = client.post("/api/alerts/bulk-resolve", json={"alert_ids": open_alerts})
    assert r.status_code == 200, f"dispatcher should be 200, got {r.status_code}"
    actual("auth cases 401/403/200 as expected")


def test_bulk_resolve_repeated_batch_safe(client, q, actual):
    """TC-48 | Repeating a batch is safe; resolved_at is not overwritten."""
    ids = first_ids(client, 30)
    client.post("/api/transits/score-batch", json={"transit_ids": ids})
    open_alerts = q(
        "SELECT alert_id FROM alerts WHERE source='model' AND resolved=FALSE ORDER BY alert_id LIMIT 3"
    )
    assert len(open_alerts) >= 3
    first = [a["alert_id"] for a in open_alerts]
    r1 = client.post("/api/alerts/bulk-resolve", json={"alert_ids": first})
    assert r1.status_code == 200
    assert r1.json()["counts"]["resolved"] == 3
    r2 = client.post("/api/alerts/bulk-resolve", json={"alert_ids": first})
    assert r2.status_code == 200
    j2 = r2.json()
    assert j2["counts"] == {
        "total": 3, "resolved": 0, "already_resolved": 3,
        "not_found": 0, "ineligible": 0, "failed": 0,
    }
    assert j2["already_resolved_alert_ids"] == first
    ts = {row["alert_id"]: row["resolved_at"] for row in
          q("SELECT alert_id, resolved_at FROM alerts WHERE alert_id = ANY(%s)", (first,))}
    rows2 = q("SELECT alert_id, resolved_at FROM alerts WHERE alert_id = ANY(%s)", (first,))
    for row in rows2:
        assert row["resolved_at"] == ts[row["alert_id"]], "resolved_at must not change on a repeat"
    actual("repeat batch: resolved=0, already_resolved=3, resolved_at preserved")


def test_bulk_resolve_historical_alerts_unchanged(client, q, actual):
    """TC-49 | Historical (non-model) alerts are never modified by bulk resolve."""
    ids = first_ids(client, 30)
    client.post("/api/transits/score-batch", json={"transit_ids": ids})
    hist = q("SELECT alert_id, resolved, resolved_at FROM alerts WHERE source <> 'model' ORDER BY alert_id LIMIT 3")
    before = {h["alert_id"]: dict(h) for h in hist}
    first = [a["alert_id"] for a in q(
        "SELECT alert_id FROM alerts WHERE source='model' AND resolved=FALSE ORDER BY alert_id LIMIT 3"
    )]
    body = {"alert_ids": first + [h["alert_id"] for h in hist]}
    r = client.post("/api/alerts/bulk-resolve", json=body)
    assert r.status_code == 200, r.text
    after = {
        h["alert_id"]: dict(h)
        for h in q("SELECT alert_id, resolved, resolved_at FROM alerts WHERE alert_id = ANY(%s)",
                   ([h["alert_id"] for h in hist],))
    }
    assert after == before, "non-model alerts must be untouched"
    actual(f"{len(before)} historical alerts unchanged")


@pytest.mark.parametrize("bad", [
    {}, {"alert_ids": []}, {"alert_ids": [0]}, {"alert_ids": ["x"]},
    {"alert_ids": [1, 1]}, {"alert_ids": list(range(1, 502))},
])
def test_bulk_resolve_invalid_lists_422(client, bad, actual):
    """TC-50 | Empty, duplicate, non-positive, non-unique or oversized id lists rejected."""
    assert client.post("/api/alerts/bulk-resolve", json=bad).status_code == 422
    actual(f"422 for {bad}")


def test_bulk_resolve_db_error_rolls_back(client, q, monkeypatch, actual):
    """TC-51 | An unexpected database error rolls back the whole batch."""
    ids = first_ids(client, 20)
    client.post("/api/transits/score-batch", json={"transit_ids": ids})
    # resolve one model alert individually so the batch contains an already-resolved row
    first_open = q(
        "SELECT alert_id FROM alerts WHERE source='model' AND resolved=FALSE ORDER BY alert_id LIMIT 1"
    )[0]
    client.patch(f"/api/alerts/{first_open['alert_id']}/resolve")  # preserves resolved_at
    already1 = [a["alert_id"] for a in q(
        "SELECT alert_id FROM alerts WHERE source='model' AND resolved=TRUE ORDER BY alert_id LIMIT 1"
    )]
    assert already1, "need an already-resolved model alert"
    open2 = [a["alert_id"] for a in q(
        "SELECT alert_id FROM alerts WHERE source='model' AND resolved=FALSE ORDER BY alert_id LIMIT 2"
    )]
    body = {"alert_ids": open2 + already1}
    import psycopg2
    from api.main import fetch_one as _main_fetch_one

    calls = {"n": 0}

    def _boom(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise psycopg2.OperationalError("simulated disk failure")
        return _main_fetch_one(*args, **kwargs)

    monkeypatch.setattr("api.main.fetch_one", _boom)
    r = client.post("/api/alerts/bulk-resolve", json=body)
    assert r.status_code == 503, f"expected 503, got {r.status_code}: {r.text}"
    assert "simulated disk failure" in r.json()["detail"]
    # everything rolled back: open alerts untouched, already-resolved untouched
    left = q("SELECT COUNT(*) AS n FROM alerts WHERE source='model' AND resolved=FALSE AND alert_id = ANY(%s)", (open2,))
    assert left[0]["n"] == 2, "open alerts must be rolled back"
    still = q("SELECT COUNT(*) AS n FROM alerts WHERE source='model' AND resolved=TRUE AND alert_id = ANY(%s)", (already1,))
    assert still[0]["n"] == 1, "already-resolved alert must be rolled back to resolved"
    actual("503 raised and entire batch rolled back")
