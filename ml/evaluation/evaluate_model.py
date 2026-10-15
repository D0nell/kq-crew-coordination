"""
Baseline evaluation of the delay-risk model.

Data discipline: the model is trained on the TRAIN split only. The alert threshold is
chosen on the VALIDATION split. The TEST split is used once, at the end, to report
the numbers. Nothing here is tuned on test.

Target: DELAYED = delay_risk_class in (HIGH, CRITICAL), i.e. a delay of 20+ minutes.

Usage:
    python ml/evaluation/evaluate_model.py --data-dir data/output --model models/xgb_final_v1.pkl
Writes docs/evaluation_results.md
"""

import argparse
import os
import sys

import joblib
import numpy as np
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score, precision_score,
                             recall_score, roc_auc_score)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from ml.preprocessing.load_data import FEATURE_COLS, load_and_preprocess  # noqa: E402


def metrics(y, p, thr):
    yh = (p >= thr).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, yh, labels=[0, 1]).ravel()
    return {"thr": thr, "accuracy": accuracy_score(y, yh), "precision": precision_score(y, yh, zero_division=0),
            "recall": recall_score(y, yh, zero_division=0), "f1": f1_score(y, yh, zero_division=0),
            "tp": int(tp), "fp": int(fp), "fn": int(fn), "tn": int(tn)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data/output")
    ap.add_argument("--model", default="models/xgb_final_v1.pkl")
    ap.add_argument("--out", default="docs/evaluation_results.md")
    a = ap.parse_args()

    train, val, test, _ = load_and_preprocess(a.data_dir)
    model = joblib.load(a.model)["model"]
    Xv, yv = val[FEATURE_COLS].values, val["delay_binary"].values
    Xt, yt = test[FEATURE_COLS].values, test["delay_binary"].values
    pv, pt = model.predict_proba(Xv)[:, 1], model.predict_proba(Xt)[:, 1]

    # Threshold chosen on validation only.
    grid = np.round(np.arange(0.20, 0.80, 0.05), 2)
    sweep_val = [metrics(yv, pv, t) for t in grid]
    best_thr = max(sweep_val, key=lambda m: m["f1"])["thr"]

    at_default_val, at_best_val = metrics(yv, pv, 0.5), metrics(yv, pv, best_thr)
    at_default_test, at_best_test = metrics(yt, pt, 0.5), metrics(yt, pt, best_thr)
    auc_val, auc_test = roc_auc_score(yv, pv), roc_auc_score(yt, pt)

    # Baselines on test: what a model has to beat.
    rate_train = train["delay_binary"].mean()
    flag_all = metrics(yt, np.ones(len(yt)), 0.5)
    rng = np.random.default_rng(42)
    rand = metrics(yt, rng.random(len(yt)), 1 - rate_train)  # random flags at the training base rate
    hist_cut = float(np.median(train["historical_avg_delay_min"]))
    rule = metrics(yt, (test["historical_avg_delay_min"].values > hist_cut).astype(float), 0.5)

    def row(name, m):
        return (f"| {name} | {m['accuracy']:.3f} | {m['precision']:.3f} | {m['recall']:.3f} | {m['f1']:.3f} | "
                f"{m['tp']} / {m['fp']} / {m['fn']} / {m['tn']} |")

    L = ["# Baseline evaluation", "",
         f"Train {len(train)} / validation {len(val)} / test {len(test)} transits (stratified 80/10/10, "
         "split fixed in the dataset). Target: delayed = HIGH or CRITICAL (delay of 20+ minutes). "
         f"Positive rate on train: {rate_train:.3f}.", "",
         "The threshold is chosen on **validation**. The **test** split is only used to report the result.", "",
         "## Test-set results", "",
         "| Approach | Accuracy | Precision | Recall | F1 (delayed) | TP / FP / FN / TN |",
         "|---|---|---|---|---|---|",
         row(f"XGBoost, threshold 0.50 (system default)", at_default_test),
         row(f"XGBoost, threshold {best_thr:.2f} (best on validation)", at_best_test),
         row("Baseline: flag every transit", flag_all),
         row("Baseline: random flags at the training base rate", rand),
         row(f"Baseline: rule 'historical average delay > {hist_cut:.1f} min'", rule), "",
         f"ROC-AUC: validation {auc_val:.3f}, test {auc_test:.3f}.", "",
         "## Threshold sweep (validation split)", "",
         "| Threshold | Precision | Recall | F1 |", "|---|---|---|---|"]
    L += [f"| {m['thr']:.2f} | {m['precision']:.3f} | {m['recall']:.3f} | {m['f1']:.3f} |" for m in sweep_val]
    L += ["", f"Validation F1 at the default threshold 0.50: {at_default_val['f1']:.3f}; "
              f"at the chosen {best_thr:.2f}: {at_best_val['f1']:.3f}.", "",
          "## Reading the numbers", "",
          "- On this dataset the delay outcome has a built-in random component, so no model can score "
          "F1 = 1.0. `data/validate_dataset.py` and the ceiling analysis put the best achievable F1 for the "
          "delayed class at roughly 0.645 (flagging everything scores about 0.58). The original 0.80 target "
          "is therefore not reachable on this data, and results should be judged against the baselines above.",
          f"- On test, the model's F1 ({at_default_test['f1']:.3f}) is only {at_default_test['f1'] - flag_all['f1']:+.3f} "
          "versus flagging every transit, because F1 on the delayed class rewards recall. What the model adds is "
          "discrimination: it cuts false alarms (precision and accuracy are higher) while still catching about "
          f"{at_default_test['recall']:.0%} of delays, and it beats the single-feature rule "
          f"(ROC-AUC {auc_test:.2f}). Flagging everything has no discrimination at all.",
          "- Accuracy alone is misleading here: about 41% of transits are delayed, so the baselines are the "
          "fair comparison.",
          "- These are results on **synthetic** data and show that the pipeline works end to end. They are "
          "not evidence of accuracy on real Kenya Airways operations."]
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    open(a.out, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
