from app.extensions import db
from app.models.underwriting import UnderwritingAssessment, UnderwritingOutcome
from app.models.loan_application import LoanApplication
from app.models.customer import CustomerProfile


def evaluate_loan_application(
    application: LoanApplication,
    evaluator_id: int = None,
    custom_notes: str = None,
) -> UnderwritingAssessment:
    """
    Executes rule-based underwriting evaluation on a loan application.
    Calculates DTI, EMI-to-income, credit score eligibility, and computes a risk score.
    """
    product = application.product
    customer = application.customer
    profile = customer.customer_profile or CustomerProfile(user_id=customer.id)

    # Financial parameters
    monthly_income = float(application.monthly_income_declared or profile.monthly_income or 0.0)
    existing_debt = float(application.existing_monthly_debt or profile.monthly_debt or 0.0)
    requested_amount = float(application.requested_amount)
    tenure_months = int(application.tenure_months)
    credit_score = profile.credit_score if profile.credit_score is not None else 650

    # 1. Calculate Estimated Monthly Installment (EMI)
    estimated_emi = application.calculate_estimated_monthly_emi()

    # 2. Calculate Debt-to-Income (DTI) and EMI-to-Income
    if monthly_income > 0:
        total_monthly_obligations = existing_debt + estimated_emi
        dti_ratio = round((total_monthly_obligations / monthly_income) * 100.0, 2)
        emi_to_income_ratio = round((estimated_emi / monthly_income) * 100.0, 2)
    else:
        dti_ratio = 100.0
        emi_to_income_ratio = 100.0

    # 3. Rule Evaluations
    min_score_required = product.min_credit_score if product else 650
    max_dti_allowed = float(product.max_dti_ratio) if product else 50.0

    rule_credit = {
        "rule": "Minimum Credit Score",
        "required": min_score_required,
        "actual": credit_score,
        "passed": credit_score >= min_score_required,
    }

    rule_dti = {
        "rule": "Maximum Debt-To-Income (DTI) Ratio",
        "threshold_pct": max_dti_allowed,
        "actual_pct": dti_ratio,
        "passed": dti_ratio <= max_dti_allowed,
    }

    rule_amount = {
        "rule": "Loan Amount Bounds",
        "min": float(product.min_amount) if product else 1000.0,
        "max": float(product.max_amount) if product else 500000.0,
        "actual": requested_amount,
        "passed": (
            (float(product.min_amount) <= requested_amount <= float(product.max_amount))
            if product
            else True
        ),
    }

    rule_tenure = {
        "rule": "Tenure Bounds",
        "min_months": product.min_tenure_months if product else 6,
        "max_months": product.max_tenure_months if product else 60,
        "actual_months": tenure_months,
        "passed": (
            (product.min_tenure_months <= tenure_months <= product.max_tenure_months)
            if product
            else True
        ),
    }

    rule_income = {
        "rule": "Income Sufficiency (EMI <= 45% Monthly Income)",
        "threshold_pct": 45.0,
        "actual_pct": emi_to_income_ratio,
        "passed": emi_to_income_ratio <= 45.0 and monthly_income > 0,
    }

    rule_breakdown = {
        "credit_score": rule_credit,
        "dti": rule_dti,
        "amount_bounds": rule_amount,
        "tenure_bounds": rule_tenure,
        "income_sufficiency": rule_income,
    }

    # 4. Compute Composite Risk Score (0 = ultra safe, 100 = extreme risk)
    # Credit factor (weight 40%)
    credit_factor = max(0.0, min(100.0, (850 - credit_score) / (850 - 300) * 100.0))
    # DTI factor (weight 40%)
    dti_factor = max(0.0, min(100.0, (dti_ratio / 65.0) * 100.0))
    # EMI burden factor (weight 20%)
    emi_factor = max(0.0, min(100.0, (emi_to_income_ratio / 50.0) * 100.0))

    composite_risk = round(0.40 * credit_factor + 0.40 * dti_factor + 0.20 * emi_factor, 2)
    composite_risk = max(5.0, min(98.0, composite_risk))

    # 5. Determine Overall Outcome
    if (
        not rule_amount["passed"]
        or not rule_tenure["passed"]
        or credit_score < 550
        or dti_ratio > 65.0
        or monthly_income <= 0
    ):
        overall_result = UnderwritingOutcome.INELIGIBLE
        summary_note = "High risk profile: fails critical debt or minimum credit/income criteria."
    elif (
        rule_credit["passed"]
        and rule_dti["passed"]
        and rule_income["passed"]
        and rule_amount["passed"]
        and rule_tenure["passed"]
    ):
        overall_result = UnderwritingOutcome.ELIGIBLE
        summary_note = "Applicant meets all rule criteria within prime guidelines."
    else:
        overall_result = UnderwritingOutcome.REFER
        summary_note = "Borderline metrics: recommended for manual underwriter review."

    # 6. Save or update UnderwritingAssessment record
    assessment = application.underwriting
    if not assessment:
        assessment = UnderwritingAssessment(application_id=application.id)
        db.session.add(assessment)

    assessment.evaluator_id = evaluator_id
    assessment.debt_to_income_ratio = dti_ratio
    assessment.estimated_emi = estimated_emi
    assessment.emi_to_income_ratio = emi_to_income_ratio
    assessment.credit_score_passed = rule_credit["passed"]
    assessment.dti_passed = rule_dti["passed"]
    assessment.income_passed = rule_income["passed"]
    assessment.overall_result = overall_result
    assessment.rule_breakdown = rule_breakdown
    assessment.notes = custom_notes or summary_note

    # Sync to application fields
    application.risk_score = composite_risk
    application.automated_decision = overall_result
    application.automated_notes = summary_note

    db.session.commit()
    return assessment
