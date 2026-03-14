"""
Unit tests for bank_parser advanced metrics.

Cases
-----
A: Statement with running balances on every tx date → verify average_daily_balance.
B: Recurring EMI-like debits (same merchant, three months) → assert emi_estimated_monthly.
C: Single large debit 500% of median → assert unusual_count == 1 and reason contains ">3x median".
D: Two bounce-labelled narrations → bounce_count == 2.
"""
import sys
import os
from datetime import date
from pathlib import Path

import pytest

# Allow imports without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.ingestion.bank_parser import (
    compute_average_daily_balance,
    compute_average_transactional_balance,
    detect_recurring_debits,
    detect_unusual_transactions,
    is_bounce,
    BankData,
)


# ---------------------------------------------------------------------------
# Case A — Average Daily Balance (carry-forward)
# ---------------------------------------------------------------------------

class TestAverageDailyBalance:
    """
    Statement with 3 consecutive dates, each having a distinct running balance.

    Dates:  2024-01-01  2024-01-02  2024-01-03
    Balances: 10000       12000       11000
    Expected average_daily_balance = (10000+12000+11000) / 3 = 11000.00
    """

    TRANSACTIONS = [
        {"date": "2024-01-01", "year_month": "2024-01", "narration": "NEFT IN",  "type": "credit", "amount": 5000,  "balance": 10000},
        {"date": "2024-01-02", "year_month": "2024-01", "narration": "Salary",   "type": "credit", "amount": 7000,  "balance": 12000},
        {"date": "2024-01-03", "year_month": "2024-01", "narration": "Rent OUT", "type": "debit",  "amount": 1000,  "balance": 11000},
    ]

    def test_average_daily_balance_exact(self):
        avg, quality = compute_average_daily_balance(self.TRANSACTIONS)
        assert quality == "high", "Balance quality should be 'high' when running balances present"
        # (10000 + 12000 + 11000) / 3 = 11000.00
        assert avg == 11000.00, f"Expected 11000.00, got {avg}"

    def test_balance_quality_low_when_no_balances(self):
        txns = [{"date": "2024-01-01", "type": "credit", "amount": 1000, "balance": 0}]
        avg, quality = compute_average_daily_balance(txns)
        assert quality == "low"
        assert avg == 0.0

    def test_average_transactional_balance(self):
        avg_tx = compute_average_transactional_balance(self.TRANSACTIONS)
        # mean([10000, 12000, 11000]) = 11000.00
        assert avg_tx == 11000.00, f"Expected 11000.00, got {avg_tx}"


# ---------------------------------------------------------------------------
# Case B — EMI / Recurring Payment Detection
# ---------------------------------------------------------------------------

class TestEMIDetection:
    """
    Three debits to the same merchant across three different months.
    Amounts: [15000, 15500, 14800] → median = 15000, CoV = (15500-14800)/15100 ≈ 0.046

    Expected:
        emi_estimated_monthly == 15000.0 (median of the one series)
        recurring_payments has one entry
    """

    TRANSACTIONS = [
        {"date": "2024-01-10", "year_month": "2024-01", "narration": "HDFC EMI LOAN",
         "type": "debit", "amount": 15000, "balance": 0},
        {"date": "2024-02-10", "year_month": "2024-02", "narration": "HDFC EMI LOAN",
         "type": "debit", "amount": 15500, "balance": 0},
        {"date": "2024-03-10", "year_month": "2024-03", "narration": "HDFC EMI LOAN",
         "type": "debit", "amount": 14800, "balance": 0},
        # A one-off debit to a different merchant (should NOT be flagged as recurring)
        {"date": "2024-01-15", "year_month": "2024-01", "narration": "Amazon purchase",
         "type": "debit", "amount": 3200, "balance": 0},
    ]

    def test_emi_estimated_monthly(self):
        emi, recurring = detect_recurring_debits(self.TRANSACTIONS)
        from statistics import median
        expected_emi = median([15000, 15500, 14800])   # 15000.0
        assert emi == expected_emi, f"Expected EMI {expected_emi}, got {emi}"

    def test_recurring_payments_entry(self):
        emi, recurring = detect_recurring_debits(self.TRANSACTIONS)
        assert len(recurring) >= 1, "Expected at least one recurring payment series"
        merged = [r for r in recurring if "hdfc" in r["merchant"]]
        assert merged, f"No HDFC recurring entry found in {recurring}"
        assert merged[0]["median_amount"] == 15000.0

    def test_amazon_not_recurring(self):
        emi, recurring = detect_recurring_debits(self.TRANSACTIONS)
        amazon = [r for r in recurring if "amazon" in r["merchant"]]
        assert not amazon, "One-off Amazon purchase should not be flagged as recurring"


