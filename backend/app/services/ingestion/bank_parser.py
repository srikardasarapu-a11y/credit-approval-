"""
Bank Statement PDF Parser
Extracts transactions from bank statement PDFs.
Primary: Camelot table extraction → pdfplumber fallback → OCR fallback.
Classifies each row as credit/debit and computes monthly net credits.
"""
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from app.utils.pdf_utils import extract_tables_camelot, extract_text_pdfplumber, pdf_to_images
from app.utils.ocr import extract_text_from_pil

logger = logging.getLogger(__name__)


@dataclass
class BankData:
    account_number: str = ""
    account_holder: str = ""
    bank_name: str = ""
    statement_period: str = ""
    transactions: list = field(default_factory=list)
    monthly_credits: dict = field(default_factory=dict)   # {YYYY-MM: total_credit}
    monthly_debits: dict = field(default_factory=dict)
    monthly_net: dict = field(default_factory=dict)
    total_credits: float = 0.0
    total_debits: float = 0.0
    average_monthly_credit: float = 0.0
    opening_balance: float = 0.0
    closing_balance: float = 0.0
    emi_capacity: float = 0.0
    average_balance: float = 0.0
    unusual_transactions: list = field(default_factory=list)


CREDIT_KEYWORDS = ["cr", "credit", "deposit", "transfer in", "neft cr", "imps cr", "rtgs cr", "salary"]
DEBIT_KEYWORDS = ["dr", "debit", "withdrawal", "transfer out", "payment", "emi", "ach"]


def _classify_transaction(row_text: str, amount: float, debit_col_val, credit_col_val) -> tuple[str, float]:
    """Return (type='credit'|'debit', amount)."""
    text = str(row_text).lower()

    # If separate debit/credit columns exist
    try:
        c_val = float(str(credit_col_val).replace(",", "").strip() or 0)
        d_val = float(str(debit_col_val).replace(",", "").strip() or 0)
        if c_val > 0:
            return "credit", c_val
        if d_val > 0:
            return "debit", d_val
    except Exception:
        pass

    # Fallback: keyword matching
    for kw in CREDIT_KEYWORDS:
        if kw in text:
            return "credit", abs(amount)
    return "debit", abs(amount)


def _detect_columns(df: pd.DataFrame):
    """Return (date_col, narration_col, debit_col, credit_col, balance_col) from df."""
    cols_lower = {c: c.lower() for c in df.columns}
    date_col = next((c for c, v in cols_lower.items() if "date" in v), None)
    narr_col = next((c for c, v in cols_lower.items() if any(k in v for k in ["narr", "desc", "particular", "detail", "remark"])), None)
    debit_col = next((c for c, v in cols_lower.items() if any(k in v for k in ["debit", "dr", "withdrawal"])), None)
    credit_col = next((c for c, v in cols_lower.items() if any(k in v for k in ["credit", "cr", "deposit"])), None)
    balance_col = next((c for c, v in cols_lower.items() if "balance" in v or "bal" in v), None)
    return date_col, narr_col, debit_col, credit_col, balance_col


def _parse_amount(val) -> float:
    try:
        return float(str(val).replace(",", "").replace("₹", "").strip() or 0)
    except Exception:
        return 0.0


