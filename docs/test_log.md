# Test log

Generated 2026-10-15 00:02 by `pytest`. Result: **44 of 44 checks passed** across 31 test cases (a test case with several inputs counts one check per input).

Run against a throw-away database (`kq_test`) with a small synthetic dataset and a model trained on it, so the suite never touches the working database.

| ID | Test | Expected result | Actual result | Outcome | Corrective action |
|---|---|---|---|---|---|
| TC-01 | Loader: row counts in PostgreSQL equal the rows in each CSV | every table count equals its CSV row count | All 6 tables match: crew_profiles 60, vehicles 20, flight_schedules 400, transit_events 1500, mobilization_log 6046, users 75 | PASSED | None needed |
| TC-02 | Loader: an empty database gets the schema and the Sprint II migration | tables, predictions table and alert columns exist after loading | Fresh database created with predictions table and the 4 new alert columns | PASSED | None needed |
| TC-03 | Loader: running the load twice gives the same counts and new rows still get fresh ids | same counts, no duplicate-key error on insert | Second load returned identical counts (8630 rows); insert after reload succeeded | PASSED | None needed |
| TC-04 | Loader: no child row points at a missing parent | zero orphan rows | 0 orphans across 4 relationships | PASSED | None needed |
| TC-05 | Loader: a CSV is missing from the data folder | FileNotFoundError naming the file; existing data untouched | Raised FileNotFoundError: C:\Users\donel\AppData\Local\Temp\pytest-of-donel\pytest-0\test_missing_csv_is_reported0\broken\Vehicles.csv not found. Generate the data first: python data/generate_dataset.py --outdir C:\Users\donel\AppData\Local\Temp\pytest-of-donel\pytest-0\test_missing_csv_is_reported0\broken; transit_events still populated | PASSED | None needed |
| TC-06 | Loader CLI: PostgreSQL is not reachable on the given URL | exit code 1 and a one-line 'ERROR:' message, no stack trace | Exit code 1; message: Is the server running on that host and accepting TCP/IP connections? | PASSED | None needed |
| TC-07 | GET /health with model and database available | status ok, database ok, model_file_found true | status=ok, database=ok, threshold=0.5 | PASSED | None needed |
| TC-08 | GET /api/transits with no filters | only held-out test-split transits, in pickup-time order | 153 test transits, all split=test, sorted by pickup time | PASSED | None needed |
| TC-09 | GET /api/transits with corridor filter and limit/offset | only that corridor, pages do not overlap | corridor='Mombasa Rd - JKIA' returned 5 rows; pages 1 and 2 are disjoint | PASSED | None needed |
| TC-10 | POST /api/transits/{id}/score for a real transit | probability in 0..1, risk level set, prediction stored | transit 1391: p=0.5936, HIGH, stored | PASSED | None needed |
| TC-11 | Score 60 transits at the default 0.5 threshold | an open model alert exists exactly when p >= 0.5 | 25 alerts for 60 scored transits; alert set equals {p >= 0.5} | PASSED | None needed |
| TC-12 | Score the same transits twice | no duplicate predictions or alerts | 40 predictions and no duplicated model alerts after two passes | PASSED | None needed |
| TC-13 | A transit with an open alert is re-scored with a higher threshold | the stale alert is auto-resolved | Open alerts before: >0, after re-score at threshold 0.99: 0 | PASSED | None needed |
| TC-14 | POST score-batch with 25 ids | scored=25 and alerts_raised equals the number of results flagged | scored=25, alerts_raised=13 | PASSED | None needed |
| TC-15 | GET /api/alerts after scoring | open alerts only, highest probability first | 33 open alerts, top p=0.8507 | PASSED | None needed |
| TC-16 | PATCH /api/alerts/{id}/resolve on an open alert | alert resolved, timestamp set, removed from the open list | alert 668 resolved and gone from open list | PASSED | None needed |
| TC-17 | Resolve the same alert twice, then re-score its transit | both calls 200, original resolved_at kept, dispatcher decision not reopened | Second resolve returned same resolved_at; re-score did not reopen the alert | PASSED | None needed |
| TC-18 | GET /api/summary replay metrics after scoring 120 test transits | precision, recall and F1 equal scikit-learn computed independently from the database | n=120: P=0.6667, R=0.7308, F1=0.6972 (matches scikit-learn) | PASSED | None needed |
| TC-19 | Leakage guard: the feature query used for scoring | contains no outcome columns (delay_minutes, delay_risk_class, actual_*, mobilization, alerts) | Feature SQL references none of: delay_minutes, delay_risk_class, actual, mobilization, alerts, split | PASSED | None needed |
| TC-20 | Score a transit id that does not exist | 404 with a clear message, nothing stored | 404: Transit 99999999 not found | PASSED | None needed |
| TC-21 | Score with a non-integer, zero or negative transit id | 422 validation error | 422 for ids abc, 0, -5, 1.5 | PASSED | None needed |
| TC-21 | Score with a non-integer, zero or negative transit id | 422 validation error | 422 for ids abc, 0, -5, 1.5 | PASSED | None needed |
| TC-21 | Score with a non-integer, zero or negative transit id | 422 validation error | 422 for ids abc, 0, -5, 1.5 | PASSED | None needed |
| TC-21 | Score with a non-integer, zero or negative transit id | 422 validation error | 422 for ids abc, 0, -5, 1.5 | PASSED | None needed |
| TC-22 | score-batch with a missing, empty, non-positive, non-numeric or 201-item list | 422 validation error | 422 for {}, [], [0], ['x'] and 201 ids | PASSED | None needed |
| TC-22 | score-batch with a missing, empty, non-positive, non-numeric or 201-item list | 422 validation error | 422 for {}, [], [0], ['x'] and 201 ids | PASSED | None needed |
| TC-22 | score-batch with a missing, empty, non-positive, non-numeric or 201-item list | 422 validation error | 422 for {}, [], [0], ['x'] and 201 ids | PASSED | None needed |
| TC-22 | score-batch with a missing, empty, non-positive, non-numeric or 201-item list | 422 validation error | 422 for {}, [], [0], ['x'] and 201 ids | PASSED | None needed |
| TC-22 | score-batch with a missing, empty, non-positive, non-numeric or 201-item list | 422 validation error | 422 for {}, [], [0], ['x'] and 201 ids | PASSED | None needed |
| TC-23 | Batch containing two real ids and one unknown id | real ones scored, unknown listed in not_found, request succeeds | scored=2, not_found=[99999999] | PASSED | None needed |
| TC-24 | Resolve an unknown alert id, and a historical (non-model) alert | 404 for both; historical data is never modified | 404 for unknown id and for historical alert; historical row unchanged | PASSED | None needed |
| TC-25 | List endpoints with out-of-range or unknown query values | 422 validation error, not a 500 | 422 for limit=0, limit=500, offset=-1, split=banana, corridor=Nowhere, status=weird, alerts status=maybe | PASSED | None needed |
| TC-25 | List endpoints with out-of-range or unknown query values | 422 validation error, not a 500 | 422 for limit=0, limit=500, offset=-1, split=banana, corridor=Nowhere, status=weird, alerts status=maybe | PASSED | None needed |
| TC-25 | List endpoints with out-of-range or unknown query values | 422 validation error, not a 500 | 422 for limit=0, limit=500, offset=-1, split=banana, corridor=Nowhere, status=weird, alerts status=maybe | PASSED | None needed |
| TC-25 | List endpoints with out-of-range or unknown query values | 422 validation error, not a 500 | 422 for limit=0, limit=500, offset=-1, split=banana, corridor=Nowhere, status=weird, alerts status=maybe | PASSED | None needed |
| TC-25 | List endpoints with out-of-range or unknown query values | 422 validation error, not a 500 | 422 for limit=0, limit=500, offset=-1, split=banana, corridor=Nowhere, status=weird, alerts status=maybe | PASSED | None needed |
| TC-25 | List endpoints with out-of-range or unknown query values | 422 validation error, not a 500 | 422 for limit=0, limit=500, offset=-1, split=banana, corridor=Nowhere, status=weird, alerts status=maybe | PASSED | None needed |
| TC-25 | List endpoints with out-of-range or unknown query values | 422 validation error, not a 500 | 422 for limit=0, limit=500, offset=-1, split=banana, corridor=Nowhere, status=weird, alerts status=maybe | PASSED | None needed |
| TC-26 | POST /predict-delay-risk with an out-of-range value, a missing field and an unseen category | 422 each time; a valid body returns a probability | valid body p=0.6801; congestion=7, missing rank, destination=ZZZ all 422 | PASSED | None needed |
| TC-27 | Model file is missing | scoring returns 503 with an instruction to train the model; /health reports degraded | 503: Model not found at 'C:\Users\donel\AppData\Local\Temp\pytest-of-donel\pytest-0\t | PASSED | None needed |
| TC-28 | Model file exists but is corrupt | 503 saying the model could not be loaded, not a 500 crash | 503: Model file at 'C:\Users\donel\AppData\Local\Temp\pytest-of-donel\pytest-0\test_c | PASSED | None needed |
| TC-29 | PostgreSQL is unreachable | data endpoints return 503 'Database unreachable'; /health still answers with status degraded | /api/transits 503; /health 200 with database=unreachable | PASSED | None needed |
| TC-30 | GET /dashboard and GET / | dashboard HTML is served; root identifies the service | dashboard 200 text/html; root 200 | PASSED | None needed |
| TC-31 | One transit has a destination the model never saw | that transit is listed in 'failed' with a reason, the others in the batch still score | failed=[1391] with reason 'Unseen value for 'destination': 'ZZZ''; scored=2 | PASSED | None needed |
