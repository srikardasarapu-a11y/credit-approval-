# CreditSight AI — Build Walkthrough

## What Was Built

A full-stack **AI-driven credit appraisal engine** with FastAPI backend and React frontend.

---

## Verification Results

| Check | Result |
|---|---|
| `npm install` | ✅ Completed, 0 errors |
| `npm run build` | ✅ Built in 6.87s, 2327 modules |
| XGBoost model training | ✅ 2000 samples, model saved to `models_ml/credit_model.pkl` |
| Backend package install | ✅ All core packages installed |

---

## File Structure Created

```
credit_iit/
├── backend/
│   ├── app/
│   │   ├── main.py                    ✅ FastAPI entry point + CORS + lifespan
│   │   ├── config.py                  ✅ Pydantic settings from .env
│   │   ├── database.py                ✅ Async SQLAlchemy engine + init_db
│   │   ├── models/application.py      ✅ Application + Document ORM models
│   │   ├── schemas/application.py     ✅ Pydantic API schemas
│   │   ├── routers/
│   │   │   ├── upload.py              ✅ POST /api/upload (multipart)
│   │   │   ├── applications.py        ✅ POST /analyze + GET /results
│   │   │   └── reports.py             ✅ GET /cam (streaming PDF download)
│   │   ├── services/
│   │   │   ├── ingestion/
│   │   │   │   ├── gst_parser.py      ✅ CSV parsing, monthly aggregation
│   │   │   │   ├── bank_parser.py     ✅ Camelot → pdfplumber → OCR fallback
│   │   │   │   └── itr_parser.py      ✅ Regex keyword extraction + OCR
│   │   │   ├── reconciliation.py      ✅ Monthly mismatch + anomaly detection
│   │   │   ├── research_agent.py      ✅ NewsAPI + MCA + eCourts async agent
│   │   │   ├── scoring_engine.py      ✅ XGBoost + SHAP + rule gates
│   │   │   ├── loan_decision.py       ✅ Cash-flow + LTV + rate pricing
│   │   │   └── cam_generator.py       ✅ DOCX template + SHAP chart + PDF
│   │   └── utils/
│   │       ├── ocr.py                 ✅ OpenCV preprocessing + Tesseract
│   │       └── pdf_utils.py           ✅ pdfplumber + Camelot + pdf2image
│   ├── scripts/train_model.py         ✅ Synthetic data + XGBoost trainer
│   ├── data/samples/sample_gst.csv    ✅ Sample GST CSV for testing
│   ├── models_ml/credit_model.pkl     ✅ Trained model (auto-generated)
│   ├── requirements.txt               ✅
│   └── .env + .env.example            ✅
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── UploadPage.jsx         ✅ Drag-drop + company form
│   │   │   ├── ApplicationsPage.jsx   ✅ List with auto-refresh polling
│   │   │   ├── DashboardPage.jsx      ✅ Score ring, SHAP, radar, recon charts
│   │   │   ├── ReviewPage.jsx         ✅ Parsed data tables + anomaly rows
│   │   │   └── ReportPage.jsx         ✅ Five Cs + CAM download
│   │   ├── api/client.js              ✅ Axios wrapper
│   │   ├── App.jsx                    ✅ Router + Sidebar
│   │   ├── main.jsx                   ✅
│   │   └── index.css                  ✅ Full design system (dark, gradients)
│   ├── package.json, vite.config.js   ✅
│   └── dist/ (built)                  ✅
├── templates/                          (DOCX template — generated at first CAM run)
└── README.md                           ✅
```

---

## Pipeline Flow

```
Upload → Parse (GST+Bank+ITR) → Reconcile → Research → Score+SHAP → Loan Decision → CAM Generation
```

All steps run as a **FastAPI background task** — UI polls for completion every 3 seconds.

---

## How to Start

**Terminal 1 — Backend:**
```bash
cd credit_iit/backend
uvicorn app.main:app --reload --port 8000
```

**Terminal 2 — Frontend:**
```bash
cd credit_iit/frontend
npm run dev
```

Open **http://localhost:5173** and create your first credit application.

---

## Notes
- PostgreSQL is required for the backend. Edit [backend/.env](file:///c:/Users/srika/OneDrive/Desktop/credit_iit/backend/.env) with your DB credentials.
- Tesseract and Ghostscript are needed for OCR / PDF table extraction.
- Without API keys, research agent returns mock/empty data gracefully.
- LibreOffice or docx2pdf needed for actual PDF CAM; DOCX always generated.
