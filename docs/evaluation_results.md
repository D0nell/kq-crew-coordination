# Baseline evaluation

Train 4799 / validation 598 / test 603 transits (stratified 80/10/10, split fixed in the dataset). Target: delayed = HIGH or CRITICAL (delay of 20+ minutes). Positive rate on train: 0.407.

The threshold is chosen on **validation**. The **test** split is only used to report the result.

## Test-set results

| Approach | Accuracy | Precision | Recall | F1 (delayed) | TP / FP / FN / TN |
|---|---|---|---|---|---|
| XGBoost, threshold 0.50 (system default) | 0.630 | 0.537 | 0.649 | 0.588 | 159 / 137 / 86 / 221 |
| XGBoost, threshold 0.40 (best on validation) | 0.582 | 0.491 | 0.780 | 0.603 | 191 / 198 / 54 / 160 |
| Baseline: flag every transit | 0.406 | 0.406 | 1.000 | 0.578 | 245 / 358 / 0 / 0 |
| Baseline: random flags at the training base rate | 0.509 | 0.397 | 0.400 | 0.398 | 98 / 149 / 147 / 209 |
| Baseline: rule 'historical average delay > 13.8 min' | 0.592 | 0.498 | 0.637 | 0.559 | 156 / 157 / 89 / 201 |

ROC-AUC: validation 0.723, test 0.676.

## Threshold sweep (validation split)

| Threshold | Precision | Recall | F1 |
|---|---|---|---|
| 0.20 | 0.436 | 0.955 | 0.598 |
| 0.25 | 0.449 | 0.947 | 0.609 |
| 0.30 | 0.475 | 0.922 | 0.627 |
| 0.35 | 0.486 | 0.893 | 0.629 |
| 0.40 | 0.515 | 0.832 | 0.636 |
| 0.45 | 0.533 | 0.762 | 0.627 |
| 0.50 | 0.571 | 0.689 | 0.625 |
| 0.55 | 0.589 | 0.598 | 0.593 |
| 0.60 | 0.612 | 0.537 | 0.572 |
| 0.65 | 0.667 | 0.443 | 0.532 |
| 0.70 | 0.720 | 0.295 | 0.419 |
| 0.75 | 1.000 | 0.037 | 0.071 |
| 0.80 | 0.000 | 0.000 | 0.000 |

Validation F1 at the default threshold 0.50: 0.625; at the chosen 0.40: 0.636.

## Reading the numbers

- On this dataset the delay outcome has a built-in random component, so no model can score F1 = 1.0. `data/validate_dataset.py` and the ceiling analysis put the best achievable F1 for the delayed class at roughly 0.645 (flagging everything scores about 0.58). The original 0.80 target is therefore not reachable on this data, and results should be judged against the baselines above.
- On test, the model's F1 (0.588) is only +0.010 versus flagging every transit, because F1 on the delayed class rewards recall. What the model adds is discrimination: it cuts false alarms (precision and accuracy are higher) while still catching about 65% of delays, and it beats the single-feature rule (ROC-AUC 0.68). Flagging everything has no discrimination at all.
- Accuracy alone is misleading here: about 41% of transits are delayed, so the baselines are the fair comparison.
- These are results on **synthetic** data and show that the pipeline works end to end. They are not evidence of accuracy on real Kenya Airways operations.
