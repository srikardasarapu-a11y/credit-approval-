"""
OCR utility: wraps Tesseract for scanned document text extraction.
Uses OpenCV for image preprocessing before OCR to improve accuracy.
"""
import io
import logging
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    logger.warning("pytesseract not available — OCR will be skipped")


def preprocess_image(image: np.ndarray) -> np.ndarray:
    """
    Preprocess image for improved OCR:
    - Convert to grayscale
    - Apply adaptive thresholding (handles uneven lighting)
    - Deskew image
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # Adaptive threshold to handle shadows
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 2
    )
    return thresh


def deskew(image: np.ndarray) -> np.ndarray:
    """Correct skew in scanned documents."""
    coords = np.column_stack(np.where(image > 0))
    if len(coords) == 0:
        return image
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    (h, w) = image.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_CUBIC,
                              borderMode=cv2.BORDER_REPLICATE)
    return rotated


def extract_text_from_image(image: np.ndarray, lang: str = "eng") -> str:
    """Extract text from a numpy image array using Tesseract."""
    if not TESSERACT_AVAILABLE:
        return ""
    preprocessed = preprocess_image(image)
    preprocessed = deskew(preprocessed)
    config = "--oem 3 --psm 6"
    text = pytesseract.image_to_string(preprocessed, lang=lang, config=config)
    return text.strip()


def extract_text_from_pil(pil_image: Image.Image, lang: str = "eng") -> str:
    """Extract text from a PIL Image."""
    arr = np.array(pil_image.convert("RGB"))
    return extract_text_from_image(arr, lang)


def extract_text_from_bytes(image_bytes: bytes, lang: str = "eng") -> str:
    """Extract text from raw image bytes."""
    arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return ""
    return extract_text_from_image(img, lang)
