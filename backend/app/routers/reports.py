"""
Reports Router
GET /api/reports/{id}/cam — streams the CAM PDF/DOCX file
"""
import os
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.application import Application

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/{app_id}/cam")
async def download_cam(app_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Application).where(Application.id == app_id))
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(404, detail="Application not found")
    if app.status != "completed":
        raise HTTPException(400, detail=f"Report not ready. Status: {app.status}")
    if not app.cam_path or not os.path.exists(app.cam_path):
        raise HTTPException(404, detail="CAM file not found. Please trigger analysis first.")

    filename = f"CAM_{app.company_name.replace(' ', '_')}_{app_id[:8]}"
    ext = Path(app.cam_path).suffix
    media_type = "application/pdf" if ext == ".pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return FileResponse(
        path=app.cam_path,
        media_type=media_type,
        filename=f"{filename}{ext}",
    )
