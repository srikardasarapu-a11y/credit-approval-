# CreditSight AI — Credit Appraisal Engine

> Production-grade AI-driven credit appraisal system built with **FastAPI + React**.

---

## Features

| Module | Description |
|---|---|
| 📥 **Data Ingestion** | GST CSV, ITR PDF, Bank Statement PDF parsing with OCR (Tesseract) + Camelot |
| 🏦 **Advanced Bank Metrics** | Average daily balance, EMI/recurring detection, unusual tx flagging, bounce detection |
| ⚖️ **Reconciliation** | Monthly GST vs Bank credit comparison with anomaly flagging |
| 🔎 **Research Agent** | NewsAPI, MCA filings, eCourts case lookup |
| 📊 **Scoring Engine** | XGBoost v2 (12 features) + SHAP explanations + rule-based gates (bounce, overleverage, fraud) |
| 💰 **Loan Decision** | EMI-adjusted cash-flow capacity + collateral LTV + risk-adjusted rate |
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

### 3. Running Unit Tests

```bash
cd backend
python -m pytest tests/ -v -q
# Expected: 10+ tests pass
```

### 4. Manual Verification Script

```bash
cd backend
python scripts/verify_scoring.py
# Runs 5 scoring/loan decision cases and prints results
```

### 5. Feature Importance Report (requires trained v2 model)

```bash
cd backend
python scripts/train_model.py          # generates credit_model_v2.pkl
python scripts/feature_importance_report.py   # prints top-10 SHAP features
```

---

## Required Local Binaries

| Binary | Purpose | Graceful fallback? |
|---|---|---|
| [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) | PDF OCR fallback | ✅ Yes — table extraction used first |
| [Ghostscript](https://ghostscript.com/) | Camelot PDF table extraction | ✅ Yes — pdfplumber fallback |
| [LibreOffice](https://www.libreoffice.org/) | PDF export of CAM report (optional) | ✅ Yes — DOCX only |

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

The XGBoost v2 model uses **12 features**:

| Feature | Description |
|---|---|
| `dscr` | Debt Service Coverage Ratio (EMI-adjusted) |
| `de_ratio` | Debt/Equity |
| `current_ratio` | Current Ratio |
| `interest_coverage` | Interest Coverage |
| `gross_margin` | Gross Profit Margin |
| `log_revenue` | Log of annual revenue |
| `research_risk` | External research risk score (0–1) |
| `average_daily_balance` | 🆕 Carry-forward daily average balance (₹) |
| `average_transactional_balance` | 🆕 Mean of balance-after-tx (₹) |
| `emi_estimated_monthly` | 🆕 Detected monthly EMI burden (₹) |
| `unusual_count` | 🆕 Count of anomalous transactions |
| `bounce_count` | 🆕 Count of returned/bounced cheques |

**Hard rules:**
- DSCR (EMI-adjusted) < 1.0 → auto-reject
- Negative equity → auto-reject
- `bounce_count ≥ 3` → auto-reject
- `unusual_count ≥ 2` and any >5× median → `fraud_suspected` (manual review)
- `emi / avg_monthly_net > 0.5` → `overleveraged` flag

**Score:** 0–1000. **Grades:** A (≥800) B (≥650) C (≥500) D (≥350) E (<350)

---

## Tech Stack

**Backend:** FastAPI, SQLAlchemy (async), PostgreSQL, Alembic, XGBoost, SHAP, Camelot, pdfplumber, Tesseract, python-docx  
**Frontend:** React 18, Vite, Recharts, Axios, React Router, Lucide Icons
