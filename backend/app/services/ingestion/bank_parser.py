"""
Bank Statement PDF Parser
=========================
Extracts transactions from bank statement PDFs.
Primary: Camelot table extraction → pdfplumber fallback → OCR fallback.

Advanced metrics extracted:
- average_daily_balance  : carry-forward daily balance over statement period
- average_transactional_balance : mean balance-after-tx across all transactions
- emi_estimated_monthly  : sum of median amounts of detected recurring debit series
- recurring_payments     : list of detected recurring payment series
- unusual_transactions   : transactions flagged as anomalous (3×median / 3×mean / top-1%)
- unusual_count          : count of flagged unusual transactions
- bounce_count           : number of returned/bounced cheque transactions
- balance_quality        : 'high' if running balances available, else 'low'
"""
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from statistics import median, mean, stdev

import numpy as np
import pandas as pd

from app.utils.pdf_utils import extract_tables_camelot, extract_text_pdfplumber, pdf_to_images
from app.utils.ocr import extract_text_from_pil

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CREDIT_KEYWORDS = ["cr", "credit", "deposit", "transfer in", "neft cr", "imps cr", "rtgs cr", "salary"]
DEBIT_KEYWORDS  = ["dr", "debit", "withdrawal", "transfer out", "payment", "emi", "ach"]

BOUNCE_KEYWORDS = [
    "return", "returned", "bounced", "nsf", "chq ret",
    "cheque returned", "cheque bounce", "cheque stop",
    "insufficient funds", "return chq",
]

EMI_KEYWORDS = [
    r"\bemi\b", r"equated", r"install", r"instal",
    r"\bloan\b", r"monthly", r"emipay", r"credit card payment",
    r"ccb payment", r"equi",
]

# ---------------------------------------------------------------------------
# BankData dataclass — all parsed data in one place
# ---------------------------------------------------------------------------

@dataclass
class BankData:
    account_number: str = ""
    account_holder: str = ""
    bank_name: str = ""
    statement_period: str = ""
    transactions: list = field(default_factory=list)

    # Monthly aggregates
    monthly_credits: dict = field(default_factory=dict)   # {YYYY-MM: total_credit}
    monthly_debits:  dict = field(default_factory=dict)
    monthly_net:     dict = field(default_factory=dict)

    # Totals
    total_credits: float = 0.0
    total_debits:  float = 0.0
    average_monthly_credit: float = 0.0
    opening_balance: float = 0.0
    closing_balance: float = 0.0

    # ---- Advanced metrics ----
    average_daily_balance: float = 0.0
    average_transactional_balance: float = 0.0
    balance_quality: str = "low"         # 'high' if running balances present

    emi_estimated_monthly: float = 0.0
    recurring_payments: list = field(default_factory=list)

    unusual_transactions: list = field(default_factory=list)
    unusual_count: int = 0

    bounce_count: int = 0

    # Legacy fields kept for backward compat
    emi_capacity: float = 0.0
    average_balance: float = 0.0


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _parse_amount(val) -> float:
    """Clean and parse a numeric value from a bank statement cell."""
    try:
        return float(str(val).replace(",", "").replace("₹", "").replace(" ", "").strip() or 0)
    except Exception:
        return 0.0


def _classify_transaction(row_text: str, amount: float, debit_col_val, credit_col_val) -> tuple[str, float]:
    """Return (type='credit'|'debit', amount)."""
    text = str(row_text).lower()
    try:
        c_val = float(str(credit_col_val).replace(",", "").strip() or 0)
        d_val = float(str(debit_col_val).replace(",", "").strip() or 0)
        if c_val > 0:
            return "credit", c_val
        if d_val > 0:
            return "debit", d_val
    except Exception:
        pass
    for kw in CREDIT_KEYWORDS:
        if kw in text:
            return "credit", abs(amount)
    return "debit", abs(amount)


