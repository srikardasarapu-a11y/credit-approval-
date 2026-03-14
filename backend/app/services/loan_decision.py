"""
Loan Decision Engine
====================
Computes:
  - Cash-flow based loan capacity (EMI-adjusted)
  - Collateral LTV-based limit
  - Recommended loan amount (min of both)
  - Interest rate = Base rate + risk spread
  - Structured reason strings

Cash-flow formula (feat/advanced-bank-metrics):
    adjusted_avg_monthly_net = max(0, average_monthly_net_credit - emi_estimated_monthly)
    annual_cash_flow_capacity = 0.5 * adjusted_avg_monthly_net * 12
    recommended_loan = min(annual_cash_flow_capacity, collateral_ltv)
"""
import logging
from dataclasses import dataclass, field

from app.config import settings

logger = logging.getLogger(__name__)

# Risk grade → spread (%)
GRADE_SPREAD = {
    "A": 0.0,
    "B": 0.5,
    "C": 1.25,
    "D": 2.5,
    "E": 4.0,
}

# Asset type → LTV ratio
LTV_RATIOS = {
    "residential_property": 0.75,
    "commercial_property":  0.65,
    "plant_and_machinery":  0.50,
    "fdr_liquid":           0.90,
    "stocks_mv":            0.60,
    "default":              0.70,
}


@dataclass
class LoanDecision:
    # Core outputs
    cash_flow_capacity:     float = 0.0
    collateral_ltv_limit:   float = 0.0
    recommended_loan_amount: float = 0.0
    collateral_value:        float = 0.0
    collateral_type:         str   = "default"
    ltv_ratio:               float = 0.70

    # Interest rate components
    base_rate:           float = 10.0
    risk_spread:         float = 0.0
    final_interest_rate: float = 10.0
    risk_grade:          str   = "C"

    # EMI impact (new)
    emi_estimated_monthly:          float = 0.0
    adjusted_avg_monthly_net_credit: float = 0.0

    # Decision narrative
    reasons:        list = field(default_factory=list)
    approved:       bool = True
    reject_reasons: list = field(default_factory=list)


def compute_loan_decision(
    average_monthly_net_credit: float,
    risk_grade: str,
    collateral_value: float,
    collateral_type: str = "default",
    auto_reject: bool = False,
    reject_reason: str = "",
    rule_flags: list = None,
    emi_estimated_monthly: float = 0.0,
    # Legacy param — kept for backward compat; ignored (use emi_estimated_monthly)
    emi_capacity: float = 0.0,
) -> LoanDecision:
    """
    Determine loan amount and pricing.

    Cash-flow capacity (EMI-adjusted, spec §5):
        adjusted_avg_monthly_net = max(0, average_monthly_net_credit - emi_estimated_monthly)
        annual_cash_flow_capacity = 0.5 × adjusted_avg_monthly_net × 12

    Parameters
    ----------
    average_monthly_net_credit : float
        Average monthly net (credit − debit) from bank statement. If not
        available, caller may pass average_monthly_credit instead.
    emi_estimated_monthly : float
        Monthly EMI burden detected from bank statement (from bank_parser).
    collateral_value : float
        Declared collateral market value (₹).
    """
    decision = LoanDecision()
    decision.risk_grade           = risk_grade
    decision.collateral_value     = collateral_value
    decision.collateral_type      = collateral_type
    decision.base_rate            = settings.BASE_INTEREST_RATE
    decision.emi_estimated_monthly = round(emi_estimated_monthly, 2)

    # --- Hard reject ---
    if auto_reject:
        decision.approved = False
        decision.reject_reasons.append(reject_reason)
        decision.recommended_loan_amount = 0.0
        decision.final_interest_rate     = 0.0
        return decision

    # --- Cash-flow capacity (EMI-adjusted) ---
    adjusted = max(0.0, average_monthly_net_credit - emi_estimated_monthly)
    decision.adjusted_avg_monthly_net_credit = round(adjusted, 2)
    annual_cash_flow_capacity = 0.5 * adjusted * 12
    decision.cash_flow_capacity = round(annual_cash_flow_capacity, 2)
    decision.reasons.append(
        f"Cash-flow capacity: 50% × (₹{average_monthly_net_credit:,.0f} − ₹{emi_estimated_monthly:,.0f} EMI) × 12 = ₹{decision.cash_flow_capacity:,.0f}"
    )

    # --- Collateral LTV limit ---
    ltv = LTV_RATIOS.get(collateral_type.lower(), LTV_RATIOS["default"])
    decision.ltv_ratio            = ltv
    decision.collateral_ltv_limit = round(collateral_value * ltv, 2)
    decision.reasons.append(
        f"Collateral LTV: ₹{collateral_value:,.0f} × {ltv*100:.0f}% = ₹{decision.collateral_ltv_limit:,.0f}"
    )

    # --- Recommended loan = min ---
    decision.recommended_loan_amount = round(
        min(decision.cash_flow_capacity, decision.collateral_ltv_limit), 2
    )
    limiting = "cash-flow" if decision.cash_flow_capacity < decision.collateral_ltv_limit else "collateral LTV"
    decision.reasons.append(
        f"Recommended limit constrained by {limiting}: ₹{decision.recommended_loan_amount:,.0f}"
    )

    # --- Interest rate ---
    spread = GRADE_SPREAD.get(risk_grade, 2.5)
    decision.risk_spread         = spread
    decision.final_interest_rate = round(decision.base_rate + spread, 2)
    decision.reasons.append(
        f"Interest rate: {decision.base_rate}% base + {spread}% risk spread (Grade {risk_grade}) = {decision.final_interest_rate}%"
    )

    # --- Soft flags ---
    if rule_flags:
        for flag in rule_flags:
            decision.reasons.append(f"⚠ {flag}")

    decision.approved = decision.recommended_loan_amount > 0
    logger.info(
        f"Loan decision: ₹{decision.recommended_loan_amount:,.0f} @ {decision.final_interest_rate}% "
        f"(Grade {risk_grade}) | adjusted_net=₹{adjusted:,.0f}/mo | emi=₹{emi_estimated_monthly:,.0f}/mo"
    )
    return decision


def loan_decision_to_dict(d: LoanDecision) -> dict:
    return {
        "approved":              d.approved,
        "recommended_loan_amount": d.recommended_loan_amount,
        "cash_flow_capacity":    d.cash_flow_capacity,
        "collateral_ltv_limit":  d.collateral_ltv_limit,
        "collateral_value":      d.collateral_value,
        "collateral_type":       d.collateral_type,
        "ltv_ratio":             d.ltv_ratio,
        "base_rate":             d.base_rate,
        "risk_spread":           d.risk_spread,
        "final_interest_rate":   d.final_interest_rate,
        "risk_grade":            d.risk_grade,
        # EMI impact details
        "emi_estimated_monthly":            d.emi_estimated_monthly,
        "adjusted_avg_monthly_net_credit":  d.adjusted_avg_monthly_net_credit,
        "reasons":               d.reasons,
        "reject_reasons":        d.reject_reasons,
    }
