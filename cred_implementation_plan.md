# Analyzing Bank Statements for Advanced Metrics

The goal of this change is to extract deeper insights from uploaded Bank Statement PDFs to better evaluate a company's financial health, specifically focusing on **Monthly Cash Flow**, **Average Balance**, **EMI Capacity**, and **Unusual Transactions**.

## Proposed Changes

### Backend Ingestion Layer
#### [MODIFY] [bank_parser.py](file:///c:/Users/srika/OneDrive/Desktop/credit_iit/backend/app/services/ingestion/bank_parser.py)
Update the [BankData](file:///c:/Users/srika/OneDrive/Desktop/credit_iit/backend/app/services/ingestion/bank_parser.py#20-35) dataclass and parsing logic:
- **Average Balance:** Calculate the average daily/transactional balance using the extracted `balance` column from the PDF tables.
- **EMI / Bounced Cheques Detection:** Add specific keywords to track recurring EMI payments mathematically to estimate their current monthly debt obligations (EMI capacity). Track bounce charges (`"return"`, `"bounce"`, `"chq ret"`).
- **Unusual Transactions Flagging:** Scan the parsed `transactions` list to flag any single credit or debit that is unusually large (e.g., > 300% of the average transaction size) or occurs at highly unusual intervals.

### Backend Application Models
#### [MODIFY] [application.py](file:///c:/Users/srika/OneDrive/Desktop/credit_iit/backend/app/models/application.py)
#### [MODIFY] [application.py (Schemas)](file:///c:/Users/srika/OneDrive/Desktop/credit_iit/backend/app/schemas/application.py)
Ensure the new bank data fields (average balance, emi_estimated, unusual_flags) are passed cleanly through the Pydantic schemas and SQLAlchemy models.

### Backend Scoring & Decision
#### [MODIFY] [scoring_engine.py](file:///c:/Users/srika/OneDrive/Desktop/credit_iit/backend/app/services/scoring_engine.py)
- Incorporate the "Bounced Cheque" and "Unusual Transaction" counts into the rule-based flags. If a company has multiple cheque bounces, auto-reject or severely downgrade the risk score.

#### [MODIFY] [loan_decision.py](file:///c:/Users/srika/OneDrive/Desktop/credit_iit/backend/app/services/loan_decision.py)
- Adjust the `cash_flow_capacity` limit. Subtract the newly discovered `estimated_emi` from the allowable loan bucket, ensuring we don't over-leverage a company that already has maxed-out monthly EMI obligations.

## Verification Plan

### Automated Tests
- Run the python backend tests (or simply dry-run the backend with an uploaded sample PDF).
- There is currently no `pytest` suite in this codebase, so I will write a temporary python script to feed a sample bank CSV/JSON into the [_classify_transaction](file:///c:/Users/srika/OneDrive/Desktop/credit_iit/backend/app/services/ingestion/bank_parser.py#41-61) and aggregation loops to verify the math is correct.

### Manual Verification
- Start the FastAPI backend and use the Swagger UI (`http://localhost:8000/docs`) to trigger the `/api/upload` and `/api/applications/{id}/analyze` endpoints.
- Check the generated CAM Document to see if the new "Average Balance" and "Unusual Transactions" flags appear in the final report.