def _detect_columns(df: pd.DataFrame):
    """Return (date_col, narration_col, debit_col, credit_col, balance_col) from df."""
    cols_lower = {c: c.lower() for c in df.columns}
    date_col    = next((c for c, v in cols_lower.items() if "date" in v), None)
    narr_col    = next((c for c, v in cols_lower.items() if any(k in v for k in ["narr", "desc", "particular", "detail", "remark"])), None)
    debit_col   = next((c for c, v in cols_lower.items() if any(k in v for k in ["debit", "dr", "withdrawal"])), None)
    credit_col  = next((c for c, v in cols_lower.items() if any(k in v for k in ["credit", "cr", "deposit"])), None)
    balance_col = next((c for c, v in cols_lower.items() if "balance" in v or "bal" in v), None)
    return date_col, narr_col, debit_col, credit_col, balance_col


# ---------------------------------------------------------------------------
# Bounce detection
# ---------------------------------------------------------------------------

def is_bounce(desc: str) -> bool:
    """Return True if the transaction description matches a bounce/return keyword."""
    desc_lower = str(desc).lower()
    return any(kw in desc_lower for kw in BOUNCE_KEYWORDS)


# ---------------------------------------------------------------------------
# Recurring / EMI detection
# ---------------------------------------------------------------------------

def detect_recurring_debits(transactions: list) -> tuple[float, list]:
    """
    Detect recurring debit series that look like EMI / standing orders.

    Algorithm
    ---------
    1. Normalise description → 4-token merchant key.
    2. Group debits by merchant token.
    3. A series qualifies if:
       a. ≥3 occurrences in ≥3 distinct months, OR
       b. description matches EMI keywords AND ≥2 occurrences.
       AND coefficient of variation ≤ 0.20 (tight amount band).
    4. ``emi_estimated_monthly`` = sum of median(amounts) across qualifying series.

    Parameters
    ----------
    transactions : list of dicts with keys date, narration, type, amount.

    Returns
    -------
    emi_estimated_monthly : float
    recurring_payments    : list of dicts
    """
    by_token: dict[str, list] = defaultdict(list)

    for tx in transactions:
        if tx.get("type") != "debit":
            continue
        desc = re.sub(r"[^a-z0-9 ]", " ", str(tx.get("narration", "")).lower())
        token = " ".join(desc.split()[:4])
        by_token[token].append(tx)

    recurring = []

    for token, txs in by_token.items():
        amounts = [abs(t["amount"]) for t in txs if t.get("amount", 0) != 0]
        if not amounts:
            continue

        # Check keyword match
        keyword_hit = any(re.search(kw, token) for kw in EMI_KEYWORDS)

        # Distinct months appearing in the series
        months = {str(t.get("date", ""))[:7] for t in txs}
        enough_months = len(months) >= 3

        # CoV: coefficient of variation = (max-min)/mean — tighter than stdev/mean
        avg_amt = sum(amounts) / len(amounts)
        cov = (max(amounts) - min(amounts)) / (avg_amt + 1e-9)

        qualifies = (
            (enough_months and len(amounts) >= 3) or
            (keyword_hit and len(amounts) >= 2)
        ) and cov <= 0.20

        if not qualifies and keyword_hit and len(amounts) >= 2:
            # Relaxed: allow CoV up to 0.40 if keyword is a strong signal
            qualifies = cov <= 0.40

        if qualifies:
            dates = [t["date"] for t in txs]
            recurring.append({
                "merchant":      token,
                "median_amount": round(median(amounts), 2),
                "first_date":    str(min(dates)),
                "last_date":     str(max(dates)),
                "count":         len(txs),
                "frequency":     "monthly",
            })

    emi_total = round(sum(r["median_amount"] for r in recurring), 2)
    return emi_total, recurring


# ---------------------------------------------------------------------------
# Unusual transaction detection
# ---------------------------------------------------------------------------

