"""
ITR (Income Tax Return) PDF Parser
Extracts key financial figures from ITR-3 / ITR-6 PDFs:
- Gross total income, business income, tax paid
- Depreciation, deductions
Uses Camelot + pdfplumber with keyword-based extraction.
"""
import logging
import re
from dataclasses import dataclass
from typing import Optional

from app.utils.pdf_utils import extract_text_pdfplumber, extract_tables_camelot, pdf_to_images
from app.utils.ocr import extract_text_from_pil

logger = logging.getLogger(__name__)


@dataclass
class ITRData:
    pan: str = ""
    assessment_year: str = ""
    gross_total_income: float = 0.0
    business_income: float = 0.0
    other_income: float = 0.0
    total_deductions: float = 0.0
    taxable_income: float = 0.0
    tax_paid: float = 0.0
    advance_tax: float = 0.0
    tds: float = 0.0
    depreciation: float = 0.0
    net_profit: float = 0.0
    turnover: float = 0.0


_FIELD_PATTERNS = {
    "gross_total_income": [
        r"gross\s+total\s+income[\s:₹]+([\d,]+)",
        r"gross\s+income[\s:₹]+([\d,]+)",
    ],
    "business_income": [
        r"income\s+from\s+business[\s:₹]+([\d,]+)",
        r"business\s+profession[\s:₹]+([\d,]+)",
        r"profit\s+&?\s+gain\s+from\s+business[\s:₹]+([\d,]+)",
    ],
    "taxable_income": [
        r"total\s+income[\s:₹]+([\d,]+)",
        r"net\s+taxable\s+income[\s:₹]+([\d,]+)",
    ],
    "tax_paid": [
        r"total\s+tax\s+paid[\s:₹]+([\d,]+)",
        r"tax\s+payable[\s:₹]+([\d,]+)",
        r"taxes\s+paid[\s:₹]+([\d,]+)",
    ],
    "turnover": [
        r"gross\s+turnover[\s:₹]+([\d,]+)",
        r"turnover[\s:₹]+([\d,]+)",
        r"total\s+sales[\s:₹]+([\d,]+)",
    ],
    "net_profit": [
        r"net\s+profit[\s:₹]+([\d,]+)",
        r"profit\s+after\s+tax[\s:₹]+([\d,]+)",
    ],
    "depreciation": [
        r"depreciation[\s:₹]+([\d,]+)",
    ],
    "pan": [
        r"PAN\s*[:\-]?\s*([A-Z]{5}[0-9]{4}[A-Z])",
    ],
    "assessment_year": [
        r"assessment\s+year\s*:?\s*(\d{4}-\d{2,4})",
        r"A\.?Y\.?\s*:?\s*(\d{4}-\d{2,4})",
    ],
}


def _parse_amount(val: str) -> float:
    try:
        return float(val.replace(",", "").strip())
    except Exception:
        return 0.0


def _extract_from_text(text: str, itr: ITRData):
    text_lower = text.lower()
    for field_name, patterns in _FIELD_PATTERNS.items():
        current_val = getattr(itr, field_name)
        if current_val:
            continue  # Already found
        for pat in patterns:
            m = re.search(pat, text_lower, re.IGNORECASE)
            if m:
                raw = m.group(1)
                if field_name in ("pan", "assessment_year"):
                    setattr(itr, field_name, raw.upper())
                else:
                    setattr(itr, field_name, _parse_amount(raw))
                break


def parse_itr_pdf(file_path: str) -> ITRData:
    itr = ITRData()

    # Primary: pdfplumber text extraction
    text = extract_text_pdfplumber(file_path)
    if text.strip():
        _extract_from_text(text, itr)

    # If key fields still missing, try Camelot tables
    if itr.gross_total_income == 0:
        try:
            dfs = extract_tables_camelot(file_path)
            for df in dfs:
                if df is None or df.empty:
                    continue
                combined = " ".join(df.astype(str).values.flatten())
                _extract_from_text(combined, itr)
        except Exception as e:
            logger.warning(f"Camelot ITR extraction: {e}")

    # OCR fallback for scanned ITRs
    if itr.gross_total_income == 0:
        logger.info("Falling back to OCR for ITR extraction")
        images = pdf_to_images(file_path)
        for img in images:
            ocr_text = extract_text_from_pil(img)
            _extract_from_text(ocr_text, itr)
            if itr.gross_total_income > 0:
                break

    # Derived metrics
    if itr.net_profit == 0 and itr.gross_total_income > 0:
        itr.net_profit = itr.gross_total_income - itr.total_deductions

    logger.info(f"ITR parsed: AY={itr.assessment_year}, GTI={itr.gross_total_income:.2f}")
    return itr


def itr_data_to_dict(itr: ITRData) -> dict:
    return {
        "pan": itr.pan,
        "assessment_year": itr.assessment_year,
        "gross_total_income": itr.gross_total_income,
        "business_income": itr.business_income,
        "other_income": itr.other_income,
        "total_deductions": itr.total_deductions,
        "taxable_income": itr.taxable_income,
        "tax_paid": itr.tax_paid,
        "depreciation": itr.depreciation,
        "net_profit": itr.net_profit,
        "turnover": itr.turnover,
    }
