# LoanPulse: LoanMaster Loan Management System

A production-ready Python full-stack loan lifecycle management system built with **Flask**, **Jinja2**, **TailwindCSS**, and **Neon PostgreSQL**.

---

## 🌟 Core Features & Modules

1. **Borrower / Customer Portal**:
   - Interactive Loan EMI Calculator & visual amortization breakdown.
   - Multi-step loan origination wizard with financial & identity data capture.
   - Secure document management (UUID file isolation, binary header MIME inspection, 5MB payload limit).
   - Real-time application lifecycle tracking stepper (Draft &rarr; Submitted &rarr; Under Review &rarr; Approved &rarr; Disbursed).
   - Complete reducing-balance repayment schedules and payment simulation.

2. **Credit Underwriting & Officer Workspace**:
   - Real-time triage worklist with dynamic filtering by status, product, and borrower query.
   - Configurable Rule-Based Underwriting Engine:
     - Debt-to-Income (DTI) check
     - Minimum credit score threshold check
     - Product amount & tenure bounds verification
     - EMI burden / income sufficiency analysis
     - Algorithmic composite risk score calculation (0–100 scale)
   - In-app document inspection & verification approval/rejection with reviewer notes.
   - Formal officer recommendations to management.

3. **Loan Manager & Executive Control**:
   - Portfolio analytics & executive KPIs: Total volume, approval rate, active portfolio volume, and delinquency rate.
   - Final approval queue with terms override (approved principal & APR).
   - Capital disbursement engine with beneficiary details and bank account masking.
   - Automatic generation of amortized monthly EMI schedules upon disbursement.
   - Product catalog management (interest rates, tenure limits, DTI thresholds).
   - Streaming CSV report exports (memory-safe chunk generators for applications & repayments).
   - Full immutable decision audit trail ledger.

4. **Institutional Security & Compliance**:
   - **MFA / 2FA**: Mandatory TOTP (Time-based One-Time Password) for administrative and management staff.
   - **Password Security**: Cryptographically strong Argon2id hashing via `argon2-cffi`.
   - **IDOR Protection**: Server-side user ownership verification on every object route.
   - **XSS & CSRF**: Global Flask-WTF CSRF tokens and Jinja2 auto-escaping with Bleach sanitization.
   - **Rate Limiting**: Configured with `Flask-Limiter` on authentication and application endpoints.
   - **PII Masking**: Custom masking for Tax IDs, PAN, SSN, and bank account numbers.
   - **Clean Production Seed Policy**: Strict zero fake test user accounts or mock data in production seeds.

---

## 🎨 Theme & Visual Tokens (WCAG AA Compliant)

- **Primary Accent**: Warm Amber / Gold (`#D97706` / `#B45309` / `#F59E0B`)
- **Secondary Accent**: Deep Warm Gold (`#92400E`)
- **Light Theme Background**: Clean warm off-white (`#FAFAF9` / `#FFFBEB`)
- **Dark Theme Background**: Rich Slate / Charcoal (`#0F172A` / `#1E293B`)
- **Accessibility**: Validated high-contrast pairings (`text-slate-900 dark:text-slate-100`, `bg-amber-500 text-slate-950`).

---

## 🚀 Setup & Local Execution

### 1. Prerequisites
- Python 3.11+
- Virtual environment support

### 2. Installation
```bash
# Clone and enter directory
cd /path/to/loanpulse

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install audited dependencies
pip install -r requirements.txt
```

### 3. Environment Configuration
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
For production Neon PostgreSQL, update `DATABASE_URL` in `.env`:
```ini
DATABASE_URL=postgresql://user:password@endpoint.neon.tech/loanpulse?sslmode=require
```

### 4. Database Migrations & Clean Production Seed
```bash
# Run schema migration
flask db upgrade

# Seed essential active loan product configurations ONLY (Zero test users)
flask seed-production
```

### 5. Provision Staff Account
To create initial officer or manager accounts securely (with mandatory 2FA):
```bash
flask create-staff
```

### 6. Run the Application
**Development Server**:
```bash
python wsgi.py
```

**Production (Render Free-Tier Optimized Gunicorn)**:
```bash
gunicorn --config gunicorn.conf.py wsgi:app
```

---

## 🧪 Test Suite Execution

Run the complete test suite:
```bash
pytest
```
Tests cover Argon2id hashing, TOTP MFA, automated underwriting rules, amortization mathematics, IDOR server-side checks, file header inspection, and zero mock users policy.

## 🚀 Project Live Deployment link

https://loanpulse-dkc4.onrender.com/
