# Model Results Log — Baseline Delay Prediction

Tracks each modelling iteration against `Transit_Events.csv`, with
reasoning for why each change was made. Source: `ml/training/train_xgboost.ipynb`.

## Setup
- Features: `is_weekday`, `is_rush_hour`, `weather_flag`,
  `traffic_congestion_index`, `historical_avg_delay_min`, `distance_km`,
  `hour_of_day`, `day_of_week`, `capacity`, plus label-encoded
  `corridor`, `rank`, `base_location`, `vehicle_type`, `destination`
  (merged in from `Crew_Profiles`, `Vehicles`, `Flight_Schedules` —
  deliberately excluding `Mobilization_Log`/`Alerts` to avoid label
  leakage, since those record what happened during/after the transit).
- Split: stratified 80/10/10 train/val/test (baked into the dataset's
  `split` column, seed 42).

## Iteration log

| # | Model | Target framing | Macro F1 | Notes |
|---|---|---|---|---|
| 1 | Random Forest (300 trees, `class_weight=balanced`) | 4-class (LOW/MEDIUM/HIGH/CRITICAL) | 0.333 | Baseline. CRITICAL recall ≈ 0.01 — essentially undetected. |
| 2 | XGBoost (default params) | 4-class | 0.345 | Marginal gain over RF — confirms the bottleneck is problem framing, not model choice. |
| 3 | XGBoost (default params) | **Binary** (DELAYED = HIGH+CRITICAL vs NOT_DELAYED) | 0.63 (macro) / 0.53 (DELAYED F1) | Reframing to the operationally meaningful question closed most of the gap in one step. |
| 4 | XGBoost + GridSearchCV (144 combos, 3-fold CV) | Binary | 0.67 (macro) / 0.58 (DELAYED F1) | Best params: `max_depth=3, learning_rate=0.01, n_estimators=500, min_child_weight=1`. Precision on DELAYED: 0.63. |
| 5 | XGBoost (tuned params) + SMOTE oversampling | Binary | 0.66 (macro) / **0.62 (DELAYED F1)** | Recall on DELAYED jumps 0.53 → 0.67 (fewer missed delays), precision drops 0.63 → 0.57 (more false alarms). **Selected as final model** — see reasoning below. |

## Why the binary + SMOTE model was selected over the higher-macro-F1 tuned-only version

Macro F1 alone (0.67 tuned-only vs 0.66 tuned+SMOTE) doesn't capture the
actual cost asymmetry in this system: missing a real delay (false
negative) means a crew member is late without warning, which risks a
flight; a false alarm just means a dispatcher checks on someone who
turns out to be fine. Recall on the DELAYED class matters more than
precision here, which favors SMOTE (recall 0.67) over the tuned-only
version (recall 0.53), even though its macro F1 is marginally lower.

## Feature importance (Random Forest baseline)