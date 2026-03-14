# Changelog

All notable changes to CreditSight AI are documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased] — feat/advanced-bank-metrics

### Added

#### Bank Statement Parser (`bank_parser.py`)
- **`average_daily_balance`** — carry-forward daily balance algorithm across statement period
- **`average_transactional_balance`** — mean of balance-after-transaction across all transactions
- **`balance_quality`** indicator (`'high'` / `'low'`) when running balances unavailable
- **`detect_recurring_debits()`** — detects EMI/recurring debits by merchant token + keyword heuristic
- **`emi_estimated_monthly`** — sum of median amounts across detected recurring debit series
- **`detect_unusual_transactions()`** — flags transactions ≥3× median, ≥3× mean, or top-1% with timing check
- **`unusual_count`** — integer count of anomalous transactions
- **`is_bounce()`** / **`bounce_count`** — returns/bounced cheque detection

#### SQLAlchemy Model (`models/application.py`)
- New columns: `average_daily_balance`, `average_transactional_balance`, `emi_estimated_monthly` (DECIMAL 18,2)
- New columns: `recurring_payments`, `unusual_transactions` (JSON)
- New columns: `unusual_count`, `bounce_count` (Integer)

#### Pydantic Schema (`schemas/application.py`)
- All 7 new fields added to `ApplicationOut` with `ge=0` validators

#### Scoring Engine (`scoring_engine.py`)
- **Bounce rules**: bounce_count ≥ 3 → `auto_reject_bounce` (hard reject); 2 → −200 pts; 1 → −100 pts
- **Fraud flag**: unusual_count ≥ 2 with any >5× median → `fraud_suspected` (manual review)
- **Overleverage flag**: `emi / avg_monthly_net > 0.5` → `overleveraged` with −150 pt penalty
- **EMI-adjusted DSCR**: `DSCR = NOI / (ADS + 12 × emi_estimated_monthly)`
- **v2 feature vector** (12 features) for `credit_model_v2.pkl`
- **`explanation`** field: human-readable string combining rule_flags + top SHAP insights
- Structured `rule_flags_dict` boolean map alongside existing list

#### Loan Decision (`loan_decision.py`)
- Replaced cash-flow formula: `adjusted = max(0, avg_net_credit - emi); capacity = 0.5 × adjusted × 12`
- New output fields: `emi_estimated_monthly`, `adjusted_avg_monthly_net_credit`
- `compute_loan_decision()` accepts `emi_estimated_monthly` parameter (default=0, backward-compatible)

#### ML Training (`scripts/train_model.py`)
- 5 new synthetic features in training data (average balances, EMI, bounce/unusual counts)
- Imputation defaults: `emi_estimated_monthly=0`, `bounce_count=0`, `unusual_count=0`, balances→median
- Saves to `models_ml/credit_model_v2.pkl`

#### New Scripts
- `scripts/feature_importance_report.py` — prints top-10 SHAP features; reports % of rejections with bank metrics in top-3
- `scripts/verify_scoring.py` — 5 manual verification cases (bounce reject, overleverage, loan spec)
- `scripts/demo_analyze_sample.sh` — end-to-end shell demo (upload → analyze → print results)

#### Tests (`backend/tests/`)
- `tests/test_bank_parser.py` — Cases A–D (average balance, EMI, unusual tx, bounce detection)
- `tests/test_loan_decision.py` — Spec §8 exact assertions + edge cases
- `conftest.py` — sys.path setup for pytest

### Changed
- `bank_data_to_dict()` now exports all new metrics alongside legacy fields
- `ScoringEngine` auto-detects and loads v2 model (12 features) or falls back to v1 (7 features)
- `_rule_checks()` refactored to accept `bank_data` dict and return structured `rule_flags_dict`

---

## Previous versions
See git history for changes prior to this feature branch.
