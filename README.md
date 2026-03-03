# CreditSight AI — Credit Appraisal Engine

> Production-grade AI-driven credit appraisal system built with **FastAPI + React**.

---

## Features

| Module | Description |
|---|---|
| 📥 **Data Ingestion** | GST CSV, ITR PDF, Bank Statement PDF parsing with OCR (Tesseract) + Camelot |
| ⚖️ **Reconciliation** | Monthly GST vs Bank credit comparison with anomaly flagging |
| 🔎 **Research Agent** | NewsAPI, MCA filings, eCourts case lookup |
| 📊 **Scoring Engine** | XGBoost ML model + SHAP explanations + rule-based hard gates |
| 💰 **Loan Decision** | Cash-flow + collateral LTV limit + risk-adjusted rate |
| 📄 **CAM Generation** | DOCX template → PDF with embedded SHAP chart |
| 🖥 **UI** | Dark-mode React dashboard with charts and drag-drop upload |

---

## Project Structure

```
credit_iit/
├── backend/            # FastAPI Python backend
│   ├── app/
│   │   ├── main.py             # FastAPI entry point
│   │   ├── config.py           # Settings
│   │   ├── database.py         # SQLAlchemy async engine
│   │   ├── models/             # ORM models
│   │   ├── schemas/            # Pydantic schemas
│   │   ├── routers/            # API routes (upload, applications, reports)
│   │   ├── services/           # Business logic
│   │   │   ├── ingestion/      # GST/ITR/Bank parsers
│   │   │   ├── reconciliation.py
│   │   │   ├── research_agent.py
│   │   │   ├── scoring_engine.py
│   │   │   ├── loan_decision.py
│   │   │   └── cam_generator.py
│   │   └── utils/              # OCR + PDF utilities
│   ├── scripts/train_model.py  # Train XGBoost model
│   ├── data/samples/           # Sample input files
│   ├── models_ml/              # Saved ML model (auto-created)
│   └── requirements.txt
├── frontend/           # React + Vite frontend
│   └── src/
│       ├── pages/      # UploadPage, DashboardPage, ReviewPage, ReportPage
│       ├── api/        # Axios client
│       └── index.css   # Design system
└── templates/          # DOCX CAM template
```

---

## Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- PostgreSQL 14+ (or use SQLite by changing `DATABASE_URL`)
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) on PATH
- [Ghostscript](https://ghostscript.com/) on PATH (for Camelot)
- [LibreOffice](https://www.libreoffice.org/) on PATH (for PDF export, optional)

### 1. Backend

```bash
cd backend
cp .env.example .env       # Edit .env to set DB URL and API keys
pip install -r requirements.txt

# Train ML model (generates synthetic data automatically)
python scripts/train_model.py

# Start server
uvicorn app.main:app --reload --port 8000
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open: http://localhost:5173

---

## API Keys (optional)

Set in `backend/.env`:

| Variable | Service | Required? |
|---|---|---|
| `NEWSAPI_KEY` | [newsapi.org](https://newsapi.org) | Optional |
| `SUREPASS_API_KEY` | [surepass.io](https://surepass.io) | Optional |
| `COMPDATA_API_KEY` | CompData MCA API | Optional |

> If keys are blank, those sources are skipped gracefully.

---

## Usage

1. Open the app → click **New Application**
2. Fill company details, upload GST CSV + ITR PDF + Bank PDF
3. Click **Submit for Appraisal** — the AI pipeline runs in the background
4. View the **Risk Dashboard** for score, SHAP, reconciliation, and research
5. Review parsed data on the **Data Review** tab
6. Download the **Credit Appraisal Memo (CAM)** PDF

---

## Scoring Model

The XGBoost model uses 7 features:
- `dscr` — Debt Service Coverage Ratio
- `de_ratio` — Debt/Equity
- `current_ratio` — Current Ratio
- `interest_coverage` — Interest Coverage
- `gross_margin` — Gross Profit Margin
- `log_revenue` — Log of annual revenue
- `research_risk` — External research risk score (0–1)

**Hard rules:** DSCR < 1.0 or negative equity → auto-reject.

**Score:** 0–1000. **Grades:** A (≥800) B (≥650) C (≥500) D (≥350) E (<350)

---

## Tech Stack

**Backend:** FastAPI, SQLAlchemy (async), PostgreSQL, Alembic, XGBoost, SHAP, Camelot, pdfplumber, Tesseract, python-docx  
**Frontend:** React 18, Vite, Recharts, Axios, React Router, Lucide Icons
