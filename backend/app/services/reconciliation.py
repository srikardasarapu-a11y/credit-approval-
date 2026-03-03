"""
GST-Bank Reconciliation Engine
Compares monthly GST reported sales against actual bank credit inflows.
Flags months where the mismatch ratio exceeds the configured threshold.
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

MISMATCH_THRESHOLD = 0.15   # 15% deviation triggers a flag


@dataclass
class MonthlyReconciliation:
    month: str
    gst_sales: float
    bank_credits: float
    mismatch_amount: float
    mismatch_ratio: float
    is_anomaly: bool
    note: str = ""


@dataclass
class ReconciliationResult:
    monthly_breakdown: list[MonthlyReconciliation] = field(default_factory=list)
    anomaly_months: list[str] = field(default_factory=list)
    total_gst_sales: float = 0.0
    total_bank_credits: float = 0.0
    overall_mismatch_ratio: float = 0.0
    risk_flag: bool = False
    summary: str = ""


def reconcile(
    gst_monthly_sales: dict,
    bank_monthly_credits: dict,
    threshold: float = MISMATCH_THRESHOLD
) -> ReconciliationResult:
    """
    Compare GST monthly sales vs bank monthly credits.

    Args:
        gst_monthly_sales: {YYYY-MM: amount} from GST parser
        bank_monthly_credits: {YYYY-MM: amount} from bank parser
        threshold: mismatch ratio above which month is flagged
    """
    result = ReconciliationResult()

    all_months = sorted(set(list(gst_monthly_sales.keys()) + list(bank_monthly_credits.keys())))

    for month in all_months:
        gst_amt = float(gst_monthly_sales.get(month, 0))
        bank_amt = float(bank_monthly_credits.get(month, 0))
        mismatch = abs(gst_amt - bank_amt)

        if gst_amt > 0:
            ratio = mismatch / gst_amt
        elif bank_amt > 0:
            ratio = 1.0  # GST not reported but bank credits exist
        else:
            ratio = 0.0

        is_anomaly = ratio > threshold

        # Determine note
        if gst_amt == 0 and bank_amt > 0:
            note = "Bank credits without GST filing — potential under-reporting"
        elif bank_amt == 0 and gst_amt > 0:
            note = "GST filed but no bank credits — potential misclassification"
        elif gst_amt > bank_amt * (1 + threshold):
            note = "GST sales significantly exceed bank credits — potential over-reporting"
        elif bank_amt > gst_amt * (1 + threshold):
            note = "Bank credits significantly exceed GST — potential unaccounted income"
        else:
            note = "Within acceptable range"

        rec = MonthlyReconciliation(
            month=month,
            gst_sales=gst_amt,
            bank_credits=bank_amt,
            mismatch_amount=mismatch,
            mismatch_ratio=round(ratio, 4),
            is_anomaly=is_anomaly,
            note=note,
        )
        result.monthly_breakdown.append(rec)
        if is_anomaly:
            result.anomaly_months.append(month)

    result.total_gst_sales = sum(gst_monthly_sales.values())
    result.total_bank_credits = sum(bank_monthly_credits.values())

    if result.total_gst_sales > 0:
        result.overall_mismatch_ratio = abs(
            result.total_gst_sales - result.total_bank_credits
        ) / result.total_gst_sales
    else:
        result.overall_mismatch_ratio = 1.0 if result.total_bank_credits > 0 else 0.0

    anomaly_pct = len(result.anomaly_months) / max(len(all_months), 1)
    result.risk_flag = anomaly_pct > 0.3 or result.overall_mismatch_ratio > 0.25

    n_anomaly = len(result.anomaly_months)
    result.summary = (
        f"{n_anomaly} anomalous months out of {len(all_months)}. "
        f"Overall mismatch ratio: {result.overall_mismatch_ratio:.1%}. "
        f"{'⚠ HIGH RISK — significant discrepancy detected.' if result.risk_flag else '✓ No major discrepancy.'}"
    )

    logger.info(f"Reconciliation complete: {result.summary}")
    return result


def reconciliation_to_dict(result: ReconciliationResult) -> dict:
    return {
        "monthly_breakdown": [
            {
                "month": r.month,
                "gst_sales": r.gst_sales,
                "bank_credits": r.bank_credits,
                "mismatch_amount": r.mismatch_amount,
                "mismatch_ratio": r.mismatch_ratio,
                "is_anomaly": r.is_anomaly,
                "note": r.note,
            }
            for r in result.monthly_breakdown
        ],
        "anomaly_months": result.anomaly_months,
        "total_gst_sales": result.total_gst_sales,
        "total_bank_credits": result.total_bank_credits,
        "overall_mismatch_ratio": result.overall_mismatch_ratio,
        "risk_flag": result.risk_flag,
        "summary": result.summary,
    }