def detect_unusual_transactions(transactions: list) -> tuple[list, int]:
    """
    Flag transactions that are statistically anomalous.

    Rules (any one sufficient):
    - amount >= 3 × median_debit_amount
    - amount >= 3 × mean_debit_amount
    - amount in top 1% of all debit amounts

    Timing anomaly:
    - Large amount on a date with no prior activity in previous 30 calendar days.

    Parameters
    ----------
    transactions : list of dicts with keys date, type, amount, narration.

    Returns
    -------
    unusual : list of flagged transactions (dict with reason_flagged added)
    unusual_count : int
    """
    debits = [t for t in transactions if t.get("type") == "debit" and t.get("amount", 0) > 0]
    if not debits:
        return [], 0

    amounts = [t["amount"] for t in debits]
    med     = median(amounts)
    avg     = mean(amounts)
    top_1pct = float(np.percentile(amounts, 99))

    # Build a set of active dates for timing check
    all_dates = sorted({t["date"] for t in transactions})
    active_dates_set = set(all_dates)

    unusual: list[dict] = []

    for tx in debits:
        amt  = tx["amount"]
        reasons = []

        if med > 0 and amt >= 3 * med:
            reasons.append(f">3x median debit (median=₹{med:,.0f})")
        if avg > 0 and amt >= 3 * avg:
            reasons.append(f">3x mean debit (mean=₹{avg:,.0f})")
        if amt >= top_1pct and top_1pct > 0:
            reasons.append(f"top-1% of debit amounts (threshold=₹{top_1pct:,.0f})")

        # Timing anomaly: large (>3×avg) debit with no activity 30 days prior
        try:
            tx_date = date.fromisoformat(str(tx["date"]))
            if amt >= 3 * avg:
                window_start = tx_date - timedelta(days=30)
                prior_activity = any(
                    window_start <= date.fromisoformat(d) < tx_date
                    for d in active_dates_set
                )
                if not prior_activity:
                    reasons.append("timing anomaly: no activity in prior 30 days")
        except Exception:
            pass

        if reasons:
            flagged = {**tx, "reason_flagged": "; ".join(reasons)}
            unusual.append(flagged)

    return unusual, len(unusual)


# ---------------------------------------------------------------------------
# Average balance computation
# ---------------------------------------------------------------------------

def compute_average_daily_balance(transactions: list) -> tuple[float, str]:
    """
    Compute average daily balance using carry-forward method.

    Algorithm
    ---------
    1. Group transactions by date → keep the balance after the last transaction per day.
    2. Fill forward every calendar day across the statement range.
    3. average_daily_balance = sum(daily_balance) / num_days.

    Returns
    -------
    average_daily_balance : float (rounded to 2dp), 0.0 if balances unavailable.
    balance_quality       : 'high' if real balances used, 'low' if unavailable.
    """
    # Filter transactions that have a non-zero balance
    balance_txs = [(t["date"], t.get("balance", 0)) for t in transactions if t.get("balance", 0) > 0]

    if not balance_txs:
        return 0.0, "low"

    # Group: last balance per date
    by_date: dict[str, float] = {}
    for d, bal in balance_txs:
        by_date[d] = bal   # later entries for same date overwrite earlier ones

    if not by_date:
        return 0.0, "low"

    date_keys = sorted(by_date.keys())
    start = date.fromisoformat(date_keys[0])
    end   = date.fromisoformat(date_keys[-1])
    num_days = (end - start).days + 1

    if num_days <= 0:
        return round(float(by_date[date_keys[0]]), 2), "high"

    # Carry forward
    daily_balances = []
    last_known = by_date[date_keys[0]]
    for i in range(num_days):
        current_date = (start + timedelta(days=i)).isoformat()
        if current_date in by_date:
            last_known = by_date[current_date]
        daily_balances.append(last_known)

    avg = round(sum(daily_balances) / num_days, 2)
    return avg, "high"