def parse_bank_pdf(file_path: str) -> BankData:
    bank = BankData()
    transactions = []

    # --- Attempt table extraction ---
    try:
        dfs = extract_tables_camelot(file_path)
        if not dfs:
            raise ValueError("No tables extracted")

        for df in dfs:
            if df is None or df.empty or len(df.columns) < 3:
                continue
            # First row may be header; promote it
            if all(str(v).lower() in ["", "nan", "none"] for v in df.iloc[0]):
                df = df.iloc[1:]
            df.columns = [str(c).strip() for c in df.columns]

            date_col, narr_col, debit_col, credit_col, balance_col = _detect_columns(df)
            if not date_col:
                # Try to promote header from first row
                df.columns = [str(v).strip() for v in df.iloc[0]]
                df = df.iloc[1:].reset_index(drop=True)
                date_col, narr_col, debit_col, credit_col, balance_col = _detect_columns(df)

            if not date_col:
                continue

            for _, row in df.iterrows():
                raw_date = str(row.get(date_col, "")).strip()
                if not raw_date or raw_date.lower() in ["date", "nan", ""]:
                    continue
                try:
                    parsed_date = pd.to_datetime(raw_date, dayfirst=True, errors="coerce")
                except Exception:
                    parsed_date = None

                narr = str(row.get(narr_col, "")) if narr_col else ""
                debit_val = _parse_amount(row.get(debit_col)) if debit_col else 0.0
                credit_val = _parse_amount(row.get(credit_col)) if credit_col else 0.0
                balance_val = _parse_amount(row.get(balance_col)) if balance_col else 0.0

                if credit_val > 0:
                    t_type, t_amount = "credit", credit_val
                elif debit_val > 0:
                    t_type, t_amount = "debit", debit_val
                else:
                    t_type, t_amount = _classify_transaction(narr, 0, debit_val, credit_val)

                if parsed_date is not None and not pd.isna(parsed_date):
                    transactions.append({
                        "date": parsed_date.strftime("%Y-%m-%d"),
                        "year_month": parsed_date.strftime("%Y-%m"),
                        "narration": narr,
                        "type": t_type,
                        "amount": t_amount,
                        "balance": balance_val,
                    })

    except Exception as e:
        logger.warning(f"Table extraction failed ({e}), trying OCR fallback")
        # OCR fallback: convert PDF pages to images and run OCR
        images = pdf_to_images(file_path)
        for img in images:
            text = extract_text_from_pil(img)
            _parse_bank_text_ocr(text, transactions)

    # ---Aggregate monthly totals ---
    bank.transactions = transactions
    monthly_credits: dict = {}
    monthly_debits: dict = {}

    for t in transactions:
        ym = t.get("year_month", "unknown")
        if t["type"] == "credit":
            monthly_credits[ym] = monthly_credits.get(ym, 0) + t["amount"]
        else:
            monthly_debits[ym] = monthly_debits.get(ym, 0) + t["amount"]

    bank.monthly_credits = monthly_credits
    bank.monthly_debits = monthly_debits
    bank.monthly_net = {
        m: monthly_credits.get(m, 0) - monthly_debits.get(m, 0)
        for m in set(list(monthly_credits.keys()) + list(monthly_debits.keys()))
    }
    bank.total_credits = sum(monthly_credits.values())
    bank.total_debits = sum(monthly_debits.values())
    n_months = len(monthly_credits) or 1
    bank.average_monthly_credit = bank.total_credits / n_months

    if transactions:
        bank.opening_balance = transactions[0].get("balance", 0)
        bank.closing_balance = transactions[-1].get("balance", 0)

    # --- New Advanced Metrics ---
    # Average Balance
    balances = [t.get("balance", 0) for t in transactions if t.get("balance", 0) > 0]
    bank.average_balance = sum(balances) / len(balances) if balances else 0.0

    # EMI Capacity (sum of EMI / Loan debits)
    emi_txns = [t["amount"] for t in transactions if t["type"] == "debit" and any(k in str(t.get("narration", "")).lower() for k in ["emi", "loan", "repayment", "finance"])]
    bank.emi_capacity = sum(emi_txns) / n_months if emi_txns else 0.0

    # Unusual Transactions (Bounces & Massive transfers)
    unusual = []
    # Bounces
    for t in transactions:
        narr = str(t.get("narration", "")).lower()
        if any(k in narr for k in ["bounce", "return", "chq ret", "insufficient", "penalty"]):
            unusual.append({**t, "flag": "Bounced Cheque / Failed Txn / Penalty"})

    # Large unusual transfers
    avg_debit = bank.total_debits / max(sum(1 for t in transactions if t["type"] == "debit"), 1)
    for t in transactions:
        if t["type"] == "debit" and t["amount"] > (avg_debit * 4) and t["amount"] > 50000:
            unusual.append({**t, "flag": f"Unusually large debit (4x average)"})
            
    bank.unusual_transactions = unusual

    logger.info(f"Bank parsed: {len(transactions)} transactions, avg monthly credit={bank.average_monthly_credit:.2f}")
    return bank


def _parse_bank_text_ocr(text: str, transactions: list):
    """Naïve OCR text parser — looks for date + amount patterns."""
    date_pattern = re.compile(r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})")
    amount_pattern = re.compile(r"([\d,]+\.\d{2})")

    lines = text.split("\n")
    for line in lines:
        dates = date_pattern.findall(line)
        amounts = amount_pattern.findall(line)
        if dates and amounts:
            try:
                parsed_date = pd.to_datetime(dates[0], dayfirst=True, errors="coerce")
                if pd.isna(parsed_date):
                    continue
                amount = float(amounts[-1].replace(",", ""))
                line_lower = line.lower()
                t_type = "credit" if any(k in line_lower for k in CREDIT_KEYWORDS) else "debit"
                transactions.append({
                    "date": parsed_date.strftime("%Y-%m-%d"),
                    "year_month": parsed_date.strftime("%Y-%m"),
                    "narration": line.strip(),
                    "type": t_type,
                    "amount": amount,
                    "balance": 0.0,
                })
            except Exception:
                pass


def bank_data_to_dict(bank: BankData) -> dict:
    return {
        "account_number": bank.account_number,
        "bank_name": bank.bank_name,
        "statement_period": bank.statement_period,
        "monthly_credits": bank.monthly_credits,
        "monthly_debits": bank.monthly_debits,
        "monthly_net": bank.monthly_net,
        "total_credits": bank.total_credits,
        "total_debits": bank.total_debits,
        "average_monthly_credit": bank.average_monthly_credit,
        "opening_balance": bank.opening_balance,
        "closing_balance": bank.closing_balance,
        "emi_capacity": bank.emi_capacity,
        "average_balance": bank.average_balance,
        "unusual_transactions": bank.unusual_transactions,
        "transaction_count": len(bank.transactions),
        "transactions_sample": bank.transactions[:20],
    }
