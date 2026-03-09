import os
import sys
import logging
import joblib
import pandas as pd
import numpy as np
from sklearn.metrics import classification_report, roc_auc_score, accuracy_score, confusion_matrix

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

FEATURE_COLS = [
    "dscr", "de_ratio", "current_ratio", "interest_coverage",
    "gross_margin", "log_revenue", "research_risk"
]
TARGET_COL = "good_credit"
MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "models_ml", "credit_model.pkl")

def generate_unseen_test_data(n: int = 5000) -> pd.DataFrame:
    """Generate a brand new batch of unseen test data to evaluate the model."""
    np.random.seed(999) # Different seed from training
    
    n_good = int(n * 0.90)
    good = pd.DataFrame({
        "dscr": np.random.normal(1.8, 0.5, n_good),
        "de_ratio": np.random.normal(1.2, 0.8, n_good),
        "current_ratio": np.random.normal(2.0, 0.6, n_good),
        "interest_coverage": np.random.normal(4.0, 1.5, n_good),
        "gross_margin": np.random.normal(0.35, 0.15, n_good),
        "log_revenue": np.random.normal(15, 2, n_good),
        "research_risk": np.random.beta(1, 5, n_good),
        TARGET_COL: 1,
    })

    n_bad = n - n_good
    bad = pd.DataFrame({
        "dscr": np.random.normal(0.9, 0.4, n_bad),
        "de_ratio": np.random.normal(3.5, 1.5, n_bad),
        "current_ratio": np.random.normal(0.8, 0.4, n_bad),
        "interest_coverage": np.random.normal(1.0, 0.8, n_bad),
        "gross_margin": np.random.normal(0.10, 0.20, n_bad),
        "log_revenue": np.random.normal(13, 2, n_bad),
        "research_risk": np.random.beta(5, 2, n_bad),
        TARGET_COL: 0,
    })

    df = pd.concat([good, bad], ignore_index=True)
    df.loc[np.random.choice(df.index, int(n * 0.05)), "dscr"] = np.random.uniform(0.1, 5.0, int(n * 0.05))
    df.loc[np.random.choice(df.index, int(n * 0.05)), "de_ratio"] = np.random.uniform(0.1, 8.0, int(n * 0.05))
    return df.sample(frac=1, random_state=999)

def test():
    if not os.path.exists(MODEL_PATH):
        logger.error(f"Model not found at {MODEL_PATH}. Please train the model first.")
        return

    logger.info("Loading saved XGBoost model...")
    model = joblib.load(MODEL_PATH)

    logger.info("\nGenerating 5,000 brand new unseen loan applications...")
    df = generate_unseen_test_data(5000)
    
    X_test = df[FEATURE_COLS]
    y_test = df[TARGET_COL]

    logger.info("Running predictions on the unseen data...\n")
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]

    acc = accuracy_score(y_test, y_pred)
    auc = roc_auc_score(y_test, y_prob)
    cm = confusion_matrix(y_test, y_pred)
    
    logger.info("=" * 40)
    logger.info("         FINAL TEST RESULTS         ")
    logger.info("=" * 40)
    logger.info(f"Total Samples Passed: {len(df):,}")
    logger.info(f"Accuracy:           {acc * 100:.2f}%")
    logger.info(f"ROC-AUC Score:      {auc * 100:.2f}%")
    logger.info("-" * 40)
    
    logger.info("Classification Report:")
    logger.info("\n" + classification_report(y_test, y_pred, target_names=["Bad Credit (0)", "Good Credit (1)"]))

    logger.info("Confusion Matrix:")
    logger.info(f"True Negatives (Correctly rejected bad loans):   {cm[0][0]}")
    logger.info(f"False Positives (Incorrectly approved bad loans):  {cm[0][1]}")
    logger.info(f"False Negatives (Incorrectly rejected good loans): {cm[1][0]}")
    logger.info(f"True Positives (Correctly approved good loans):    {cm[1][1]}")
    logger.info("=" * 40)

if __name__ == "__main__":
    test()
