"""
PDF utility functions: PDF-to-image, text extraction, and table detection.
Uses pdfplumber as primary extractor and pdf2image for page-level images.
"""
import logging
from pathlib import Path
from typing import Generator, Optional

import pdfplumber
from PIL import Image

logger = logging.getLogger(__name__)

try:
    from pdf2image import convert_from_path
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False
    logger.warning("pdf2image not available — falling back to pdfplumber")


def extract_text_pdfplumber(pdf_path: str) -> str:
    """Extract all text from PDF using pdfplumber."""
    text_parts = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text_parts.append(t)
    except Exception as e:
        logger.error(f"pdfplumber failed for {pdf_path}: {e}")
    return "\n".join(text_parts)


def extract_tables_pdfplumber(pdf_path: str) -> list[list[list]]:
    """Extract all tables from PDF using pdfplumber."""
    tables = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables():
                    tables.append(table)
    except Exception as e:
        logger.error(f"pdfplumber table extraction failed for {pdf_path}: {e}")
    return tables


def pdf_to_images(pdf_path: str, dpi: int = 200) -> list[Image.Image]:
    """Convert PDF pages to PIL Images for OCR processing."""
    if not PDF2IMAGE_AVAILABLE:
        logger.warning("pdf2image not installed. Cannot convert PDF to images.")
        return []
    try:
        images = convert_from_path(pdf_path, dpi=dpi)
        return images
    except Exception as e:
        logger.error(f"pdf2image failed for {pdf_path}: {e}")
        return []


def extract_tables_camelot(pdf_path: str, pages: str = "all") -> list:
    """
    Extract tables using Camelot (better for structured PDFs with borders).
    Falls back gracefully if Camelot or Ghostscript is not available.
    """
    try:
        import camelot
        tables = camelot.read_pdf(pdf_path, pages=pages, flavor="lattice")
        if tables.n == 0:
            tables = camelot.read_pdf(pdf_path, pages=pages, flavor="stream")
        return [t.df for t in tables]
    except Exception as e:
        logger.warning(f"Camelot extraction failed ({e}), falling back to pdfplumber")
        raw_tables = extract_tables_pdfplumber(pdf_path)
        import pandas as pd
        return [pd.DataFrame(t[1:], columns=t[0] if t else []) for t in raw_tables if t]
