# Chapter 4 diagram updates (design changes in Sprint II)

What changed from the Sprint I design:
- A **predictions** table stores every score (one row per transit, replaced on re-score).
- The **alerts** table gains `delay_probability`, `source` (historical or model), `model_version` and `resolved_at`. A partial unique index allows one model alert per transit.
- Alerts are produced by the model through the API, not only loaded from history.
- A **web dispatcher dashboard** is the first interface; the Kotlin app follows in Sprint III.

## System architecture

```mermaid
flowchart LR
  D[Dispatcher browser<br/>dashboard.html] -->|HTTP JSON| A[FastAPI<br/>api/main.py]
  A --> S[Scoring service<br/>api/scoring.py]
  S -->|features SQL| P[(PostgreSQL)]
  S -->|loads| M[[XGBoost model<br/>xgb_final_v1.pkl]]
  S -->|predictions, alerts| P
  A -->|queue, alerts, summary| P
  K[Kotlin crew app<br/>Sprint III] -.-> A
```

## Core workflow (sequence)

```mermaid
sequenceDiagram
  actor Disp as Dispatcher
  participant UI as Dashboard
  participant API as FastAPI
  participant DB as PostgreSQL
  participant ML as XGBoost model
  Disp->>UI: Open dashboard
  UI->>API: GET /api/transits
  API->>DB: test-split transits
  DB-->>UI: queue
  Disp->>UI: Score these transits
  UI->>API: POST /api/transits/score-batch
  API->>DB: pre-trip features
  API->>ML: predict_proba
  API->>DB: upsert predictions, alerts (p >= threshold)
  API-->>UI: results
  Disp->>UI: Resolve alert
  UI->>API: PATCH /api/alerts/{id}/resolve
  API->>DB: set resolved, resolved_at
```

## Data model additions

```mermaid
erDiagram
  TRANSIT_EVENTS ||--o| PREDICTIONS : "scored as"
  TRANSIT_EVENTS ||--o{ ALERTS : "raises"
  PREDICTIONS {
    int prediction_id PK
    int transit_id FK "unique"
    numeric delay_probability
    bool predicted_delayed
    varchar risk_level
    varchar model_version
    timestamp scored_at
  }
  ALERTS {
    int alert_id PK
    int transit_id FK
    varchar source "historical or model"
    numeric delay_probability
    varchar model_version
    bool resolved
    timestamp resolved_at
  }
```

## Alert lifecycle

```mermaid
stateDiagram-v2
  [*] --> Open: scored, p >= threshold
  Open --> Resolved: dispatcher resolves
  Open --> Resolved: re-scored below threshold (auto)
  Resolved --> [*]
```
A resolved alert is not reopened by a re-score at or above the threshold; the dispatcher's decision stands.
