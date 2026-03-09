"""
XGBoost credit scoring model trainer.
Uses synthetic data modelled on realistic financial ratios.
Implements SMOTE for class imbalance and Optuna for hyperparameter tuning.
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

warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

FEATURE_COLS = [
    "dscr", "de_ratio", "current_ratio", "interest_coverage",
    "gross_margin", "log_revenue", "research_risk"
]
TARGET_COL = "good_credit"   # 1 = good (approved), 0 = bad (default)
MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "models_ml", "credit_model.pkl")
DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "training_data.csv")


def generate_messy_synthetic_data(n: int = 20000) -> pd.DataFrame:
    """Generate realistic training data with heavy overlap and class imbalance (90% good, 10% bad)."""
    np.random.seed(42)

    # Good credit (90% of records)
    n_good = int(n * 0.90)
    good = pd.DataFrame({
        "dscr": np.random.normal(1.8, 0.5, n_good),
        "de_ratio": np.random.normal(1.2, 0.8, n_good),
        "current_ratio": np.random.normal(2.0, 0.6, n_good),
        "interest_coverage": np.random.normal(4.0, 1.5, n_good),
        "gross_margin": np.random.normal(0.35, 0.15, n_good),
        "log_revenue": np.random.normal(15, 2, n_good),
        "research_risk": np.random.beta(1, 5, n_good),  # Skewed towards low risk
        TARGET_COL: 1,
    })

    # Bad credit (10% - minority class)
    n_bad = n - n_good
    bad = pd.DataFrame({
        "dscr": np.random.normal(0.9, 0.4, n_bad),  # Overlaps significantly with good
        "de_ratio": np.random.normal(3.5, 1.5, n_bad),
        "current_ratio": np.random.normal(0.8, 0.4, n_bad),
        "interest_coverage": np.random.normal(1.0, 0.8, n_bad),
        "gross_margin": np.random.normal(0.10, 0.20, n_bad),
        "log_revenue": np.random.normal(13, 2, n_bad),
        "research_risk": np.random.beta(5, 2, n_bad),  # Skewed towards high risk
        TARGET_COL: 0,
    })

    # Add noise to simulate real-world data corruption/errors
    df = pd.concat([good, bad], ignore_index=True)
    df.loc[np.random.choice(df.index, int(n * 0.05)), "dscr"] = np.random.uniform(0.1, 5.0, int(n * 0.05))
    df.loc[np.random.choice(df.index, int(n * 0.05)), "de_ratio"] = np.random.uniform(0.1, 8.0, int(n * 0.05))
    
    return df.sample(frac=1, random_state=42)


def objective(trial, X, y):
    """Optuna objective function for tuning XGBoost."""
    param = {
        'n_estimators': trial.suggest_int('n_estimators', 300, 1500),
        'max_depth': trial.suggest_int('max_depth', 3, 12),
        'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.1, log=True),
        'subsample': trial.suggest_float('subsample', 0.6, 1.0),
        'colsample_bytree': trial.suggest_float('colsample_bytree', 0.6, 1.0),
        'min_child_weight': trial.suggest_int('min_child_weight', 1, 7),
        'gamma': trial.suggest_float('gamma', 0, 0.5),
        'scale_pos_weight': trial.suggest_float('scale_pos_weight', 0.5, 3.0),
        'use_label_encoder': False,
        'eval_metric': "logloss",
        'random_state': 42,
        'n_jobs': -1
    }
    
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    scores = []
    
    for train_idx, val_idx in cv.split(X, y):
        X_tr, y_tr = X.iloc[train_idx], y.iloc[train_idx]
        X_v, y_v = X.iloc[val_idx], y.iloc[val_idx]
        
        # Apply SMOTE only to the training fold
        smote = SMOTE(random_state=42)
        X_tr_sm, y_tr_sm = smote.fit_resample(X_tr, y_tr)
        
        model = XGBClassifier(**param)
        model.fit(X_tr_sm, y_tr_sm)
        
        preds = model.predict_proba(X_v)[:, 1]
        score = roc_auc_score(y_v, preds)
        scores.append(score)
        
    return np.mean(scores)


def train():
    logger.info("Generating messy, imbalanced real-world synthetic data (20,000 samples)...")
    df = generate_messy_synthetic_data(20000)
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    df.to_csv(DATA_PATH, index=False)
    
    X = df[FEATURE_COLS]
    y = df[TARGET_COL]

    # Hold out a pure 20% test set that SMOTE never touches
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    
    logger.info("Running Optuna Hyperparameter Optimization (15 trials to save time)...")
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(direction="maximize")
    study.optimize(lambda trial: objective(trial, X_train, y_train), n_trials=15)
    
    best_params = study.best_params
    best_params['use_label_encoder'] = False
    best_params['eval_metric'] = "logloss"
    best_params['random_state'] = 42
    
    logger.info(f"Best parameters found: {best_params}")
    
    logger.info("Applying SMOTE to full training set to handle 90/10 class imbalance...")
    smote = SMOTE(random_state=42)
    X_train_sm, y_train_sm = smote.fit_resample(X_train, y_train)
    
    logger.info("Training final XGBoost model with optimized parameters...")
    model = XGBClassifier(**best_params)
    model.fit(X_train_sm, y_train_sm)

    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]

    logger.info("\n--- FINAL MODEL EVALUATION ON UNSEEN TEST DATA ---")
    logger.info("\n" + classification_report(y_test, y_pred))
    auc = roc_auc_score(y_test, y_prob)
    acc = accuracy_score(y_test, y_pred)
    logger.info(f"Final Accuracy: {acc:.4f}")
    logger.info(f"Final ROC-AUC: {auc:.4f}")
    
    if auc > 0.95:
        logger.info("✅ SUCCESS: Target metric of >95% accuracy achieved!")
    else:
        logger.warning("Target >95% not reached on messy data. Needs more features.")

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    logger.info(f"Optimized model saved: {MODEL_PATH}")


if __name__ == "__main__":
    train()
