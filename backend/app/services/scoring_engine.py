"""
Scoring Engine
==============
Computes credit score using:
  1. Financial ratios (DSCR, D/E, Current Ratio, etc.)
  2. XGBoost ML model trained on synthetic + real data
  3. SHAP explanations for each prediction
  4. Rule-based checks (hard rejects / flags)

Score range: 0–1000. Risk Grade: A (≥800) B (≥650) C (≥500) D (≥350) E (≤350)

Advanced bank-statement rules (feat/advanced-bank-metrics)
----------------------------------------------------------
- bounce_count ≥ 3  → auto_reject_bounce (hard reject)
- bounce_count == 2 → severe downgrade (-200 pts)
- bounce_count == 1 → small penalty (-100 pts)
- unusual_count ≥ 2 and any unusual > 5× median → fraud_suspected (manual review)
- emi/avg_monthly_net > 0.5 → overleveraged flag
- DSCR adjusted = NOI / (ADS + 12 × emi_estimated_monthly)
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

# Feature vector for the v2 model — do NOT change order.
FEATURE_NAMES_V2 = [
    "dscr",
    "de_ratio",
    "current_ratio",
    "interest_coverage",
    "gross_margin",
    "log_revenue",
    "research_risk",
    # Bank metrics (new in v2)
    "average_daily_balance",
    "average_transactional_balance",
    "emi_estimated_monthly",
    "unusual_count",
    "bounce_count",
]

# Fallback when loading v2 fails — legacy 7-feature model
FEATURE_NAMES_V1 = [
    "dscr", "de_ratio", "current_ratio", "interest_coverage",
    "gross_margin", "log_revenue", "research_risk",
]


@dataclass
class ScoringResult:
    credit_score: float = 0.0
    risk_grade: str = "E"
    financial_ratios: dict = field(default_factory=dict)
    shap_values: dict = field(default_factory=dict)
    shap_base_value: float = 0.0
    rule_flags: list = field(default_factory=list)
    rule_flags_dict: dict = field(default_factory=dict)   # structured boolean flags
    auto_reject: bool = False
    reject_reason: str = ""
    explanation: str = ""                                 # human-readable combined reason


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
    emi_estimated_monthly: float = 0.0,
) -> dict:
    """
    Compute standard financial ratios used in credit analysis.

    Parameters
    ----------
    emi_estimated_monthly : float
        Monthly EMI burden detected from bank statement.
        Incorporated into DSCR denominator:
        DSCR = NOI / (ADS + 12 × emi_estimated_monthly).
    """
    def safe_div(a, b, default=0.0):
        return round(a / b, 4) if b != 0 else default

    # EMI-adjusted DSCR
    total_annual_debt = annual_debt_service + 12 * emi_estimated_monthly
    dscr = safe_div(net_operating_income, total_annual_debt)

    de_ratio        = safe_div(total_debt, equity)
    current_ratio   = safe_div(current_assets, current_liabilities)
    interest_coverage = safe_div(ebit, interest_expense)
    gross_margin    = safe_div(gross_profit, revenue)

    return {
        "dscr":                  dscr,
        "de_ratio":              de_ratio,
        "current_ratio":         current_ratio,
        "interest_coverage":     interest_coverage,
        "gross_margin":          gross_margin,
        "net_operating_income":  net_operating_income,
        "total_debt":            total_debt,
        "equity":                equity,
        "revenue":               revenue,
        "emi_adjusted_annual_debt": total_annual_debt,
    }


def _rule_checks(
    ratios: dict,
    bank_data: dict = None,
) -> tuple[list, dict, bool, str]:
    """
    Apply hard-rule gates and soft penalty flags.

    Returns
    -------
    flags        : list of human-readable flag strings
    flags_dict   : dict of boolean signal flags for downstream use
    auto_reject  : bool
    reject_reason: str
    """
    flags = []
    flags_dict: dict = {}
    auto_reject = False
    reject_reason = ""

    dscr    = ratios.get("dscr", 1.0)
    de      = ratios.get("de_ratio", 0.0)
    current = ratios.get("current_ratio", 1.0)
    equity  = ratios.get("equity", 0.0)
    ic      = ratios.get("interest_coverage", 1.0)

    # --- Standard financial ratio rules ---
    if dscr < 1.0:
        auto_reject = True
        reject_reason = f"DSCR={dscr:.2f} < 1.0: Cash flow insufficient to service debt"
        flags.append(reject_reason)
        flags_dict["dscr_fail"] = True

    if equity < 0:
        flags.append("Negative equity — highly leveraged / insolvent position")
        flags_dict["negative_equity"] = True
        if not auto_reject:
            auto_reject = True
            reject_reason = "Negative equity"

    if de > 4.0:
        flags.append(f"Debt/Equity={de:.2f} > 4.0: Extremely high leverage")

    if current < 1.0:
        flags.append(f"Current Ratio={current:.2f} < 1.0: Liquidity risk")

    if ic < 1.5:
        flags.append(f"Interest Coverage={ic:.2f} < 1.5: Thin coverage of interest obligations")

    # --- Advanced bank-metric rules ---
    if bank_data:
        bounce_count  = bank_data.get("bounce_count", 0) or 0
        unusual_count = bank_data.get("unusual_count", 0) or 0
        emi_monthly   = bank_data.get("emi_estimated_monthly", 0.0) or 0.0
        avg_credit    = bank_data.get("average_monthly_credit", 0.0) or 0.0
        unusual_txns  = bank_data.get("unusual_transactions", []) or []

        # Bounce rules
        if bounce_count >= 3:
            flags_dict["auto_reject_bounce"] = True
            if not auto_reject:
                auto_reject = True
                reject_reason = f"Auto-reject: {bounce_count} returned/bounced cheques detected"
            flags.append(f"AUTO-REJECT: {bounce_count} bounced cheques — exceeds threshold of 3")
        elif bounce_count == 2:
            flags_dict["severe_bounce_risk"] = True
            flags.append(f"⚠ SEVERE: {bounce_count} bounced cheques — heavy score penalty applied")
        elif bounce_count == 1:
            flags.append(f"⚠ {bounce_count} bounced cheque detected — score penalty applied")

        # Unusual transaction / fraud rules
        if unusual_count >= 2:
            # Find median-based threshold for the 5× check
            debit_amounts = [
                t.get("amount", 0) for t in bank_data.get("transactions_sample", [])
                if isinstance(t, dict) and t.get("type") == "debit"
            ]
            if debit_amounts:
                from statistics import median as _median
                med = _median(debit_amounts)
                any_five_x = any(
                    t.get("amount", 0) >= 5 * med for t in unusual_txns
                )
                if any_five_x:
                    flags_dict["fraud_suspected"] = True
                    flags.append(
                        f"⚠ FRAUD SUSPECTED: {unusual_count} unusual txns, at least one >5× median — manual review required"
                    )
            if not flags_dict.get("fraud_suspected"):
                flags.append(f"⚠ {unusual_count} unusual transactions flagged for review")

        # Overleveraged rule
        if avg_credit > 0 and emi_monthly / avg_credit > 0.5:
            flags_dict["overleveraged"] = True
            flags.append(
                f"⚠ OVERLEVERAGED: EMI ₹{emi_monthly:,.0f}/mo is "
                f"{emi_monthly/avg_credit*100:.0f}% of avg monthly credit ₹{avg_credit:,.0f}"
            )

        # Legacy unusual-transactions check
        unusual_legacy = [u for u in unusual_txns if "bounce" not in u.get("reason_flagged", "").lower()]
        if unusual_legacy and not flags_dict.get("fraud_suspected"):
            flags.append(f"⚠ {len(unusual_legacy)} unusually large transactions for manual review")

    return flags, flags_dict, auto_reject, reject_reason


def _heuristic_score(ratios: dict, bank_data: dict = None) -> float:
    """Rule-based fallback score when XGBoost model is unavailable."""
    score = 500.0

    dscr = ratios.get("dscr", 0)
    de   = ratios.get("de_ratio", 2)
    cur  = ratios.get("current_ratio", 1)
    ic   = ratios.get("interest_coverage", 1)
    gm   = ratios.get("gross_margin", 0.1)

    score += min(max((dscr - 1.0) * 100, -200), 200)
    score += min(max((2.0  - de)  * 50,  -100), 100)
    score += min(max((cur  - 1.0) * 100, -100), 100)
    score += min(max((ic   - 1.5) * 20,  -50),   50)
    score += min(max((gm   - 0.10)* 200, -50),  50)

    # Bank metric penalties
    if bank_data:
        bounce_count  = bank_data.get("bounce_count", 0) or 0
        unusual_count = bank_data.get("unusual_count", 0) or 0
        avg_credit    = bank_data.get("average_monthly_credit", 1) or 1
        emi_monthly   = bank_data.get("emi_estimated_monthly", 0) or 0

        score -= bounce_count * 100
        score -= unusual_count * 20
        if avg_credit > 0 and emi_monthly / avg_credit > 0.5:
            score -= 150   # overleveraged penalty

    return min(max(score, 0), 1000)


def _build_explanation(rule_flags: list, rule_flags_dict: dict, shap_values: dict, reject_reason: str) -> str:
    """
    Produce a human-readable explanation combining rule flags and SHAP top contributors.

    Format:
        Auto-reject: <reason>; SHAP: <feature> contributed <val> to score
    """
    parts = []

    if reject_reason:
        parts.append(f"Auto-reject: {reject_reason}")

    # Top-3 SHAP features by absolute value
    top_shap = sorted(shap_values.items(), key=lambda x: abs(x[1]), reverse=True)[:3]
    if top_shap:
        shap_strs = [f"{feat} {'+' if val >= 0 else ''}{val:.2f}" for feat, val in top_shap]
        parts.append("SHAP top contributors: " + ", ".join(shap_strs))

    # Notable rule flags
    critical_flags = [f for f in rule_flags if "REJECT" in f or "FRAUD" in f or "SEVERE" in f]
    if critical_flags and not reject_reason:
        parts.append("Critical flags: " + "; ".join(critical_flags[:2]))

    return " | ".join(parts) if parts else "No critical issues detected"


class ScoringEngine:
    """
    Unified scoring engine.

    Tries to load credit_model_v2.pkl (12 features) first;
    falls back to credit_model.pkl (7 features) or pure heuristics.
    """

    def __init__(self, model_path: Optional[str] = None):
        self.model = None
        self.explainer = None
        self._feature_names = FEATURE_NAMES_V1   # default; updated on model load
        self._model_version = "heuristic"

        if not XGB_AVAILABLE:
            return

        # Try v2 first, then v1
        base_dir = Path(os.path.dirname(__file__)) / ".." / ".." / "models_ml"
        paths_to_try = []
        if model_path:
            paths_to_try.append((Path(model_path).resolve(), FEATURE_NAMES_V2))
        paths_to_try += [
            (base_dir / "credit_model_v2.pkl", FEATURE_NAMES_V2),
            (base_dir / "credit_model.pkl",    FEATURE_NAMES_V1),
        ]

        for path, feat_names in paths_to_try:
            p = path.resolve()
            if p.exists():
                try:
                    self.model = joblib.load(p)
                    self.explainer = shap.TreeExplainer(self.model)
                    self._feature_names = feat_names
                    self._model_version = p.name
                    logger.info(f"Loaded XGBoost model {p.name} ({len(feat_names)} features)")
                    break
                except Exception as e:
                    logger.warning(f"Failed to load model {p} ({e})")

        if self.model is None:
            logger.info("No XGBoost model found — using heuristic fallback (run scripts/train_model.py)")

    def _build_feature_vector(self, ratios: dict, research_risk: float, bank_data: dict | None) -> np.ndarray:
        """Assemble the correct feature vector based on the loaded model version."""
        bd = bank_data or {}
        avg_daily = float(bd.get("average_daily_balance", 0) or 0)
        avg_tx    = float(bd.get("average_transactional_balance", 0) or 0)
        # Impute average_daily_balance with average_transactional_balance if 0
        if avg_daily == 0:
            avg_daily = avg_tx

        base = [
            ratios.get("dscr", 0),
            ratios.get("de_ratio", 0),
            ratios.get("current_ratio", 0),
            ratios.get("interest_coverage", 0),
            ratios.get("gross_margin", 0),
            np.log1p(ratios.get("revenue", 0)),
            research_risk,
        ]
        if self._feature_names == FEATURE_NAMES_V2:
            base += [
                avg_daily,
                avg_tx,
                float(bd.get("emi_estimated_monthly", 0) or 0),
                int(bd.get("unusual_count", 0) or 0),
                int(bd.get("bounce_count", 0) or 0),
            ]
        return np.array([base])

    def score(
        self,
        ratios: dict,
        research_risk: float = 0.0,
        reconciliation_risk: bool = False,
        bank_data: dict = None,
        mca_data: dict = None,
    ) -> ScoringResult:
        """
        Run the full scoring pipeline.

        Parameters
        ----------
        ratios           : output from compute_ratios()
        research_risk    : float in [0,1], risk from external research
        reconciliation_risk : bool, true if GST-bank mismatch flagged
        bank_data        : dict from bank_data_to_dict()
        mca_data         : dict from MCA filing parser
        """
        result = ScoringResult()
        result.financial_ratios = ratios

        # --- Rule checks (financial + bank metrics) ---
        flags, flags_dict, auto_reject, reject_reason = _rule_checks(ratios, bank_data)

        # MCA compliance checks
        if mca_data:
            if not mca_data.get("is_compliant", True):
                flags.append("Company is non-compliant with MCA filings (High Governance Risk)")
            if mca_data.get("last_agm_date") == "Not Filed":
                flags.append("AGM returns not filed — Transparency Alert")

        result.rule_flags     = flags
        result.rule_flags_dict = flags_dict
        result.auto_reject    = auto_reject
        result.reject_reason  = reject_reason

        if reconciliation_risk:
            result.rule_flags.append("GST-Bank reconciliation mismatch flagged")

        # --- ML score or heuristic fallback ---
        if self.model is not None and XGB_AVAILABLE:
            features = self._build_feature_vector(ratios, research_risk, bank_data)
            prob = float(self.model.predict_proba(features)[0][1])  # P(good credit)
            raw_score = prob * 1000

            # SHAP
            try:
                sv = self.explainer.shap_values(features)
                if isinstance(sv, list):
                    sv = sv[1]  # class 1
                result.shap_values = {
                    name: round(float(val), 4)
                    for name, val in zip(self._feature_names, sv[0])
                }
                result.shap_base_value = float(
                    self.explainer.expected_value
                    if not isinstance(self.explainer.expected_value, list)
                    else self.explainer.expected_value[1]
                )
            except Exception as e:
                logger.warning(f"SHAP computation failed: {e}")
                result.shap_values = {n: 0.0 for n in self._feature_names}
        else:
            raw_score = _heuristic_score(ratios, bank_data)
            # Synthetic SHAP weights for display
            bd = bank_data or {}
            result.shap_values = {
                "dscr":                         round((ratios.get("dscr", 0) - 1) * 50, 2),
                "de_ratio":                     round((2 - ratios.get("de_ratio", 2)) * 25, 2),
                "current_ratio":                round((ratios.get("current_ratio", 1) - 1) * 30, 2),
                "interest_coverage":            round((ratios.get("interest_coverage", 1) - 1.5) * 10, 2),
                "gross_margin":                 round((ratios.get("gross_margin", 0) - 0.1) * 60, 2),
                "log_revenue":                  0.0,
                "research_risk":                round(-research_risk * 40, 2),
                "average_daily_balance":        round(float(bd.get("average_daily_balance", 0) or 0) / 1e6, 2),
                "average_transactional_balance":round(float(bd.get("average_transactional_balance", 0) or 0) / 1e6, 2),
                "emi_estimated_monthly":        round(-float(bd.get("emi_estimated_monthly", 0) or 0) / 50000, 2),
                "unusual_count":               round(-(int(bd.get("unusual_count", 0) or 0)) * 5, 2),
                "bounce_count":                round(-(int(bd.get("bounce_count", 0) or 0)) * 20, 2),
            }

        # --- Apply penalties ---
        # Bounce penalties
        bounce = int((bank_data or {}).get("bounce_count", 0) or 0)
        if bounce >= 3:
            if not auto_reject:
                result.auto_reject = True
                result.reject_reason = f"Auto-reject: bounce_count={bounce} >= 3"
        elif bounce == 2:
            raw_score -= 200
        elif bounce == 1:
            raw_score -= 100

        if auto_reject or result.auto_reject:
            raw_score = min(raw_score, 250)

        if reconciliation_risk:
            raw_score *= 0.9

        raw_score -= research_risk * 100

        # Overleverage penalty
        if flags_dict.get("overleveraged"):
            raw_score -= 150

        result.credit_score = round(min(max(raw_score, 0), 1000), 1)
        result.risk_grade   = _grade(result.credit_score)

        # Human-readable explanation
        result.explanation = _build_explanation(
            result.rule_flags, result.rule_flags_dict,
            result.shap_values, result.reject_reason
        )

        return result


def scoring_result_to_dict(r: ScoringResult) -> dict:
    return {
        "credit_score":     r.credit_score,
        "risk_grade":       r.risk_grade,
        "financial_ratios": r.financial_ratios,
        "shap_values":      r.shap_values,
        "shap_base_value":  r.shap_base_value,
        "rule_flags":       r.rule_flags,
        "rule_flags_dict":  r.rule_flags_dict,
        "auto_reject":      r.auto_reject,
        "reject_reason":    r.reject_reason,
        "explanation":      r.explanation,
    }
