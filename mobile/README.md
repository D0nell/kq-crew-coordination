# mobile/

Native Kotlin Android client for the KQ Crew Coordination platform — the
mobile client that crew members and dispatchers open on their devices.

---

## Current state (as of the Nov-20 deadline)

The **Android project source is not in this repository.** The `mobile/`
folder contains only this README. There are no Kotlin sources
(`.kt` / `.kts`), no `build.gradle`, no `settings.gradle`, and no
`AndroidManifest.xml` anywhere in the repo (confirmed: a filesystem-wide
search for `*.kt` / `gradle` / `AndroidManifest.xml` returns nothing,
and `git log --all -- mobile` is empty).

Consequence: the three items in the request below are documented below as
**intended backend contracts the mobile client consumes**, not as
Android code that is present.

> If you are pointing this at a separate Android checkout (a path or a
> git remote), point me at it and I will regenerate this doc against it.

---

## What the mobile client is for

Two terminals, both backed by this repository's own REST API:

| Terminal | Role   | Endpoints the client will call                                |
|----------|--------|---------------------------------------------------------------|
| Dispatch | DISPATCHER | `POST /api/scheduling/generate`, `GET /api/scheduling/proposals`, `POST /api/transits/{id}/approve`, `POST /api/transits/{id}/replan` (FR-06 scheduling board) |
| Crew     | CREW   | `GET /api/my-transits` (approved test-split only, FR-15), `POST /api/transits/{id}/checklist`, `POST /api/transits/{id}/arrival`, GPS pings (FR-03) |

The root README's "Kotlin app scaffold" item is **pending**: the app
does not exist yet, so nothing below is claimable as completed Android
work.

---

## Backend features the mobile client is meant to consume

| Feature      | Where it lives (backend)                                     | Contract the client calls                                      | Mobile Android side |
|--------------|--------------------------------------------------------------|----------------------------------------------------------------|---------------------|
| Crew GPS tracking (FR-03) | `db/migrations/005_gps.sql` → `gps_pings`; `api/crew_features.py` → `GET /api/crew-locations`; `tests/test_gps.py` | Location pings sent by the crew phone, paginated by `recorded_at` | **Not implemented** |
| Scheduling board (FR-06)  | `006_scheduling.sql` (`schedule_status`); `POST /api/scheduling/generate`, `GET /api/scheduling/proposals`, `POST /api/transits/{id}/approve`, `POST /api/transits/{id}/replan` | Dispatcher assigns crew/vehicle and sets status to PROPOSED/APPROVED/REJECTED | **Not implemented** |
| Crew my-transits (FR-15)  | `GET /api/my-transits` filtered to `split='test'` AND `schedule_status='APPROVED'` | Only APPROVED test-split transits for the signed-in crew, sorted by pickup time | **Not implemented** |
| Delay-risk score + alerts | `POST /api/transits/{id}/score`, `alerts`, `ALERT_THRESHOLD=0.5` | Predict-then-alert per transit; resolve via `POST /api/alerts/{id}/resolve` | **Not implemented** |
| Auth (Google sign-in)     | `users` (`role`, `google_sub`), session tokens, `GOOGLE_CLIENT_ID` | Google OAuth + session token on sign-in | **Not implemented** |

---

## Branch reference (this repo's tracking)

- `main` — backend complete (API, DB, model); the mobile scaffold is **not** in it.
- Feature branches: `feature/crew-api`, `feature/crew-features`
  (GPS FR-03, `test_gps.py`, migration 005), `feature/google-signin`,
  `feature/scheduling`, `sprint2-core`, `sprint2-dispatcher-ui`,
  `sprint3-ui`. No `feature/gps-sharing` branch exists here.

> "GPS tracking on main" is true only for the backend (`gps_pings` table);
> the Android GPS module does not exist anywhere in this repo.

---

## Setup (once the Android module skeleton lands)

The mobile client is a standalone Android Studio project:

1. Open `mobile/` as the Android Studio project root.
2. Point the API base URL at the backend (`http://<host>:8000`; the
   emulator uses `10.0.2.2:8000` for the host machine).
3. Provide the Google OAuth `client_id` (see `.env.example` →
   `GOOGLE_CLIENT_ID`) and a session token on sign-in.

---

## Status checklist

- [x] Proposal defended
- [x] Synthetic dataset generator (`data/generate_dataset.py`)
- [x] PostgreSQL schema + migrations (006 scheduling)
- [x] XGBoost model trained & bundled (`models/xgb_final_v1.pkl`)
- [x] FastAPI REST API scaffold (auth + schedule + alerts + transits)
- [x] Dispatcher scheduling endpoints (`generate` / `proposals` / `approve` / `replan`)
- [x] `GET /api/my-transits` restricted to `APPROVED` test-split (crew)
- [x] Crew location map (`/dispatcher-map` ↔ `/api/crew-locations`)
- [ ] Kotlin Android app scaffold
- [ ] GPS tracking implementation (FR-03)
- [ ] API integration (mobile client code)
- [ ] `feature/gps-sharing` merge (no such branch in this repo)
