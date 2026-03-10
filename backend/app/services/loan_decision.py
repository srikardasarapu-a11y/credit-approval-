"""
Loan Decision Engine
Computes:
  - Cash-flow based loan capacity
  - Collateral LTV-based limit
  - Recommended loan amount (min of both)
  - Interest rate = Base rate + risk spread
  - Structured reason strings
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
    "commercial_property": 0.65,
    "plant_and_machinery": 0.50,
    "fdr_liquid": 0.90,
    "stocks_mv": 0.60,
    "default": 0.70,
}


@dataclass
class LoanDecision:
    cash_flow_capacity: float = 0.0
    collateral_ltv_limit: float = 0.0
    recommended_loan_amount: float = 0.0
    collateral_value: float = 0.0
    collateral_type: str = "default"
    ltv_ratio: float = 0.70
    base_rate: float = 10.0
    risk_spread: float = 0.0
    final_interest_rate: float = 10.0
    risk_grade: str = "C"
    reasons: list[str] = field(default_factory=list)
    approved: bool = True
    reject_reasons: list[str] = field(default_factory=list)


def compute_loan_decision(
    average_monthly_credit: float,
    risk_grade: str,
    collateral_value: float,
    collateral_type: str = "default",
    auto_reject: bool = False,
    reject_reason: str = "",
    rule_flags: list = None,
    emi_capacity: float = 0.0,
) -> LoanDecision:
    """
    Determine loan amount and pricing.

    Cash-flow capacity: 50% of annualised average monthly bank credits minus existing EMIs.
    This is a conservative multiplier that ensures DSCR headroom.
    """
    decision = LoanDecision()
    decision.risk_grade = risk_grade
    decision.collateral_value = collateral_value
    decision.collateral_type = collateral_type
    decision.base_rate = settings.BASE_INTEREST_RATE

    # If auto-rejected by rule engine
    if auto_reject:
        decision.approved = False
        decision.reject_reasons.append(reject_reason)
        decision.recommended_loan_amount = 0.0
        decision.final_interest_rate = 0.0
        return decision

    # Cash-flow capacity
    annual_capacity = average_monthly_credit * 12
    annual_emi = emi_capacity * 12
    available_capacity = max((annual_capacity * 0.50) - annual_emi, 0.0)
    decision.cash_flow_capacity = round(available_capacity, 2)
    decision.reasons.append(
        f"Cash-flow capacity: (50% × ₹{average_monthly_credit:,.0f}/mo × 12) - ₹{annual_emi:,.0f} existing EMIs = ₹{decision.cash_flow_capacity:,.0f}"
    )

    # Collateral LTV limit
    ltv = LTV_RATIOS.get(collateral_type.lower(), LTV_RATIOS["default"])
    decision.ltv_ratio = ltv
    decision.collateral_ltv_limit = round(collateral_value * ltv, 2)
    decision.reasons.append(
        f"Collateral LTV: ₹{collateral_value:,.0f} × {ltv*100:.0f}% = ₹{decision.collateral_ltv_limit:,.0f}"
    )

    # Recommended loan = minimum of both
    decision.recommended_loan_amount = round(
        min(decision.cash_flow_capacity, decision.collateral_ltv_limit), 2
    )
    limiting = "cash-flow" if decision.cash_flow_capacity < decision.collateral_ltv_limit else "collateral LTV"
    decision.reasons.append(
        f"Recommended limit constrained by {limiting}: ₹{decision.recommended_loan_amount:,.0f}"
    )

    # Interest rate
    spread = GRADE_SPREAD.get(risk_grade, 2.5)
    decision.risk_spread = spread
    decision.final_interest_rate = round(decision.base_rate + spread, 2)
    decision.reasons.append(
        f"Interest rate: {decision.base_rate}% base + {spread}% risk spread (Grade {risk_grade}) = {decision.final_interest_rate}%"
    )

    # Flag borderline cases
    if rule_flags:
        for flag in rule_flags:
            decision.reasons.append(f"⚠ {flag}")

    decision.approved = decision.recommended_loan_amount > 0
    logger.info(
        f"Loan decision: ₹{decision.recommended_loan_amount:,.0f} @ {decision.final_interest_rate}% (Grade {risk_grade})"
    )
    return decision


def loan_decision_to_dict(d: LoanDecision) -> dict:
    return {
        "approved": d.approved,
        "recommended_loan_amount": d.recommended_loan_amount,
        "cash_flow_capacity": d.cash_flow_capacity,
        "collateral_ltv_limit": d.collateral_ltv_limit,
        "collateral_value": d.collateral_value,
        "collateral_type": d.collateral_type,
        "ltv_ratio": d.ltv_ratio,
        "base_rate": d.base_rate,
        "risk_spread": d.risk_spread,
        "final_interest_rate": d.final_interest_rate,
        "risk_grade": d.risk_grade,
        "reasons": d.reasons,
        "reject_reasons": d.reject_reasons,
    }
