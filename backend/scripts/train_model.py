"""
XGBoost credit scoring model trainer.
Uses synthetic data modelled on realistic financial ratios.
Replace data/training_data.csv with real labelled loan data for production.
"""
import os
import sys
import logging

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

FEATURE_COLS = [
    "dscr", "de_ratio", "current_ratio", "interest_coverage",
    "gross_margin", "log_revenue", "research_risk"
]
TARGET_COL = "good_credit"   # 1 = good (approved), 0 = bad (default)
MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "models_ml", "credit_model.pkl")
DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "training_data.csv")


def generate_synthetic_data(n: int = 10000) -> pd.DataFrame:
    """Generate synthetic training data with realistic financial ratios."""
    np.random.seed(42)

    # Good credit (70% of records)
    n_good = int(n * 0.70)
    good = pd.DataFrame({
        "dscr": np.random.uniform(1.1, 3.5, n_good),
        "de_ratio": np.random.uniform(0.1, 2.5, n_good),
        "current_ratio": np.random.uniform(1.2, 3.0, n_good),
        "interest_coverage": np.random.uniform(1.5, 8.0, n_good),
        "gross_margin": np.random.uniform(0.15, 0.60, n_good),
        "log_revenue": np.random.uniform(12, 20, n_good),
        "research_risk": np.random.uniform(0.0, 0.30, n_good),
        TARGET_COL: 1,
    })

    # Bad credit (30%)
    n_bad = n - n_good
    bad = pd.DataFrame({
        "dscr": np.random.uniform(0.3, 1.2, n_bad),
        "de_ratio": np.random.uniform(2.0, 8.0, n_bad),
        "current_ratio": np.random.uniform(0.3, 1.5, n_bad),
        "interest_coverage": np.random.uniform(0.2, 2.5, n_bad),
        "gross_margin": np.random.uniform(-0.10, 0.20, n_bad),
        "log_revenue": np.random.uniform(10, 17, n_bad),
        "research_risk": np.random.uniform(0.20, 1.0, n_bad),
        TARGET_COL: 0,
    })

    df = pd.concat([good, bad], ignore_index=True).sample(frac=1, random_state=42)
    return df


def train():
    # Load or generate data
    if os.path.exists(DATA_PATH):
        logger.info(f"Loading training data from {DATA_PATH}")
        df = pd.read_csv(DATA_PATH)
    else:
        logger.info("Generating synthetic training data (10000 samples)...")
        df = generate_synthetic_data(10000)
        os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
        df.to_csv(DATA_PATH, index=False)
        logger.info(f"Saved to {DATA_PATH}")

    X = df[FEATURE_COLS]
    y = df[TARGET_COL]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    model = XGBClassifier(
        n_estimators=1000,
        max_depth=8,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        use_label_encoder=False,
        eval_metric="logloss",
        random_state=42,
    )
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]

    logger.info("\n" + classification_report(y_test, y_pred))
    logger.info(f"ROC-AUC: {roc_auc_score(y_test, y_prob):.4f}")

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    logger.info(f"Model saved: {MODEL_PATH}")


if __name__ == "__main__":
    train()
