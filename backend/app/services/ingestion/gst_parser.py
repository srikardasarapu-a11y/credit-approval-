"""
GST CSV Parser
Parses GSTR-1 / GSTR-3B exported CSV files.
Computes monthly sales totals and extracts GSTIN / filing period info.
"""
import csv
import io
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class GSTData:
    gstin: str = ""
    filing_period: str = ""
    monthly_sales: dict = field(default_factory=dict)   # {YYYY-MM: amount}
    total_taxable_sales: float = 0.0
    total_igst: float = 0.0
    total_cgst: float = 0.0
    total_sgst: float = 0.0
    total_tax: float = 0.0
    num_invoices: int = 0
    raw_rows: list = field(default_factory=list)


def parse_gst_csv(file_path: str) -> GSTData:
    """
    Parse a GST return CSV file.
    Supports common GSTN portal export formats:
    - GSTR-1 B2B / B2C summary
    - GSTR-3B turnover rows
    """
    gst = GSTData()
    try:
        df = pd.read_csv(file_path, low_memory=False)
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

        # Try to detect GSTIN column
        for col in ["gstin", "gstin_of_supplier", "gstin_of_recipient"]:
            if col in df.columns:
                gst.gstin = str(df[col].dropna().iloc[0]) if not df[col].dropna().empty else ""
                break

        # Detect period column
        period_cols = [c for c in df.columns if "period" in c or "month" in c or "date" in c]
        taxable_cols = [c for c in df.columns if "taxable" in c or "value" in c or "sales" in c or "turnover" in c]
        igst_cols = [c for c in df.columns if "igst" in c]
        cgst_cols = [c for c in df.columns if "cgst" in c]
        sgst_cols = [c for c in df.columns if "sgst" in c or "utgst" in c]

        # Build numeric columns
        amount_col = taxable_cols[0] if taxable_cols else None

        if amount_col:
            df[amount_col] = pd.to_numeric(df[amount_col].astype(str).str.replace(",", ""), errors="coerce").fillna(0)

        if period_cols and amount_col:
            period_col = period_cols[0]
            df[period_col] = pd.to_datetime(df[period_col], errors="coerce", dayfirst=True)
            df["year_month"] = df[period_col].dt.to_period("M").astype(str)
            monthly = df.groupby("year_month")[amount_col].sum().to_dict()
            gst.monthly_sales = {k: float(v) for k, v in monthly.items() if k != "NaT"}
        else:
            # No period — aggregate total
            if amount_col:
                gst.monthly_sales = {"total": float(df[amount_col].sum())}

        # Totals
        gst.total_taxable_sales = sum(gst.monthly_sales.values())
        if igst_cols:
            df["__igst"] = pd.to_numeric(df[igst_cols[0]].astype(str).str.replace(",", ""), errors="coerce").fillna(0)
            gst.total_igst = float(df["__igst"].sum())
        if cgst_cols:
            df["__cgst"] = pd.to_numeric(df[cgst_cols[0]].astype(str).str.replace(",", ""), errors="coerce").fillna(0)
            gst.total_cgst = float(df["__cgst"].sum())
        if sgst_cols:
            df["__sgst"] = pd.to_numeric(df[sgst_cols[0]].astype(str).str.replace(",", ""), errors="coerce").fillna(0)
            gst.total_sgst = float(df["__sgst"].sum())

        gst.total_tax = gst.total_igst + gst.total_cgst + gst.total_sgst
        gst.num_invoices = len(df)
        gst.raw_rows = df.head(50).to_dict(orient="records")  # Store sample rows

        logger.info(f"GST CSV parsed: {gst.num_invoices} rows, total sales={gst.total_taxable_sales:.2f}")

    except Exception as e:
        logger.error(f"GST CSV parse error: {e}")

    return gst


def gst_data_to_dict(gst: GSTData) -> dict:
    return {
        "gstin": gst.gstin,
        "filing_period": gst.filing_period,
        "monthly_sales": gst.monthly_sales,
        "total_taxable_sales": gst.total_taxable_sales,
        "total_igst": gst.total_igst,
        "total_cgst": gst.total_cgst,
        "total_sgst": gst.total_sgst,
        "total_tax": gst.total_tax,
        "num_invoices": gst.num_invoices,
    }