def compute_average_transactional_balance(transactions: list) -> float:
    """Mean of balance_after_tx across transactions that have a non-zero balance."""
    balances = [t.get("balance", 0) for t in transactions if t.get("balance", 0) > 0]
    if not balances:
        return 0.0
    return round(mean(balances), 2)


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------

def parse_bank_pdf(file_path: str) -> BankData:
    """
    Parse a bank statement PDF and extract all financial metrics.

    Priority chain: Camelot table extraction → OCR fallback.

    Returns a fully populated BankData instance.
    """
    bank = BankData()
    transactions = []

    # --- Attempt table extraction via Camelot --------------------------------
    try:
        dfs = extract_tables_camelot(file_path)
        if not dfs:
            raise ValueError("No tables extracted by Camelot")

        for df in dfs:
            if df is None or df.empty or len(df.columns) < 3:
                continue
            # First row may be header repeated; promote it if columns are unnamed
            if all(str(v).lower() in ["", "nan", "none"] for v in df.iloc[0]):
                df = df.iloc[1:]
            df.columns = [str(c).strip() for c in df.columns]

            date_col, narr_col, debit_col, credit_col, balance_col = _detect_columns(df)
            if not date_col:
                # Promote first-row as header
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

                narr      = str(row.get(narr_col, "")) if narr_col else ""
                debit_val = _parse_amount(row.get(debit_col))  if debit_col  else 0.0
                credit_val= _parse_amount(row.get(credit_col)) if credit_col else 0.0
                balance_val = _parse_amount(row.get(balance_col)) if balance_col else 0.0

                if credit_val > 0:
                    t_type, t_amount = "credit", credit_val
                elif debit_val > 0:
                    t_type, t_amount = "debit", debit_val
                else:
                    t_type, t_amount = _classify_transaction(narr, 0, debit_val, credit_val)

                if parsed_date is not None and not pd.isna(parsed_date):
                    transactions.append({
                        "date":       parsed_date.strftime("%Y-%m-%d"),
                        "year_month": parsed_date.strftime("%Y-%m"),
                        "narration":  narr,
                        "type":       t_type,
                        "amount":     t_amount,
                        "balance":    balance_val,
                    })

    except Exception as e:
        logger.warning(f"Table extraction failed ({e}), falling back to OCR")
        images = pdf_to_images(file_path)
        for img in images:
            text = extract_text_from_pil(img)
            _parse_bank_text_ocr(text, transactions)

    # --- Aggregate monthly totals -------------------------------------------
    bank.transactions = transactions
    monthly_credits: dict = {}
    monthly_debits:  dict = {}

    for t in transactions:
        ym = t.get("year_month", "unknown")
        if t["type"] == "credit":
            monthly_credits[ym] = monthly_credits.get(ym, 0) + t["amount"]
        else:
            monthly_debits[ym]  = monthly_debits.get(ym, 0)  + t["amount"]

    bank.monthly_credits = monthly_credits
    bank.monthly_debits  = monthly_debits
    bank.monthly_net = {
        m: monthly_credits.get(m, 0) - monthly_debits.get(m, 0)
        for m in set(list(monthly_credits.keys()) + list(monthly_debits.keys()))
    }
    bank.total_credits = sum(monthly_credits.values())
    bank.total_debits  = sum(monthly_debits.values())
    n_months = len(monthly_credits) or 1
    bank.average_monthly_credit = round(bank.total_credits / n_months, 2)

    if transactions:
        bank.opening_balance = transactions[0].get("balance", 0)
        bank.closing_balance = transactions[-1].get("balance", 0)

    # --- Advanced Metric 1: Average Balances --------------------------------
    bank.average_daily_balance, bank.balance_quality = compute_average_daily_balance(transactions)
    bank.average_transactional_balance = compute_average_transactional_balance(transactions)

    # Legacy aliases
    bank.average_balance = bank.average_transactional_balance

    # --- Advanced Metric 2: EMI / Recurring Payments ------------------------
    bank.emi_estimated_monthly, bank.recurring_payments = detect_recurring_debits(transactions)

    # Legacy alias
    emi_txns = [
        t["amount"] for t in transactions
        if t["type"] == "debit"
        and any(k in str(t.get("narration", "")).lower() for k in ["emi", "loan", "repayment", "finance"])
    ]
    bank.emi_capacity = sum(emi_txns) / n_months if emi_txns else bank.emi_estimated_monthly

    # --- Advanced Metric 3: Unusual Transactions ----------------------------
    bank.unusual_transactions, bank.unusual_count = detect_unusual_transactions(transactions)

    # --- Advanced Metric 4: Bounce / Returned Cheque Count ------------------
    bank.bounce_count = sum(1 for t in transactions if is_bounce(str(t.get("narration", ""))))

    logger.info(
        f"Bank parsed: {len(transactions)} txns | "
        f"avg_monthly_credit=₹{bank.average_monthly_credit:,.0f} | "
        f"avg_daily_balance=₹{bank.average_daily_balance:,.0f} ({bank.balance_quality}) | "
        f"emi=₹{bank.emi_estimated_monthly:,.0f}/mo | "
        f"unusual={bank.unusual_count} | bounces={bank.bounce_count}"
    )
    return bank


