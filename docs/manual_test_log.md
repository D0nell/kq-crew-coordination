# Manual test log (run by hand in the browser and Swagger UI)

These complement the automated suite in docs/test_log.md. They are functional checks, not model-performance evidence.
Environment: Windows 11, PostgreSQL 18, Python 3.12, server started with `python -m uvicorn api.main:app --reload`. Run on 14 and 15 October 2026.

| ID | Test | Expected | Actual | Result |
|---|---|---|---|---|
| M-01 | Valid prediction through /predict-delay-risk (Swagger UI) | 200 with probability and risk level | 200, probability 0.7274, HIGH. The same input in the What-if form gave 72.7%, HIGH (screenshot 12) | Pass |
| M-02 | Unknown corridor "Invalid Corridor" (Swagger UI) | 422 naming the corridor | 422: Unseen value for 'corridor': 'Invalid Corridor' (screenshot 04) | Pass |
| M-03 | destination field omitted (Swagger UI) | 422, field required | 422, type "missing" for destination (screenshot 05) | Pass |
| M-04 | Press "Score these transits" on the dashboard | Risk tags, probabilities and alerts appear | 50 transits scored, 19 open alerts listed | Pass |
| M-05 | Resolve an alert on the dashboard | Open alert count drops by one | 19 to 18 | Pass |
| M-06 | Server stopped, press "Predict delay risk" in the What-if form | Clear message, no frozen or blank page | Red box: "Cannot reach the prediction server. Check that the API is running ... and try again." (screenshot 16) | Pass |
| M-06b | Server stopped, press "Re-score" on the dashboard | Clear message, no frozen or blank page | Not yet checked by hand | Pending |
| M-07 | What-if form: "Fill with an example", then predict | Result equals the API's answer for the same input | 72.7%, HIGH risk, "Delay likely" (screenshot 12) | Pass |
| M-08 | What-if form: submit with every field empty | Every field flagged, nothing sent | "Please fix the highlighted fields", each field marked Required or Choose a value (screenshot 13) | Pass |
| M-09 | What-if form: hour of day set to 30 | Message under the field | "Must be 23 or less." (screenshot 14) | Pass |
| M-10 | What-if form: open the Corridor dropdown | Exactly the six corridors the model knows | Six corridors, including "Medical Centre - JKIA" and "Westlands - JKIA" (screenshot 15) | Pass |

Note: a handover document listed two corridors with wrong spellings ("MedicalCentre - JKIA", "Westlands -JKIA"). The model's encoders and the dataset use "Medical Centre - JKIA" and "Westlands - JKIA", so the form reads its dropdown values from the model (GET /api/options) instead of hardcoding them.
