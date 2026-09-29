# Development Environment Walkthrough — Talking Points for Supervisor

Use this as a script to talk through your setup. It's organized around
the 5 requirements so you can map what you did directly to what was asked.

---

## 1. Development environment

"I'm using VS Code for the Python/ML side and Android Studio for the
Kotlin mobile app later — split deliberately, since VS Code handles
Python tooling (Pylance, Jupyter, SQLTools) well but Android Studio is
the only realistic option for native Kotlin development.

Inside VS Code, I've got a Python virtual environment (`.venv`) so my
project's dependencies — pandas, scikit-learn, xgboost, fastapi,
psycopg2 — are isolated from anything else on my machine. Everything
needed is pinned in `requirements.txt`, so anyone can reproduce this
exact environment with two commands: `python -m venv .venv` and
`pip install -r requirements.txt`."

## 2. Clean, organised codebase

"The repo is split by concern rather than one flat folder:
- `data/` — the dataset generator and its documentation
- `ml/` — preprocessing, training, evaluation (split into subfolders
  even though they're currently empty, so the structure is ready as I
  build each piece)
- `api/` — the Python backend, not started yet
- `mobile/` — where the Kotlin app will live, opened directly as its
  own Android Studio project root
- `db/` — the PostgreSQL schema
- `docs/` — data dictionary and anything else worth documenting

Each folder has its own README explaining what belongs there, and the
root README has a status checklist so it's obvious at a glance what's
done and what isn't yet."

## 3. Git version control

"Everything is committed to GitHub — [github.com/D0nell/kq-crew-coordination].
I've got a `.gitignore` that deliberately excludes the virtual
environment, the generated dataset CSVs, and IDE-specific files
(Android Studio's `.idea/`, `.gradle/`, etc.) — so the repo only tracks
source code and configuration, not generated artifacts or local
machine noise. The dataset CSVs specifically live on Google Drive
rather than git, because they're regenerable from the script and too
large to sensibly version — only the generator script itself is
tracked, which is what actually needs to be reproducible."

## 4. Data, database, and resources prepared

"Kenya Airways didn't provide real operational data, so I built a
synthetic dataset generator instead of hand-faking CSVs. It's
calibrated to plausible Nairobi corridor distances and JKIA-scale
flight volume, and — this is the important part — the delay outcomes
aren't random. They're generated from a logistic function of traffic
congestion, weather, and rush hour, the same features my model is
meant to learn from. I ran a quick untuned model against it and got
macro-F1 around 0.33, well above the ~0.25 you'd get from random
guessing on 4 classes but nowhere near my 0.80 target — which is
correct, because that gap is supposed to be closed by my actual
modelling work later (feature engineering, tuning, class-weighting for
the rare CRITICAL delay class), not by the dataset being artificially
easy.

For the database, I've got a PostgreSQL schema (`db/schema.sql`)
matching the 7-table design from my proposal — Users, Crew_Profiles,
Flight_Schedules, Vehicles, Transit_Events, Mobilization_Log, Alerts —
and it's not just a file sitting in the repo. I've actually installed
PostgreSQL, created the database, and run the schema against it, so
all 7 tables exist and are queryable right now."

## 5. Automation for workflow and development management

"I've set up a GitHub Actions CI workflow that runs automatically on
every push to `main`. It spins up a clean machine, installs my
dependencies, runs the dataset generator as a smoke test, and checks
all 7 CSVs come out correctly. If I ever break the generation logic —
say, introduce a bug in the delay calculation — this catches it
immediately instead of me finding out weeks later. It's currently
green on the latest commit."

---

## If asked "what's next"

"Now that the environment, data, database, and automation are in
place, the next phase is: writing the preprocessing/feature engineering
pipeline in `ml/preprocessing/`, training the baseline Random Forest
model, then tuning XGBoost against it — followed by scaffolding the
FastAPI backend and starting the Kotlin app in Android Studio."