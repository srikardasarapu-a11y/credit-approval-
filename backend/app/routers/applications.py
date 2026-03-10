"""
Applications Router
POST /api/applications/{id}/analyze — runs the full pipeline
GET  /api/applications/{id}/results — returns scored results
GET  /api/applications/            — lists all applications
"""
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.application import Application, Document
from app.schemas.application import ApplicationOut, AnalysisResponse
from app.services.ingestion.gst_parser import parse_gst_csv, gst_data_to_dict
from app.services.ingestion.bank_parser import parse_bank_pdf, bank_data_to_dict
from app.services.ingestion.itr_parser import parse_itr_pdf, itr_data_to_dict
from app.services.reconciliation import reconcile, reconciliation_to_dict
from app.services.research_agent import run_research_agent, research_to_dict
from app.services.scoring_engine import ScoringEngine, compute_ratios, scoring_result_to_dict
from app.services.loan_decision import compute_loan_decision, loan_decision_to_dict

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/applications", tags=["applications"])

engine = ScoringEngine()   # Loaded once at startup


async def _run_pipeline(app_id: str, db: AsyncSession):
    """Full async analysis pipeline executed as a background task."""
    try:
        result = await db.execute(select(Application).where(Application.id == app_id))
        app = result.scalar_one_or_none()
        if not app:
            return

        app.status = "processing"
        await db.commit()

        # --- Fetch documents ---
        doc_result = await db.execute(select(Document).where(Document.application_id == app_id))
        documents = {d.doc_type: d.stored_path for d in doc_result.scalars().all()}

        # --- 1. Parse documents ---
        gst_data = {}
        bank_data = {}
        itr_data = {}

        if "gst_csv" in documents:
            gst = parse_gst_csv(documents["gst_csv"])
            gst_data = gst_data_to_dict(gst)

        if "bank_pdf" in documents:
            bank = parse_bank_pdf(documents["bank_pdf"])
            bank_data = bank_data_to_dict(bank)

        if "itr_pdf" in documents:
            itr = parse_itr_pdf(documents["itr_pdf"])
            itr_data = itr_data_to_dict(itr)

        # --- 2. Reconciliation ---
        recon_data = {}
        if gst_data and bank_data:
            recon = reconcile(
                gst_data.get("monthly_sales", {}),
                bank_data.get("monthly_credits", {}),
            )
            recon_data = reconciliation_to_dict(recon)

        # --- 3. Research Agent ---
        research_result = await run_research_agent(app.company_name, app.cin)
        research_data = research_to_dict(research_result)

        # --- 4. Scoring ---
        avg_monthly_credit = bank_data.get("average_monthly_credit", 0)
        revenue = itr_data.get("turnover", 0) or gst_data.get("total_taxable_sales", 0)
        net_profit = itr_data.get("net_profit", 0)
        depreciation = itr_data.get("depreciation", 0)
        ebitda = net_profit + depreciation
        # Rough estimates if detailed balance sheet not available
        total_debt = avg_monthly_credit * 12 * 0.4   # estimated
        equity = itr_data.get("gross_total_income", revenue) * 0.3
        current_assets = avg_monthly_credit * 3
        current_liabilities = avg_monthly_credit * 1.5
        interest_expense = total_debt * 0.10
        annual_debt_service = total_debt * 0.20
        gross_profit = revenue * 0.25

        ratios = compute_ratios(
            annual_debt_service=annual_debt_service,
            net_operating_income=ebitda,
            total_debt=total_debt,
            equity=equity,
            current_assets=current_assets,
            current_liabilities=current_liabilities,
            ebit=ebitda,
            interest_expense=interest_expense,
            gross_profit=gross_profit,
            revenue=revenue,
        )

        scoring = engine.score(
            ratios=ratios,
            research_risk=research_data.get("overall_research_risk", 0),
            reconciliation_risk=recon_data.get("risk_flag", False),
            bank_data=bank_data,
            mca_data=research_data.get("mca", {}),
        )
        scoring_dict = scoring_result_to_dict(scoring)

        # --- 5. Loan Decision ---
        collateral_value = app.collateral_value or (avg_monthly_credit * 24)
        loan = compute_loan_decision(
            average_monthly_credit=avg_monthly_credit,
            risk_grade=scoring.risk_grade,
            collateral_value=collateral_value,
            collateral_type="default",
            auto_reject=scoring.auto_reject,
            reject_reason=scoring.reject_reason,
            rule_flags=scoring.rule_flags,
            emi_capacity=bank_data.get("emi_capacity", 0.0),
        )
        loan_dict = loan_decision_to_dict(loan)

        # --- 6. CAM Generation ---
        cam_path = None
        try:
            from app.services.cam_generator import generate_cam
            import tempfile
            cam_path = generate_cam(
                application_id=app_id,
                company_name=app.company_name,
                gst_data=gst_data,
                bank_data=bank_data,
                itr_data=itr_data,
                reconciliation_data=recon_data,
                research_data=research_data,
                scoring_result=scoring_dict,
                loan_decision=loan_dict,
                output_dir=tempfile.gettempdir(),
            )
        except Exception as e:
            logger.warning(f"CAM generation failed: {e}")

        # --- 7. Save results ---
        app.gst_data = gst_data
        app.bank_data = bank_data
        app.itr_data = itr_data
        app.reconciliation_data = recon_data
        app.research_data = research_data
        app.financial_ratios = scoring_dict.get("financial_ratios")
        app.credit_score = scoring_dict.get("credit_score")
        app.risk_grade = scoring_dict.get("risk_grade")
        app.shap_values = scoring_dict.get("shap_values")
        app.rule_flags = scoring_dict.get("rule_flags")
        app.recommended_loan_amount = loan_dict.get("recommended_loan_amount")
        app.interest_rate = loan_dict.get("final_interest_rate")
        app.loan_decision_reasons = loan_dict.get("reasons")
        app.cam_path = cam_path
        app.status = "completed"
        await db.commit()
        logger.info(f"Pipeline completed for application {app_id}")

    except Exception as e:
        logger.exception(f"Pipeline error for {app_id}: {e}")
        try:
            result = await db.execute(select(Application).where(Application.id == app_id))
            app = result.scalar_one_or_none()
            if app:
                app.status = "error"
                app.error_message = str(e)
                await db.commit()
        except Exception:
            pass


@router.post("/{app_id}/analyze", response_model=AnalysisResponse)
async def analyze_application(
    app_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Application).where(Application.id == app_id))
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(404, detail="Application not found")
    if app.status == "processing":
        raise HTTPException(409, detail="Analysis already in progress")

    background_tasks.add_task(_run_pipeline, app_id, db)
    return AnalysisResponse(
        application_id=app_id,
        status="processing",
        message="Analysis started. Poll /api/applications/{id}/results for completion.",
    )


@router.get("/{app_id}/results", response_model=ApplicationOut)
async def get_results(app_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Application).where(Application.id == app_id))
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(404, detail="Application not found")
    return app


@router.get("/", response_model=list[ApplicationOut])
async def list_applications(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Application).order_by(Application.created_at.desc()))
    return result.scalars().all()
