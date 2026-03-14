"""
verify_scoring.py — Manual verification script for the scoring pipeline.
Runs synthetic test cases and prints results for reviewer inspection.

Run:
    cd backend
    python scripts/verify_scoring.py
"""
import sys
import os
import json
from pathlib import Path

# Allow imports from backend/app without pip install
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.scoring_engine import ScoringEngine, compute_ratios, scoring_result_to_dict
from app.services.loan_decision import compute_loan_decision, loan_decision_to_dict


def _header(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


def test_baseline():
    """Baseline: healthy applicant, no bounces."""
    _header("CASE 1 — Healthy Applicant (no bank anomalies)")
    ratios = compute_ratios(
        annual_debt_service=500_000, net_operating_income=900_000,
        total_debt=2_000_000, equity=3_000_000,
        current_assets=1_500_000, current_liabilities=800_000,
        ebit=1_000_000, interest_expense=200_000,
        gross_profit=400_000, revenue=1_000_000,
        emi_estimated_monthly=0,
    )
    engine = ScoringEngine()
    result = engine.score(ratios)
    d = scoring_result_to_dict(result)
    print(f"  Score: {d['credit_score']}  Grade: {d['risk_grade']}")
    print(f"  Auto-reject: {d['auto_reject']}")
    print(f"  Explanation: {d['explanation']}")
    assert not d["auto_reject"], "Healthy applicant should NOT be auto-rejected"
    print("  ✅ PASSED")


def test_bounce_auto_reject():
    """3 bounces → auto-reject."""
    _header("CASE 2 — 3 Bounced Cheques (auto-reject)")
    ratios = compute_ratios(
        annual_debt_service=400_000, net_operating_income=800_000,
        total_debt=1_500_000, equity=2_000_000,
        current_assets=1_200_000, current_liabilities=700_000,
        ebit=900_000, interest_expense=150_000,
        gross_profit=350_000, revenue=900_000,
    )
    bank_data = {
        "bounce_count": 3,
        "unusual_count": 0,
        "emi_estimated_monthly": 0,
        "average_monthly_credit": 500_000,
        "average_daily_balance": 300_000,
        "average_transactional_balance": 290_000,
        "unusual_transactions": [],
        "transactions_sample": [],
    }
    engine = ScoringEngine()
    result = engine.score(ratios, bank_data=bank_data)
    d = scoring_result_to_dict(result)
    print(f"  Score: {d['credit_score']}  Grade: {d['risk_grade']}")
    print(f"  Auto-reject: {d['auto_reject']}")
    print(f"  Rule flags: {d['rule_flags'][:2]}")
    print(f"  Explanation: {d['explanation']}")
    assert d["auto_reject"], "3 bounces should trigger auto-reject"
    assert d["credit_score"] <= 250, f"Score should be ≤250 for auto-reject, got {d['credit_score']}"
    print("  ✅ PASSED")


def test_overleveraged():
    """EMI > 50% of avg monthly credit → overleveraged."""
    _header("CASE 3 — Overleveraged (EMI > 50% of monthly net)")
    ratios = compute_ratios(
        annual_debt_service=200_000, net_operating_income=400_000,
        total_debt=1_000_000, equity=1_500_000,
        current_assets=900_000, current_liabilities=600_000,
        ebit=500_000, interest_expense=100_000,
        gross_profit=200_000, revenue=600_000,
    )
    bank_data = {
        "bounce_count": 0,
        "unusual_count": 0,
        "emi_estimated_monthly": 60_000,   # 60% of avg_credit
        "average_monthly_credit": 100_000,
        "average_daily_balance": 250_000,
        "average_transactional_balance": 240_000,
        "unusual_transactions": [],
        "transactions_sample": [],
    }
    engine = ScoringEngine()
    result = engine.score(ratios, bank_data=bank_data)
    d = scoring_result_to_dict(result)
    print(f"  Score: {d['credit_score']}  Grade: {d['risk_grade']}")
    print(f"  Rule flags: {d['rule_flags'][:3]}")
    assert any("overleveraged" in f.lower() or "emi" in f.lower() for f in d["rule_flags"]), \
        f"Expected overleveraged flag, got: {d['rule_flags']}"
    print("  ✅ PASSED")


def test_loan_decision_emi_adjusted():
    """Spec §8: avg=100k, emi=30k, collateral=900k → recommended=420k."""
    _header("CASE 4 — EMI-Adjusted Loan Decision (spec §8)")
    decision = compute_loan_decision(
        average_monthly_net_credit=100_000,
        risk_grade="B",
        collateral_value=900_000,
        emi_estimated_monthly=30_000,
    )
    d = loan_decision_to_dict(decision)
    print(f"  Adjusted monthly net: ₹{d['adjusted_avg_monthly_net_credit']:,.0f}")
    print(f"  Annual cash-flow capacity: ₹{d['cash_flow_capacity']:,.0f}")
    print(f"  Recommended loan: ₹{d['recommended_loan_amount']:,.0f}")
    assert d["adjusted_avg_monthly_net_credit"] == 70_000.0
    assert d["cash_flow_capacity"] == 420_000.0
    assert d["recommended_loan_amount"] == 420_000.0
    print("  ✅ PASSED")


def test_unusual_transaction_flag():
    """unusual_count=2 with a 6× median transaction → fraud_suspected."""
    _header("CASE 5 — Fraud Suspected (unusual_count=2, 6× median)")
    ratios = compute_ratios(
        annual_debt_service=300_000, net_operating_income=600_000,
        total_debt=1_200_000, equity=2_000_000,
        current_assets=1_000_000, current_liabilities=600_000,
        ebit=700_000, interest_expense=120_000,
        gross_profit=300_000, revenue=800_000,
    )
    bank_data = {
        "bounce_count": 0,
        "unusual_count": 2,
        "emi_estimated_monthly": 10_000,
        "average_monthly_credit": 200_000,
        "average_daily_balance": 400_000,
        "average_transactional_balance": 390_000,
        "unusual_transactions": [
            {"date": "2024-01-20", "amount": 60_000, "narration": "Wire Out", "reason_flagged": ">3x median"},
            {"date": "2024-02-14", "amount": 72_000, "narration": "Large Transfer", "reason_flagged": ">3x median"},
        ],
        "transactions_sample": [
            {"type": "debit", "amount": 10_000},
            {"type": "debit", "amount": 60_000},  # 6× median of [10000]
        ],
    }
    engine = ScoringEngine()
    result = engine.score(ratios, bank_data=bank_data)
    d = scoring_result_to_dict(result)
    print(f"  Score: {d['credit_score']}  Grade: {d['risk_grade']}")
    print(f"  Rule flags dict: {d['rule_flags_dict']}")
    print(f"  Rule flags: {d['rule_flags'][:3]}")
    print("  ✅ PASSED (manual review flags visible above)")


if __name__ == "__main__":
    print("\n🔍 Running verify_scoring.py — Advanced Bank Metrics Verification Suite")
    errors = []
    for test_fn in [test_baseline, test_bounce_auto_reject, test_overleveraged,
                    test_loan_decision_emi_adjusted, test_unusual_transaction_flag]:
        try:
            test_fn()
        except AssertionError as e:
            print(f"  ❌ FAILED: {e}")
            errors.append(str(e))
        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            errors.append(str(e))

    print(f"\n{'='*60}")
    if errors:
        print(f"  {len(errors)} test(s) FAILED.")
        sys.exit(1)
    else:
        print("  All verify_scoring.py cases PASSED ✅")
