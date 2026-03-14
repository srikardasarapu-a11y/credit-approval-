"""
Feature Importance Report — credit_model_v2
============================================
Loads the v2 XGBoost model, computes SHAP values on a synthetic test set,
and prints the top-10 features by mean |SHAP| value.

Also reports what fraction of predicted rejections have at least one new
bank-metric feature in their top-3 SHAP contributors (interpretability audit).

Usage:
    cd backend
    python scripts/feature_importance_report.py
"""
import os
import sys
import logging
import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(_SCRIPT_DIR, "..", "models_ml", "credit_model_v2.pkl")

FEATURE_COLS = [
    "dscr", "de_ratio", "current_ratio", "interest_coverage",
    "gross_margin", "log_revenue", "research_risk",
    "average_daily_balance", "average_transactional_balance",
    "emi_estimated_monthly", "unusual_count", "bounce_count",
]

BANK_METRIC_FEATURES = {
    "average_daily_balance", "average_transactional_balance",
    "emi_estimated_monthly", "unusual_count", "bounce_count",
}


def generate_test_data(n: int = 5000) -> pd.DataFrame:
    """Generate a held-out test set matching training distribution."""
    np.random.seed(999)  # different seed from training

    n_good = int(n * 0.90)
    n_bad  = n - n_good

    good = pd.DataFrame({
        "dscr": np.random.normal(1.8, 0.5, n_good),
        "de_ratio": np.random.normal(1.2, 0.8, n_good),
        "current_ratio": np.random.normal(2.0, 0.6, n_good),
        "interest_coverage": np.random.normal(4.0, 1.5, n_good),
        "gross_margin": np.random.normal(0.35, 0.15, n_good),
        "log_revenue": np.random.normal(15, 2, n_good),
        "research_risk": np.random.beta(1, 5, n_good),
        "average_daily_balance": np.random.normal(600_000, 200_000, n_good).clip(0),
        "average_transactional_balance": np.random.normal(580_000, 210_000, n_good).clip(0),
        "emi_estimated_monthly": np.random.uniform(0, 40_000, n_good),
        "unusual_count": np.random.poisson(0.5, n_good).clip(0),
        "bounce_count": np.random.poisson(0.1, n_good).clip(0),
        "good_credit": 1,
    })

    bad = pd.DataFrame({
        "dscr": np.random.normal(0.9, 0.4, n_bad),
        "de_ratio": np.random.normal(3.5, 1.5, n_bad),
        "current_ratio": np.random.normal(0.8, 0.4, n_bad),
        "interest_coverage": np.random.normal(1.0, 0.8, n_bad),
        "gross_margin": np.random.normal(0.10, 0.20, n_bad),
        "log_revenue": np.random.normal(13, 2, n_bad),
        "research_risk": np.random.beta(5, 2, n_bad),
        "average_daily_balance": np.random.normal(200_000, 150_000, n_bad).clip(0),
        "average_transactional_balance": np.random.normal(190_000, 160_000, n_bad).clip(0),
        "emi_estimated_monthly": np.random.uniform(20_000, 150_000, n_bad),
        "unusual_count": np.random.poisson(2.0, n_bad).clip(0),
        "bounce_count": np.random.poisson(1.2, n_bad).clip(0),
        "good_credit": 0,
    })

    return pd.concat([good, bad], ignore_index=True).sample(frac=1, random_state=999)


def main():
    try:
        import joblib, shap
    except ImportError:
        logger.error("joblib / shap not installed. Run: pip install joblib shap")
        sys.exit(1)

    if not os.path.exists(MODEL_PATH):
        logger.error(f"Model not found: {MODEL_PATH}\nTrain it first: python scripts/train_model.py")
        sys.exit(1)

    logger.info(f"Loading model: {MODEL_PATH}")
    model = joblib.load(MODEL_PATH)

    # Check feature count matches
    expected_feats = len(FEATURE_COLS)
    model_feats = model.n_features_in_ if hasattr(model, "n_features_in_") else None
    if model_feats and model_feats != expected_feats:
        logger.warning(
            f"Model expects {model_feats} features but report uses {expected_feats}. "
            "This may be a v1 model — retrain with train_model.py"
        )
        feat_cols = FEATURE_COLS[:model_feats]
    else:
        feat_cols = FEATURE_COLS

    logger.info("Generating 5,000 test samples...")
    df = generate_test_data(5000)
    X  = df[feat_cols]

    logger.info("Computing SHAP values (this may take a few seconds)...")
    explainer  = shap.TreeExplainer(model)
    shap_vals  = explainer.shap_values(X)
    if isinstance(shap_vals, list):
        shap_vals = shap_vals[1]   # class 1

    # Mean |SHAP| per feature
    mean_abs_shap = np.abs(shap_vals).mean(axis=0)
    feat_importance = sorted(
        zip(feat_cols, mean_abs_shap),
        key=lambda x: x[1],
        reverse=True,
    )

    logger.info("\n" + "="*50)
    logger.info("   TOP-10 FEATURES BY MEAN |SHAP|")
    logger.info("="*50)
    for rank, (feat, val) in enumerate(feat_importance[:10], 1):
        marker = "🆕" if feat in BANK_METRIC_FEATURES else "  "
        logger.info(f"  {rank:2}. {marker} {feat:<40} {val:.5f}")
    logger.info("="*50)
    logger.info(" 🆕 = new bank metric feature")

    # Rejection analysis: what % have a bank metric in top-3 SHAP
    pred_classes = model.predict(X)
    rejected_idx = np.where(pred_classes == 0)[0]

    if len(rejected_idx) == 0:
        logger.info("\nNo predicted rejections in the test set.")
        return

    rejection_shap = shap_vals[rejected_idx]   # (n_rejected, n_feats)
    top3_contain_bank = 0
    for row in rejection_shap:
        top3_feats = {feat_cols[i] for i in np.argsort(np.abs(row))[-3:]}
        if top3_feats & BANK_METRIC_FEATURES:
            top3_contain_bank += 1

    pct = top3_contain_bank / len(rejected_idx) * 100
    logger.info(f"\nRejections where a bank metric is in top-3 SHAP: "
                f"{top3_contain_bank}/{len(rejected_idx)} = {pct:.1f}%")
    if pct >= 30:
        logger.info("✅ Interpretability audit PASSED (≥30% of rejections have bank-metric SHAP contribution)")
    else:
        logger.warning("⚠ Interpretability audit WARN (<30%). Bank features may need stronger signals in training data.")


if __name__ == "__main__":
    main()
