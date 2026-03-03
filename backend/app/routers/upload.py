"""
Upload Router
POST /api/upload — accepts multipart files (gst_csv, itr_pdf, bank_pdf)
and creates a new Application record.
"""
import os
import uuid
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Form, File, UploadFile, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.application import Application, Document
from app.schemas.application import UploadResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["upload"])

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_TYPES = {
    "gst_csv": [".csv"],
    "itr_pdf": [".pdf"],
    "bank_pdf": [".pdf"],
}


def _save_file(file: UploadFile, doc_type: str, app_id: str) -> tuple[str, int]:
    """Save uploaded file and return (stored_path, file_size)."""
    ext = Path(file.filename).suffix.lower()
    filename = f"{app_id}_{doc_type}{ext}"
    dest = UPLOAD_DIR / filename
    content = file.file.read()
    with open(dest, "wb") as f:
        f.write(content)
    return str(dest), len(content)


@router.post("/upload", response_model=UploadResponse)
async def upload_documents(
    company_name: str = Form(...),
    cin: Optional[str] = Form(None),
    gstin: Optional[str] = Form(None),
    collateral_value: Optional[float] = Form(None),
    collateral_type: Optional[str] = Form("default"),
    gst_csv: Optional[UploadFile] = File(None),
    itr_pdf: Optional[UploadFile] = File(None),
    bank_pdf: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
):
    if not gst_csv and not itr_pdf and not bank_pdf:
        raise HTTPException(400, detail="At least one document must be uploaded")

    app_id = str(uuid.uuid4())
    application = Application(
        id=app_id,
        company_name=company_name,
        cin=cin,
        gstin=gstin,
        collateral_value=collateral_value,
        status="pending",
    )
    db.add(application)

    files_received = []
    for doc_type, file in [("gst_csv", gst_csv), ("itr_pdf", itr_pdf), ("bank_pdf", bank_pdf)]:
        if file is None:
            continue
        ext = Path(file.filename).suffix.lower()
        allowed = ALLOWED_TYPES.get(doc_type, [])
        if allowed and ext not in allowed:
            raise HTTPException(400, detail=f"{doc_type} must be one of {allowed}")

        stored_path, size = _save_file(file, doc_type, app_id)
        doc = Document(
            application_id=app_id,
            doc_type=doc_type,
            original_filename=file.filename,
            stored_path=stored_path,
            file_size=size,
        )
        db.add(doc)
        files_received.append(file.filename)

    await db.commit()
    logger.info(f"New application {app_id} created with {len(files_received)} documents")

    return UploadResponse(
        application_id=app_id,
        message="Documents uploaded successfully. Call /api/applications/{id}/analyze to process.",
        files_received=files_received,
    )
