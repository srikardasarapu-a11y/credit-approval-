"""
Unit tests for loan_decision compute_loan_decision() — EMI-adjusted formula.

Spec test case:
    average_monthly_net_credit = 100,000
    emi_estimated_monthly      = 30,000
    collateral_ltv             = 900,000 (collateral_value=900,000 at LTV=100% for simplicity)

    adjusted_avg_monthly_net_credit = 100,000 - 30,000 = 70,000
    annual_cash_flow_capacity       = 0.5 × 70,000 × 12 = 420,000
    recommended_loan                = min(420,000, 900,000) = 420,000
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.loan_decision import compute_loan_decision, LoanDecision


class TestLoanDecisionEMIAdjusted:
    """Spec §8 exact numeric assertions."""

    def _make_decision(self, avg_net=100_000, emi=30_000, collateral=900_000,
                       collateral_type="default") -> LoanDecision:
        return compute_loan_decision(
            average_monthly_net_credit=avg_net,
            risk_grade="B",
            collateral_value=collateral,
            collateral_type=collateral_type,
            emi_estimated_monthly=emi,
        )

    def test_adjusted_avg_monthly_net(self):
        d = self._make_decision()
        assert d.adjusted_avg_monthly_net_credit == 70_000.0, (
            f"Expected adjusted=70,000 got {d.adjusted_avg_monthly_net_credit}"
        )

    def test_annual_cash_flow_capacity(self):
        d = self._make_decision()
        expected = 0.5 * 70_000 * 12   # = 420,000
        assert d.cash_flow_capacity == expected, (
            f"Expected cash_flow_capacity={expected}, got {d.cash_flow_capacity}"
        )

    def test_recommended_loan(self):
        d = self._make_decision()
        # min(420,000, 900,000 × 0.70) → min(420,000, 630,000) = 420,000
        # With default LTV=0.70: collateral_ltv = 900,000×0.70 = 630,000
        # cash-flow (420,000) < collateral_ltv (630,000) → constraining factor
        assert d.recommended_loan_amount == 420_000.0, (
            f"Expected recommended_loan=420,000, got {d.recommended_loan_amount}"
        )

    def test_no_emi_case(self):
        """With zero EMI, adjusted == avg_monthly_net_credit."""
        d = compute_loan_decision(
            average_monthly_net_credit=100_000,
            risk_grade="A",
            collateral_value=2_000_000,
            emi_estimated_monthly=0,
        )
        assert d.adjusted_avg_monthly_net_credit == 100_000.0
        assert d.cash_flow_capacity == 0.5 * 100_000 * 12   # 600,000

    def test_emi_exceeds_net_credit(self):
        """When EMI > avg_net, adjusted clamps to 0 (no negative capacity)."""
        d = compute_loan_decision(
            average_monthly_net_credit=20_000,
            risk_grade="D",
            collateral_value=500_000,
            emi_estimated_monthly=50_000,
        )
        assert d.adjusted_avg_monthly_net_credit == 0.0
        assert d.cash_flow_capacity == 0.0

    def test_auto_reject_skips_calculation(self):
        """Auto-rejected applications should return 0 loan amount."""
        d = compute_loan_decision(
            average_monthly_net_credit=100_000,
            risk_grade="E",
            collateral_value=900_000,
            emi_estimated_monthly=30_000,
            auto_reject=True,
            reject_reason="Test rejection",
        )
        assert d.approved is False
        assert d.recommended_loan_amount == 0.0

    def test_reason_string_includes_emi(self):
        """Reason string should mention EMI deduction."""
        d = self._make_decision()
        combined_reasons = " ".join(d.reasons)
        assert "30,000" in combined_reasons or "30000" in combined_reasons, (
            f"Expected EMI amount in reasons: {d.reasons}"
        )