# ---------------------------------------------------------------------------
# Case C — Unusual Transaction Detection (500% of median)
# ---------------------------------------------------------------------------

class TestUnusualTransactions:
    """
    Debits: [1000, 1200, 900, 25000]
    Median of [1000, 1200, 900, 25000] = (1000+1200)/2 = 1100.0
    25000 >= 3 × 1100 = 3300 → flagged
    Expected: unusual_count == 1, reason contains ">3x median"
    """

    TRANSACTIONS = [
        {"date": "2024-01-01", "year_month": "2024-01", "narration": "Grocery",   "type": "debit", "amount": 1000,  "balance": 0},
        {"date": "2024-01-05", "year_month": "2024-01", "narration": "Utility",   "type": "debit", "amount": 1200,  "balance": 0},
        {"date": "2024-01-10", "year_month": "2024-01", "narration": "Transport", "type": "debit", "amount": 900,   "balance": 0},
        {"date": "2024-01-25", "year_month": "2024-01", "narration": "Wire Out",  "type": "debit", "amount": 25000, "balance": 0},
    ]

    def test_unusual_count(self):
        unusual, count = detect_unusual_transactions(self.TRANSACTIONS)
        assert count == 1, f"Expected unusual_count=1, got {count}"
        assert len(unusual) == 1

    def test_unusual_reason_contains_3x_median(self):
        unusual, count = detect_unusual_transactions(self.TRANSACTIONS)
        reason = unusual[0].get("reason_flagged", "").lower()
        assert "3x median" in reason or ">3x median" in reason, (
            f"Expected reason to contain '>3x median', got: {reason}"
        )

    def test_small_debits_not_flagged(self):
        """The first three debits (1000, 1200, 900) must NOT be flagged."""
        unusual, _ = detect_unusual_transactions(self.TRANSACTIONS)
        flagged_amounts = {u["amount"] for u in unusual}
        assert 1000 not in flagged_amounts
        assert 1200 not in flagged_amounts
        assert 900  not in flagged_amounts


# ---------------------------------------------------------------------------
# Case D — Bounce Detection
# ---------------------------------------------------------------------------

class TestBounceDetection:
    """
    Two narrations containing bounce keywords → bounce_count == 2.
    """

    NARRATIONS_BOUNCE = [
        "CHEQUE BOUNCE FEE 202401",
        "CHQ RET - INS FUNDS",
        "Regular NEFT Payment",
    ]

    def test_bounce_count_two(self):
        count = sum(1 for narr in self.NARRATIONS_BOUNCE if is_bounce(narr))
        assert count == 2, f"Expected 2 bounces, counted {count}"

    def test_is_bounce_individual(self):
        assert is_bounce("CHEQUE BOUNCE FEE") is True
        assert is_bounce("CHQ RET INSUFFICIENT FUNDS") is True
        assert is_bounce("Regular NEFT Payment") is False
        assert is_bounce("CHEQUE RETURNED by bank") is True
        assert is_bounce("NSF charge 202402") is True

    def test_non_bounce_narrations(self):
        non_bounce = ["Salary Credit", "NEFT OUT", "UPI payment to vendor", "RTGS Receipt"]
        for narr in non_bounce:
            assert not is_bounce(narr), f"'{narr}' should NOT be flagged as bounce"
