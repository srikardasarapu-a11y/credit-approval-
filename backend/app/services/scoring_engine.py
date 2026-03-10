"""
Scoring Engine
Computes credit score using:
  1. Financial ratios (DSCR, D/E, Current Ratio, etc.)
  2. XGBoost ML model trained on synthetic data
  3. SHAP explanations for each prediction
  4. Rule-based checks (hard rejects / flags)

Score range: 0–1000. Risk Grade: A (>800) B (>650) C (>500) D (>350) E (≤350)
"""
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

try:
    import joblib
    import xgboost as xgb
    import shap
    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False
    logger.warning("XGBoost/SHAP not available — using rule-based fallback scoring")


GRADE_THRESHOLDS = [
    (800, "A"),
    (650, "B"),
    (500, "C"),
    (350, "D"),
    (0,   "E"),
]


@dataclass
class ScoringResult:
    credit_score: float = 0.0
    risk_grade: str = "E"
    financial_ratios: dict = field(default_factory=dict)
    shap_values: dict = field(default_factory=dict)
    shap_base_value: float = 0.0
    rule_flags: list[str] = field(default_factory=list)
    auto_reject: bool = False
    reject_reason: str = ""


def _grade(score: float) -> str:
    for threshold, grade in GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "E"


def compute_ratios(
    annual_debt_service: float,
    net_operating_income: float,
    total_debt: float,
    equity: float,
    current_assets: float,
    current_liabilities: float,
    ebit: float,
    interest_expense: float,
    gross_profit: float,
    revenue: float,
) -> dict:
    """Compute standard financial ratios used in credit analysis."""

    def safe_div(a, b, default=0.0):
        return round(a / b, 4) if b != 0 else default

    dscr = safe_div(net_operating_income, annual_debt_service)
    de_ratio = safe_div(total_debt, equity)
    current_ratio = safe_div(current_assets, current_liabilities)
    interest_coverage = safe_div(ebit, interest_expense)
    gross_margin = safe_div(gross_profit, revenue)

    return {
        "dscr": dscr,
        "de_ratio": de_ratio,
        "current_ratio": current_ratio,
        "interest_coverage": interest_coverage,
        "gross_margin": gross_margin,
        "net_operating_income": net_operating_income,
        "total_debt": total_debt,
        "equity": equity,
        "revenue": revenue,
    }


def _rule_checks(ratios: dict) -> tuple[list[str], bool, str]:
    """Apply hard rule gates. Returns (flags, auto_reject, reject_reason)."""
    flags = []
    auto_reject = False
    reject_reason = ""

    dscr = ratios.get("dscr", 1.0)
    de = ratios.get("de_ratio", 0.0)
    current = ratios.get("current_ratio", 1.0)
    equity = ratios.get("equity", 0.0)
    ic = ratios.get("interest_coverage", 1.0)

    if dscr < 1.0:
        auto_reject = True
        reject_reason = f"DSCR={dscr:.2f} < 1.0: Cash flow insufficient to service debt"
        flags.append(reject_reason)

    if equity < 0:
        flags.append("Negative equity — highly leveraged / insolvent position")
        if not auto_reject:
            auto_reject = True
            reject_reason = "Negative equity"

    if de > 4.0:
        flags.append(f"Debt/Equity={de:.2f} > 4.0: Extremely high leverage")

    if current < 1.0:
        flags.append(f"Current Ratio={current:.2f} < 1.0: Liquidity risk")

    if ic < 1.5:
        flags.append(f"Interest Coverage={ic:.2f} < 1.5: Thin coverage of interest obligations")

    return flags, auto_reject, reject_reason


def _heuristic_score(ratios: dict) -> float:
    """Rule-based fallback score when XGBoost model is unavailable."""
    score = 500.0

    dscr = ratios.get("dscr", 0)
    de = ratios.get("de_ratio", 2)
    cur = ratios.get("current_ratio", 1)
    ic = ratios.get("interest_coverage", 1)
    gm = ratios.get("gross_margin", 0.1)

    # DSCR contribution (±200 pts)
    score += min(max((dscr - 1.0) * 100, -200), 200)
    # D/E ratio (±100 pts)
    score += min(max((2.0 - de) * 50, -100), 100)
    # Current ratio (±100 pts)
    score += min(max((cur - 1.0) * 100, -100), 100)
    # Interest coverage (±50 pts)
    score += min(max((ic - 1.5) * 20, -50), 50)
    # Gross margin (±50 pts)
    score += min(max((gm - 0.10) * 200, -50), 50)

    return min(max(score, 0), 1000)


