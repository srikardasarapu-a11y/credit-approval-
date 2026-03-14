"""
XGBoost credit scoring model trainer — v2
==========================================
Trains on synthetic data that now includes advanced bank metrics
(feat/advanced-bank-metrics):
  - average_daily_balance
  - average_transactional_balance
  - emi_estimated_monthly
  - unusual_count
  - bounce_count

Model saved as: models_ml/credit_model_v2.pkl
"""
import os
import sys
import logging

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split, StratifiedKFold
from sklearn.metrics import classification_report, roc_auc_score, accuracy_score
from imblearn.over_sampling import SMOTE
import optuna
from xgboost import XGBClassifier
import warnings

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Feature columns — v2 includes 5 new bank metrics
FEATURE_COLS = [
    # Core financial ratios
    "dscr", "de_ratio", "current_ratio", "interest_coverage",
    "gross_margin", "log_revenue", "research_risk",
    # --- Advanced bank metrics (new in v2) ---
    "average_daily_balance",
    "average_transactional_balance",
    "emi_estimated_monthly",
    "unusual_count",
    "bounce_count",
]

TARGET_COL = "good_credit"   # 1 = good (approved), 0 = bad (default)

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(_SCRIPT_DIR, "..", "models_ml", "credit_model_v2.pkl")
DATA_PATH  = os.path.join(_SCRIPT_DIR, "..", "data",      "training_data_v2.csv")


# ---------------------------------------------------------------------------
# Synthetic data generation
# ---------------------------------------------------------------------------

def generate_messy_synthetic_data(n: int = 20000) -> pd.DataFrame:
    """
    Generate realistic training data with heavy overlap and class imbalance
    (90% good, 10% bad).  Includes synthetic values for the 5 new bank metrics.

    Imputation defaults for missing real-world data:
        emi_estimated_monthly     → 0
        bounce_count              → 0
        unusual_count             → 0
        average_daily_balance     → imputed to median (~500,000)
        average_transactional_balance → same as average_daily_balance
    """
    np.random.seed(42)

    # --- Good credit (90%) ---
    n_good = int(n * 0.90)
    good = pd.DataFrame({
        "dscr":             np.random.normal(1.8, 0.5, n_good),
        "de_ratio":         np.random.normal(1.2, 0.8, n_good),
        "current_ratio":    np.random.normal(2.0, 0.6, n_good),
        "interest_coverage":np.random.normal(4.0, 1.5, n_good),
        "gross_margin":     np.random.normal(0.35, 0.15, n_good),
        "log_revenue":      np.random.normal(15,   2,    n_good),
        "research_risk":    np.random.beta(1, 5, n_good),   # low risk skew
        # Bank metrics — good applicants have healthy balances, low EMI, no bounces
        "average_daily_balance":         np.random.normal(600_000, 200_000, n_good).clip(0),
        "average_transactional_balance": np.random.normal(580_000, 210_000, n_good).clip(0),
        "emi_estimated_monthly":         np.random.uniform(0, 40_000, n_good),
        "unusual_count":                 np.random.poisson(0.5, n_good),
        "bounce_count":                  np.random.poisson(0.1, n_good),
        TARGET_COL: 1,
    })

    # --- Bad credit (10%) ---
    n_bad = n - n_good
    bad = pd.DataFrame({
        "dscr":             np.random.normal(0.9, 0.4, n_bad),
        "de_ratio":         np.random.normal(3.5, 1.5, n_bad),
        "current_ratio":    np.random.normal(0.8, 0.4, n_bad),
        "interest_coverage":np.random.normal(1.0, 0.8, n_bad),
        "gross_margin":     np.random.normal(0.10, 0.20, n_bad),
        "log_revenue":      np.random.normal(13,   2,    n_bad),
        "research_risk":    np.random.beta(5, 2, n_bad),   # high risk skew
        # Bank metrics — bad applicants have lower balances, higher EMI, more bounces
        "average_daily_balance":         np.random.normal(200_000, 150_000, n_bad).clip(0),
        "average_transactional_balance": np.random.normal(190_000, 160_000, n_bad).clip(0),
        "emi_estimated_monthly":         np.random.uniform(20_000, 150_000, n_bad),
        "unusual_count":                 np.random.poisson(2.0, n_bad),
        "bounce_count":                  np.random.poisson(1.2, n_bad),
        TARGET_COL: 0,
    })

    df = pd.concat([good, bad], ignore_index=True)

    # Inject noise to simulate real-world corruption
    df.loc[np.random.choice(df.index, int(n * 0.05)), "dscr"]     = np.random.uniform(0.1, 5.0, int(n * 0.05))
    df.loc[np.random.choice(df.index, int(n * 0.05)), "de_ratio"]  = np.random.uniform(0.1, 8.0, int(n * 0.05))

    # Ensure non-negative values for bank metrics
    for col in ["average_daily_balance", "average_transactional_balance",
                "emi_estimated_monthly", "unusual_count", "bounce_count"]:
        df[col] = df[col].clip(lower=0)

    df["unusual_count"] = df["unusual_count"].round().astype(int)
    df["bounce_count"]  = df["bounce_count"].round().astype(int)

    return df.sample(frac=1, random_state=42)


