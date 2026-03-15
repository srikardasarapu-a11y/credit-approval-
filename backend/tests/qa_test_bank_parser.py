import os
import sys
import pytest
from pathlib import Path

# Add backend/ to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.ingestion.bank_parser import parse_bank_pdf

DATA_DIR = Path(__file__).resolve().parent.parent / "qa_test_data"

def test_bank_parser_healthy():
    """Verify healthy bank data: no bounces, low EMI."""
    file_path = str(DATA_DIR / "scenario_healthy" / "bank.pdf")
    bank_data = parse_bank_pdf(file_path)
    
    assert bank_data.bounce_count == 0
    assert bank_data.emi_estimated_monthly > 0
    assert bank_data.average_daily_balance > 0
    # recurring check
    assert len(bank_data.recurring_payments) >= 1
    assert "HDFC" in bank_data.recurring_payments[0]["merchant"].upper()

def test_bank_parser_overleveraged():
    """Verify overleveraged case: high EMI."""
    file_path = str(DATA_DIR / "scenario_overleveraged" / "bank.pdf")
    bank_data = parse_bank_pdf(file_path)
    
    # 300k EMI per month
    assert bank_data.emi_estimated_monthly >= 300000
    assert len(bank_data.recurring_payments) >= 1

def test_bank_parser_high_bounce():
    """Verify high bounce case: 4 bounces."""
    file_path = str(DATA_DIR / "scenario_high_bounce" / "bank.pdf")
    bank_data = parse_bank_pdf(file_path)
    
    # We generated 4 bounce entries
    assert bank_data.bounce_count == 4

def test_bank_parser_unusual_txns():
    """Verify unusual transaction flagging (>3x average)."""
    file_path = str(DATA_DIR / "scenario_unusual" / "bank.pdf")
    bank_data = parse_bank_pdf(file_path)
    
    # 10 small debits ~15k, 1 large 500k
    assert bank_data.unusual_count >= 1
    flagged_amounts = [u["amount"] for u in bank_data.unusual_transactions]
    assert 500000 in flagged_amounts
    assert any("3x median" in u["reason_flagged"] for u in bank_data.unusual_transactions)

def test_bank_parser_avg_balances():
    """Verify average daily balance calculation."""
    file_path = str(DATA_DIR / "scenario_healthy" / "bank.pdf")
    bank_data = parse_bank_pdf(file_path)
    
    assert bank_data.average_daily_balance > 0
    assert bank_data.average_transactional_balance > 0
    assert bank_data.balance_quality == "high" # since we included running balances