class ScoringEngine:
    def __init__(self, model_path: Optional[str] = None):
        self.model = None
        self.explainer = None
        self._feature_names = [
            "dscr", "de_ratio", "current_ratio", "interest_coverage",
            "gross_margin", "log_revenue", "research_risk"
        ]

        if not XGB_AVAILABLE:
            return

        path = model_path or os.path.join(
            os.path.dirname(__file__), "..", "..", "models_ml", "credit_model.pkl"
        )
        path = Path(path).resolve()
        if path.exists():
            try:
                self.model = joblib.load(path)
                self.explainer = shap.TreeExplainer(self.model)
                logger.info(f"Loaded XGBoost model from {path}")
            except Exception as e:
                logger.warning(f"Failed to load model ({e}) — using heuristic fallback")
        else:
            logger.info(f"Model not found at {path} — using heuristic fallback (run train_model.py)")

    def score(
        self,
        ratios: dict,
        research_risk: float = 0.0,
        reconciliation_risk: bool = False,
        bank_data: dict = None,
        mca_data: dict = None,
    ) -> ScoringResult:
        result = ScoringResult()
        result.financial_ratios = ratios

        # Rule checks first
        flags, auto_reject, reject_reason = _rule_checks(ratios)
        
        # Bank & MCA Advanced Checks
        if bank_data:
            unusual = bank_data.get("unusual_transactions", [])
            bounces = [u for u in unusual if "Bounce" in u.get("flag", "")]
            if len(bounces) > 3:
                flags.append(f"{len(bounces)} bounced cheques detected: High Default Risk")
                auto_reject = True
                reject_reason = "Multiple Bounced Cheques"
            elif len(bounces) > 0:
                flags.append(f"⚠ {len(bounces)} bounced cheques detected")
                
            non_bounces = [u for u in unusual if "Bounce" not in u.get("flag", "")]
            if non_bounces:
                flags.append(f"⚠ {len(non_bounces)} unusually large transactions flagged for manual review")

        if mca_data:
            if not mca_data.get("is_compliant", True):
                flags.append("Company is non-compliant with MCA filings (High Governance Risk)")
            if mca_data.get("last_agm_date") == "Not Filed":
                flags.append("Annual General Meeting (AGM) returns not filed - Transparency Alert")

        result.rule_flags = flags
        result.auto_reject = auto_reject
        result.reject_reason = reject_reason

        if reconciliation_risk:
            result.rule_flags.append("GST-Bank reconciliation mismatch flagged")

        # ML or heuristic score
        if self.model is not None and XGB_AVAILABLE:
            features = np.array([[
                ratios.get("dscr", 0),
                ratios.get("de_ratio", 0),
                ratios.get("current_ratio", 0),
                ratios.get("interest_coverage", 0),
                ratios.get("gross_margin", 0),
                np.log1p(ratios.get("revenue", 0)),
                research_risk,
            ]])
            prob = float(self.model.predict_proba(features)[0][1])  # P(good credit)
            raw_score = prob * 1000

            # Compute SHAP
            try:
                sv = self.explainer.shap_values(features)
                if isinstance(sv, list):
                    sv = sv[1]  # class 1
                result.shap_values = {
                    name: round(float(val), 4)
                    for name, val in zip(self._feature_names, sv[0])
                }
                result.shap_base_value = float(self.explainer.expected_value
                    if not isinstance(self.explainer.expected_value, list)
                    else self.explainer.expected_value[1])
            except Exception as e:
                logger.warning(f"SHAP computation failed: {e}")
                result.shap_values = {n: 0.0 for n in self._feature_names}
        else:
            raw_score = _heuristic_score(ratios)
            # Synthetic SHAP weights for display
            result.shap_values = {
                "dscr": round((ratios.get("dscr", 0) - 1) * 50, 2),
                "de_ratio": round((2 - ratios.get("de_ratio", 2)) * 25, 2),
                "current_ratio": round((ratios.get("current_ratio", 1) - 1) * 30, 2),
                "interest_coverage": round((ratios.get("interest_coverage", 1) - 1.5) * 10, 2),
                "gross_margin": round((ratios.get("gross_margin", 0) - 0.1) * 60, 2),
                "log_revenue": 0.0,
                "research_risk": round(-research_risk * 40, 2),
            }

        # Penalise for risk signals
        if auto_reject:
            raw_score = min(raw_score, 250)
        if reconciliation_risk:
            raw_score *= 0.9
        raw_score -= research_risk * 100

        result.credit_score = round(min(max(raw_score, 0), 1000), 1)
        result.risk_grade = _grade(result.credit_score)
        return result


def scoring_result_to_dict(r: ScoringResult) -> dict:
    return {
        "credit_score": r.credit_score,
        "risk_grade": r.risk_grade,
        "financial_ratios": r.financial_ratios,
        "shap_values": r.shap_values,
        "shap_base_value": r.shap_base_value,
        "rule_flags": r.rule_flags,
        "auto_reject": r.auto_reject,
        "reject_reason": r.reject_reason,
    }