# ---------------------------------------------------------------------------
# OCR text fallback
# ---------------------------------------------------------------------------

def _parse_bank_text_ocr(text: str, transactions: list):
    """Naive OCR text parser — looks for date + amount patterns."""
    date_pattern   = re.compile(r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})")
    amount_pattern = re.compile(r"([\d,]+\.\d{2})")

    for line in text.split("\n"):
        dates   = date_pattern.findall(line)
        amounts = amount_pattern.findall(line)
        if dates and amounts:
            try:
                parsed_date = pd.to_datetime(dates[0], dayfirst=True, errors="coerce")
                if pd.isna(parsed_date):
                    continue
                amount  = float(amounts[-1].replace(",", ""))
                t_type  = "credit" if any(k in line.lower() for k in CREDIT_KEYWORDS) else "debit"
                transactions.append({
                    "date":       parsed_date.strftime("%Y-%m-%d"),
                    "year_month": parsed_date.strftime("%Y-%m"),
                    "narration":  line.strip(),
                    "type":       t_type,
                    "amount":     amount,
                    "balance":    0.0,
                })
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

def bank_data_to_dict(bank: BankData) -> dict:
    """Convert a BankData instance to a JSON-serialisable dict."""
    return {
        # Identity
        "account_number":   bank.account_number,
        "bank_name":        bank.bank_name,
        "statement_period": bank.statement_period,
        # Monthly aggregates
        "monthly_credits":  bank.monthly_credits,
        "monthly_debits":   bank.monthly_debits,
        "monthly_net":      bank.monthly_net,
        # Totals
        "total_credits":    bank.total_credits,
        "total_debits":     bank.total_debits,
        "average_monthly_credit": bank.average_monthly_credit,
        "opening_balance":  bank.opening_balance,
        "closing_balance":  bank.closing_balance,
        # ---- Advanced metrics ----
        "average_daily_balance":        bank.average_daily_balance,
        "average_transactional_balance": bank.average_transactional_balance,
        "balance_quality":              bank.balance_quality,
        "emi_estimated_monthly":        bank.emi_estimated_monthly,
        "recurring_payments":           bank.recurring_payments,
        "unusual_transactions":         bank.unusual_transactions,
        "unusual_count":                bank.unusual_count,
        "bounce_count":                 bank.bounce_count,
        # Legacy / convenience
        "emi_capacity":    bank.emi_capacity,
        "average_balance": bank.average_balance,
        "transaction_count":   len(bank.transactions),
        "transactions_sample": bank.transactions[:20],
    }
