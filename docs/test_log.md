# Test log

Generated 2026-11-18 12:29 by `pytest`. Result: **2 of 2 checks passed** across 2 test cases (a test case with several inputs counts one check per input).

Run against a throw-away database (`kq_test`) with a small synthetic dataset and a model trained on it, so the suite never touches the working database.

| ID | Test | Expected result | Actual result | Outcome | Corrective action |
|---|---|---|---|---|---|
| TC-78 | A crew member sends their phone's position for a transit | their own transit stores it with a time; someone else's transit is 404; no login is 401; a dispatcher is 403; an impossible position is 422; after arrival is confirmed sharing stops with 409 | two pings stored for the crew member's own transit; 404, 401, 403 and 422 refusals; sharing stopped with 409 after arrival | PASSED | None needed |
| TC-79 | The dispatcher asks for crew locations | each transit shows only its latest position with the crew name and corridor; old positions are left out unless the time window is widened; arrival is shown; crew and anonymous users are refused; a zero time window is 422 | latest position only, old position hidden until the window was widened, crew name and corridor shown, arrival shown, 401 and 403 and 422 as expected | PASSED | None needed |
