"""
Pydantic schemas for Application resource.
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class ApplicationCreate(BaseModel):
    """Schema for creating a new credit application."""
    company_name: str
    cin: Optional[str] = None
    gstin: Optional[str] = None
    collateral_value: Optional[float] = None


class ApplicationOut(BaseModel):
    """Full application output schema — mirrors the Application ORM model."""
    id: str
    company_name: str
    cin: Optional[str]
    gstin: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime

    # Scoring
    credit_score: Optional[float]
    risk_grade: Optional[str]
    financial_ratios: Optional[dict]
    shap_values: Optional[dict]
    rule_flags: Optional[list]

    # Loan decision
    recommended_loan_amount: Optional[float]
    interest_rate: Optional[float]
    loan_decision_reasons: Optional[list]

    # Parsed data blobs
    reconciliation_data: Optional[dict]
    research_data: Optional[dict]
    gst_data: Optional[dict]
    bank_data: Optional[dict]
    itr_data: Optional[dict]

    # ---- Advanced bank metrics (feat/advanced-bank-metrics) ----
    average_daily_balance: Optional[float] = Field(
        default=None, ge=0,
        description="Average daily running balance over statement period (₹)"
    )
    average_transactional_balance: Optional[float] = Field(
        default=None, ge=0,
        description="Mean of balance-after-transaction across all recorded transactions (₹)"
    )
    emi_estimated_monthly: Optional[float] = Field(
        default=None, ge=0,
        description="Estimated monthly recurring EMI obligations detected from bank statement (₹)"
    )
    recurring_payments: Optional[List[dict]] = Field(
        default=None,
        description="List of detected recurring payment series with merchant, amount, dates"
    )
    unusual_transactions: Optional[List[dict]] = Field(
        default=None,
        description="Transactions flagged as statistically anomalous"
    )
    unusual_count: Optional[int] = Field(
        default=None, ge=0,
        description="Number of unusual transactions detected"
    )
    bounce_count: Optional[int] = Field(
        default=None, ge=0,
        description="Number of returned/bounced cheque transactions"
    )

    # Report
    error_message: Optional[str]

    class Config:
        from_attributes = True


class UploadResponse(BaseModel):
    application_id: str
    message: str
    files_received: list[str]


class AnalysisResponse(BaseModel):
    application_id: str
    status: str
    message: str
