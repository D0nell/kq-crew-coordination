# Test log

Generated 2026-11-10 18:50 by `pytest`. Result: **98 of 98 checks passed** across 72 test cases (a test case with several inputs counts one check per input).

Run against a throw-away database (`kq_test`) with a small synthetic dataset and a model trained on it, so the suite never touches the working database.

| ID | Test | Expected result | Actual result | Outcome | Corrective action |
|---|---|---|---|---|---|
| TC-01 | Loader: row counts in PostgreSQL equal the rows in each CSV | every table count equals its CSV row count | All 6 tables match: crew_profiles 60, vehicles 20, flight_schedules 400, transit_events 1500, mobilization_log 6046, users 75 | PASSED | None needed |
| TC-02 | Loader: an empty database gets the schema and the Sprint II migration | tables, predictions table and alert columns exist after loading | Fresh database created with predictions table and the 4 new alert columns | PASSED | None needed |
| TC-03 | Loader: running the load twice gives the same counts and new rows still get fresh ids | same counts, no duplicate-key error on insert | Second load returned identical counts (8630 rows); insert after reload succeeded | PASSED | None needed |
| TC-04 | Loader: no child row points at a missing parent | zero orphan rows | 0 orphans across 4 relationships | PASSED | None needed |
| TC-05 | Loader: a CSV is missing from the data folder | FileNotFoundError naming the file; existing data untouched | Raised FileNotFoundError: C:\Users\donel\AppData\Local\Temp\pytest-of-donel\pytest-136\test_missing_csv_is_reported0\broken\Vehicles.csv not found. Generate the data first: python data/generate_dataset.py --outdir C:\Users\donel\AppData\Local\Temp\pytest-of-donel\pytest-136\test_missing_csv_is_reported0\broken; transit_events still populated | PASSED | None needed |
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
| TC-17 | Resolve the same alert twice, then re-score its transit | both resolves 200 with the same resolved_at; a still-high-risk transit reopens the model alert on rescore | both resolves 200 with same resolved_at; rescore reopened the still-high-risk alert | PASSED | None needed |
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
| TC-27 | Model file is missing | scoring returns 503 with an instruction to train the model; /health reports degraded | 503: Model not found at '<path>'. Run ml/training/train_xgboost.py first to produce it. | PASSED | None needed |
| TC-28 | Model file exists but is corrupt | 503 saying the model could not be loaded, not a 500 crash | 503: Model file at 'C | PASSED | None needed |
| TC-29 | PostgreSQL is unreachable | data endpoints return 503 'Database unreachable'; /health still answers with status degraded | /api/transits 503; /health 200 with database=unreachable | PASSED | None needed |
| TC-30 | GET /dashboard and GET / | dashboard HTML is served; root identifies the service | dashboard 200 text/html; root 200 | PASSED | None needed |
| TC-31 | One transit has a destination the model never saw | that transit is listed in 'failed' with a reason, the others in the batch still score | failed=[1391] with reason 'Unseen value for 'destination': 'ZZZ''; scored=2 | PASSED | None needed |
| TC-32 | GET /api/options (feeds the form dropdowns) | returns exactly the categories in the model's encoders for all 5 categorical fields | 5 fields returned; corridor=6, rank=4, base_location=3, vehicle_type=4, destination=10 | PASSED | None needed |
| TC-33 | Every value offered in the dropdowns is sent to /predict-delay-risk | each is accepted (HTTP 200), none rejected as unseen | 27 option values tested, all HTTP 200 | PASSED | None needed |
| TC-34 | GET /predict | HTML page is served and contains an input for each of the 14 model fields | Page served; all 14 field names present | PASSED | None needed |
| TC-35 | GET /static/kq.css and /static/kq.js | the shared stylesheet and status script are served with the right content types and define the KQ tokens | kq.css 200 text/css with KQ tokens; kq.js 200 javascript | PASSED | None needed |
| TC-36 | GET /dashboard and GET /predict | both pages load the shared stylesheet and script, show the same navigation, a system-status chip and the synthetic-data notice in the page source | both pages: stylesheet, script, nav links, status chip and synthetic-data notice present | PASSED | None needed |
| TC-37 | GET /api/transits?sort=probability | scored transits first, highest delay probability first; unscored transits last | 153 transits: 60 scored in probability DESC, 93 unscored last | PASSED | None needed |
| TC-38 | GET /api/transits?risk=critical | only scored transits whose risk is HIGH or CRITICAL | risk=critical returned 25 of 25 critical transits | PASSED | None needed |
| TC-39 | GET /api/transits with an invalid sort or risk value | 422 validation error | 422 for /api/transits?sort=banana | PASSED | None needed |
| TC-39 | GET /api/transits with an invalid sort or risk value | 422 validation error | 422 for /api/transits?risk=maybe | PASSED | None needed |
| TC-39 | GET /api/transits with an invalid sort or risk value | 422 validation error | 422 for /api/transits?sort=probability&risk=weird | PASSED | None needed |
| TC-40 | Score a high-risk transit that has no alert | one open model alert is created with the transit's probability and resolved_at empty | created model alert 754 for transit 167; resolved=False, resolved_at=None | PASSED | None needed |
| TC-41 | Re-score a high-risk transit whose alert a dispatcher already resolved | the alert is reopened and resolved_at is cleared | alert 768 reopened after rescore; resolved_at cleared | PASSED | None needed |
| TC-42 | Re-score a transit whose probability is now below the alert threshold | its open model alert is resolved automatically | alert for transit 167 resolved after below-threshold rescore | PASSED | None needed |
| TC-43 | Score the same transits repeatedly | exactly one model alert per transit, never a duplicate | 12 transits, no duplicate model alerts | PASSED | None needed |
| TC-44 | Score transits in a dataset that contains historical alerts | the historical (non-model) alerts are not modified | 529 non-model alerts unchanged after scoring | PASSED | None needed |
| TC-45 | Bulk-resolve three open model alerts in one request | all three are resolved with resolved_at set; counts show total 3, resolved 3 | resolved 3 alerts; resolved_at set | PASSED | None needed |
| TC-46 | Bulk-resolve a mix of open, already-resolved, unknown and historical ids | every id is classified correctly and the request still succeeds | mixed batch: resolved=4, already=2, unknown=2, ineligible=1 | PASSED | None needed |
| TC-47 | Bulk-resolve called with no login, as CREW and as DISPATCHER | 401, 403 and 200 respectively | auth cases 401/403/200 as expected | PASSED | None needed |
| TC-48 | The same bulk-resolve batch is sent twice | the second call reports already_resolved and resolved_at does not change | repeat batch: resolved=0, already_resolved=3, resolved_at preserved | PASSED | None needed |
| TC-49 | Bulk-resolve that includes historical alert ids | historical alerts are never modified | 3 historical alerts unchanged | PASSED | None needed |
| TC-50 | Bulk-resolve with a missing, empty, non-positive, non-numeric, duplicate or 501-item list | 422 validation error | 422 for {} | PASSED | None needed |
| TC-50 | Bulk-resolve with a missing, empty, non-positive, non-numeric, duplicate or 501-item list | 422 validation error | 422 for {'alert_ids': []} | PASSED | None needed |
| TC-50 | Bulk-resolve with a missing, empty, non-positive, non-numeric, duplicate or 501-item list | 422 validation error | 422 for {'alert_ids': [0]} | PASSED | None needed |
| TC-50 | Bulk-resolve with a missing, empty, non-positive, non-numeric, duplicate or 501-item list | 422 validation error | 422 for {'alert_ids': ['x']} | PASSED | None needed |
| TC-50 | Bulk-resolve with a missing, empty, non-positive, non-numeric, duplicate or 501-item list | 422 validation error | 422 for {'alert_ids': [1, 1]} | PASSED | None needed |
| TC-50 | Bulk-resolve with a missing, empty, non-positive, non-numeric, duplicate or 501-item list | 422 validation error | 422 for a list of 501 ids | PASSED | None needed |
| TC-51 | A database error part-way through a bulk-resolve | HTTP 503 and the whole batch is rolled back | 503 raised and entire batch rolled back | PASSED | None needed |
| TC-52 | Requests with no login to dispatcher-only endpoints | 401 on every one, before any data is read | 401 for unauthenticated requests to dispatcher-only endpoints | PASSED | None needed |
| TC-53 | A signed-in dispatcher calls dispatcher-only endpoints | access granted (200, or a normal 404 for a missing id) | dispatcher session granted /api/transits 200 and /api/alerts 200 | PASSED | None needed |
| TC-54 | A signed-in CREW account calls dispatcher-only endpoints | 403 on every one | 403 for authenticated CREW account on dispatcher-only endpoints | PASSED | None needed |
| TC-55 | Sign in with a valid dispatcher email and password | 200 with the dashboard as the redirect, and /api/me then returns the account with no password data | signed in as Test Dispatcher (DISPATCHER); /api/me has no password data | PASSED | None needed |
| TC-56 | Sign in with the email typed in capital letters | accepted, because emails are compared without case | upper-case email accepted and the session works | PASSED | None needed |
| TC-57 | Sign in with a wrong password or an unknown email | 401 with the same message for both, and no session is created | 401 'Invalid email or password.' for a wrong password and for an unknown email; no session | PASSED | None needed |
| TC-57 | Sign in with a wrong password or an unknown email | 401 with the same message for both, and no session is created | 401 'Invalid email or password.' for a wrong password and for an unknown email; no session | PASSED | None needed |
| TC-58 | Sign in with a missing, empty or too-short field | 422 validation error | 422 for no body fields, a missing password, an empty password and a 2-character email | PASSED | None needed |
| TC-58 | Sign in with a missing, empty or too-short field | 422 validation error | 422 for no body fields, a missing password, an empty password and a 2-character email | PASSED | None needed |
| TC-58 | Sign in with a missing, empty or too-short field | 422 validation error | 422 for no body fields, a missing password, an empty password and a 2-character email | PASSED | None needed |
| TC-58 | Sign in with a missing, empty or too-short field | 422 validation error | 422 for no body fields, a missing password, an empty password and a 2-character email | PASSED | None needed |
| TC-59 | Sign out | the session ends: /api/me and dispatcher-only endpoints return 401 afterwards | 200 before sign-out; 401 on /api/me and /api/transits after | PASSED | None needed |
| TC-60 | Open the dashboard, Alerts or What-if page without being signed in | redirected (303) to /login | 303 to /login for /dashboard, /alerts and /predict | PASSED | None needed |
| TC-60 | Open the dashboard, Alerts or What-if page without being signed in | redirected (303) to /login | 303 to /login for /dashboard, /alerts and /predict | PASSED | None needed |
| TC-60 | Open the dashboard, Alerts or What-if page without being signed in | redirected (303) to /login | 303 to /login for /dashboard, /alerts and /predict | PASSED | None needed |
| TC-61 | A CREW account opens the dispatcher dashboard | redirected (303) to /predict | 303 to /predict | PASSED | None needed |
| TC-62 | A signed-in user opens /dashboard, /alerts and /predict | every page has a Sign out button and the three-link menu; the Alerts page has the ID search box and alert list | all three pages have Sign out and the three menu links; Alerts page has search box and list | PASSED | None needed |
| TC-63 | GET /api/transits?q=<id> | exactly that transit is returned, with or without a leading # or spaces; an unknown id or non-numeric text (including SQL-like text) returns none | transit 1391 found as '1391', '#1391' and ' 1391 '; 7 unknown or non-numeric terms returned none | PASSED | None needed |
| TC-64 | GET /api/transits?q=<id> together with the corridor and status filters | the search narrows within the filters: the right corridor and scored state find the transit, the wrong ones do not | transit 1391: found in its own corridor and in the correct scored state only | PASSED | None needed |
| TC-65 | GET /api/transits with a blank or over-long q | a blank search is ignored and lists all transits; more than 20 characters is rejected with 422 | blank q listed all 153 transits; 21 characters gave 422 | PASSED | None needed |
| TC-66 | GET /api/my-transits as a crew member linked to a crew profile | only that crew member's own test-split transits, with a risk label and no recorded outcome; no login gives 401, a dispatcher 403, an unlinked crew account an empty list | crew 38: 8 own transits returned, no outcomes exposed; 401 / 403 / empty-list cases correct | PASSED | None needed |
| TC-67 | A new person signs up with a verified Google account | a CREW account is created and signed in, with no password and no dispatcher access | account created as CREW, signed in, dispatcher endpoints 403, password sign-in impossible | PASSED | None needed |
| TC-68 | The same Google account signs in twice | one account only; the second time created is false and the user id is unchanged | one account for two sign-ins | PASSED | None needed |
| TC-69 | A Google account whose verified email matches an existing dispatcher | it signs in to that account and keeps the DISPATCHER role; no duplicate is created; an email already linked to another Google account is refused | linked by verified email, role kept, second Google account on the same email refused (403) | PASSED | None needed |
| TC-70 | Google sign-in with a bad token, an unverified email, no server setup, or a malformed body | 401, 401, 503, 422; no session and no account is created | 401, 401, 503, 422, 422; no session; no account created | PASSED | None needed |
| TC-71 | The server's own token checks | a token for a different app, a different issuer, or an unverified email is refused; a correct one is accepted; with no client id configured nothing is accepted | wrong app, wrong issuer, unverified email, expired token and missing setup all refused; a correct token accepted | PASSED | None needed |
| TC-72 | GET /signup and /api/auth-config | the sign-up page is public and says new accounts are crew accounts; a signed-in user is redirected away; the config shows the Google client id only when one is set | sign-up page served, signed-in user redirected, client id shown only when configured | PASSED | None needed |
