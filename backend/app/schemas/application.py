from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class ApplicationCreate(BaseModel):
    company_name: str
    cin: Optional[str] = None
    gstin: Optional[str] = None
    collateral_value: Optional[float] = None


class ApplicationOut(BaseModel):
    id: str
    company_name: str
    cin: Optional[str]
    gstin: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime
    credit_score: Optional[float]
    risk_grade: Optional[str]
    financial_ratios: Optional[dict]
    shap_values: Optional[dict]
    rule_flags: Optional[list]
    recommended_loan_amount: Optional[float]
    interest_rate: Optional[float]
    loan_decision_reasons: Optional[list]
    reconciliation_data: Optional[dict]
    research_data: Optional[dict]
    gst_data: Optional[dict]
    bank_data: Optional[dict]
    itr_data: Optional[dict]
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
