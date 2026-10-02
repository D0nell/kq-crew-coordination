"""
Trains the final XGBoost delay-risk model (binary DELAYED/NOT_DELAYED,
tuned via grid search, balanced with SMOTE). Mirrors the exploratory
work in train_xgboost.ipynb, packaged as a reusable script.

Usage:
    python ml/training/train_xgboost.py --data-dir data/output --out models/xgb_final_v1.pkl

For a quick run without the (slow) grid search, add --skip-tuning to
use reasonable default hyperparameters instead.
"""

import argparse
import os
import sys

import joblib
from imblearn.over_sampling import SMOTE
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import GridSearchCV
from xgboost import XGBClassifier

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from ml.preprocessing.load_data import FEATURE_COLS, load_and_preprocess

DEFAULT_PARAMS = {
    "max_depth": 3,
    "learning_rate": 0.01,
    "n_estimators": 500,
    "min_child_weight": 1,
}

PARAM_GRID = {
    "max_depth": [3, 5, 7, 9],
    "learning_rate": [0.01, 0.05, 0.1, 0.2],
    "n_estimators": [200, 300, 500],
    "min_child_weight": [1, 3, 5],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data/output")
    ap.add_argument("--out", default="models/xgb_final_v1.pkl")
    ap.add_argument("--skip-tuning", action="store_true",
                     help="Use DEFAULT_PARAMS instead of running grid search (much faster)")
    args = ap.parse_args()

    print("Loading and preprocessing data...")
    train_df, val_df, test_df, encoders = load_and_preprocess(args.data_dir)

    X_train, y_train = train_df[FEATURE_COLS], train_df["delay_binary"]
    X_test, y_test = test_df[FEATURE_COLS], test_df["delay_binary"]

    if args.skip_tuning:
        print(f"Skipping grid search, using default params: {DEFAULT_PARAMS}")
        best_params = DEFAULT_PARAMS
    else:
        print("Running grid search (this can take several minutes)...")
        grid = GridSearchCV(
            XGBClassifier(random_state=42, eval_metric="logloss"),
            PARAM_GRID, scoring="f1", cv=3, n_jobs=-1, verbose=1,
        )
        grid.fit(X_train, y_train)
        best_params = grid.best_params_
        print(f"Best params: {best_params}")
        print(f"Best CV F1: {grid.best_score_:.4f}")

    print("Applying SMOTE to training set...")
    sm = SMOTE(random_state=42)
    X_train_res, y_train_res = sm.fit_resample(X_train, y_train)

    print("Training final model...")
    model = XGBClassifier(**best_params, random_state=42, eval_metric="logloss")
    model.fit(X_train_res, y_train_res)

    pred = model.predict(X_test)
    print(f"\nTest F1 (DELAYED class): {f1_score(y_test, pred):.4f}")
    print(classification_report(y_test, pred))

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    joblib.dump({"model": model, "encoders": encoders, "params": best_params}, args.out)
    print(f"\nSaved model + encoders to {args.out}")


if __name__ == "__main__":
    main()