# ---------------------------------------------------------------------------
# Optuna objective
# ---------------------------------------------------------------------------

def objective(trial, X, y):
    """Optuna objective: 5-fold stratified CV → mean ROC-AUC."""
    param = {
        "n_estimators":      trial.suggest_int("n_estimators",   300, 1500),
        "max_depth":         trial.suggest_int("max_depth",        3,   12),
        "learning_rate":     trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
        "subsample":         trial.suggest_float("subsample",      0.6, 1.0),
        "colsample_bytree":  trial.suggest_float("colsample_bytree", 0.6, 1.0),
        "min_child_weight":  trial.suggest_int("min_child_weight", 1, 7),
        "gamma":             trial.suggest_float("gamma",          0,   0.5),
        "scale_pos_weight":  trial.suggest_float("scale_pos_weight", 0.5, 3.0),
        "use_label_encoder": False,
        "eval_metric":       "logloss",
        "random_state":      42,
        "n_jobs":            -1,
    }

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    scores = []
    for train_idx, val_idx in cv.split(X, y):
        X_tr, y_tr = X.iloc[train_idx], y.iloc[train_idx]
        X_v,  y_v  = X.iloc[val_idx],   y.iloc[val_idx]
        smote = SMOTE(random_state=42)
        X_tr_sm, y_tr_sm = smote.fit_resample(X_tr, y_tr)
        model = XGBClassifier(**param)
        model.fit(X_tr_sm, y_tr_sm)
        preds = model.predict_proba(X_v)[:, 1]
        scores.append(roc_auc_score(y_v, preds))

    return float(np.mean(scores))


# ---------------------------------------------------------------------------
# Main training routine
# ---------------------------------------------------------------------------

def train():
    logger.info("Generating 20,000 synthetic samples with extended bank features...")
    df = generate_messy_synthetic_data(20_000)
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    df.to_csv(DATA_PATH, index=False)
    logger.info(f"Training data saved: {DATA_PATH}")

    X = df[FEATURE_COLS]
    y = df[TARGET_COL]

    # Impute any NaNs with sensible defaults
    impute_defaults = {
        "emi_estimated_monthly":         0,
        "bounce_count":                  0,
        "unusual_count":                 0,
        "average_daily_balance":         X["average_daily_balance"].median(),
        "average_transactional_balance": X["average_transactional_balance"].median(),
    }
    X = X.fillna(impute_defaults)

    # Hold out 20% for evaluation (SMOTE never touches this)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    logger.info("Running Optuna HPO (15 trials)...")
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(direction="maximize")
    study.optimize(lambda trial: objective(trial, X_train, y_train), n_trials=15)

    best_params = study.best_params
    best_params.update({"use_label_encoder": False, "eval_metric": "logloss", "random_state": 42})
    logger.info(f"Best params: {best_params}")

    logger.info("Applying SMOTE to full training set...")
    smote = SMOTE(random_state=42)
    X_train_sm, y_train_sm = smote.fit_resample(X_train, y_train)

    logger.info("Training final XGBoost model (v2, 12 features)...")
    model = XGBClassifier(**best_params)
    model.fit(X_train_sm, y_train_sm)

    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]
    auc    = roc_auc_score(y_test, y_prob)
    acc    = accuracy_score(y_test, y_pred)

    logger.info("\n--- FINAL MODEL EVALUATION ON UNSEEN TEST DATA ---")
    logger.info("\n" + classification_report(y_test, y_pred))
    logger.info(f"Accuracy: {acc:.4f}  ROC-AUC: {auc:.4f}")

    if auc > 0.80:
        logger.info("✅ AUC target (>0.80) achieved.")
    else:
        logger.warning("⚠ AUC < 0.80. Consider adding more features or data.")

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    logger.info(f"Model saved: {MODEL_PATH}")
    return model


if __name__ == "__main__":
    train()
