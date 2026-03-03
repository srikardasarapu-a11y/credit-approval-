import uuid
from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, JSON, ForeignKey, Text, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import enum
from app.database import Base


class ApplicationStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    REJECTED = "rejected"
    ERROR = "error"


class RiskGrade(str, enum.Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_name: Mapped[str] = mapped_column(String(255))
    cin: Mapped[str | None] = mapped_column(String(21))
    gstin: Mapped[str | None] = mapped_column(String(15))
    status: Mapped[ApplicationStatus] = mapped_column(
        SAEnum(ApplicationStatus), default=ApplicationStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Parsed financial data stored as JSON
    gst_data: Mapped[dict | None] = mapped_column(JSON)
    bank_data: Mapped[dict | None] = mapped_column(JSON)
    itr_data: Mapped[dict | None] = mapped_column(JSON)
    reconciliation_data: Mapped[dict | None] = mapped_column(JSON)
    research_data: Mapped[dict | None] = mapped_column(JSON)

    # Scoring
    credit_score: Mapped[float | None] = mapped_column(Float)
    risk_grade: Mapped[str | None] = mapped_column(String(1))
    financial_ratios: Mapped[dict | None] = mapped_column(JSON)
    shap_values: Mapped[dict | None] = mapped_column(JSON)
    rule_flags: Mapped[list | None] = mapped_column(JSON)

    # Loan Decision
    recommended_loan_amount: Mapped[float | None] = mapped_column(Float)
    interest_rate: Mapped[float | None] = mapped_column(Float)
    loan_decision_reasons: Mapped[list | None] = mapped_column(JSON)
    collateral_value: Mapped[float | None] = mapped_column(Float)

    # Report
    cam_path: Mapped[str | None] = mapped_column(String(500))
    error_message: Mapped[str | None] = mapped_column(Text)

    documents: Mapped[list["Document"]] = relationship("Document", back_populates="application")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    application_id: Mapped[str] = mapped_column(String(36), ForeignKey("applications.id"))
    doc_type: Mapped[str] = mapped_column(String(50))  # gst_csv | itr_pdf | bank_pdf
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(500))
    file_size: Mapped[int | None] = mapped_column(Integer)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    application: Mapped["Application"] = relationship("Application", back_populates="documents")
