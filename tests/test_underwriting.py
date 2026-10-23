from app.extensions import db
from app.models.user import User, UserRole
from app.models.customer import CustomerProfile
from app.models.loan_product import LoanProduct
from app.models.loan_application import LoanApplication, ApplicationStatus
from app.services.underwriting_engine import evaluate_loan_application
from app.models.underwriting import UnderwritingOutcome


def test_underwriting_eligible_case(app):
    with app.app_context():
        user = User(
            email="prime.borrower@example.com",
            first_name="Jane",
            last_name="Doe",
            role=UserRole.CUSTOMER,
        )
        user.set_password("SecurePassword123")
        db.session.add(user)
        db.session.flush()

        profile = CustomerProfile(
            user_id=user.id,
            annual_income=120000.00,
            monthly_debt=500.00,
            credit_score=780,
        )
        db.session.add(profile)

        product = LoanProduct.query.filter_by(code="PERSONAL_PRIME").first()

        application = LoanApplication(
            customer_id=user.id,
            product_id=product.id,
            requested_amount=15000.00,
            tenure_months=36,
            interest_rate=product.base_interest_rate,
            monthly_income_declared=10000.00,
            existing_monthly_debt=500.00,
            status=ApplicationStatus.SUBMITTED,
        )
        db.session.add(application)
        db.session.commit()

        assessment = evaluate_loan_application(application)

        assert assessment.overall_result == UnderwritingOutcome.ELIGIBLE
        assert assessment.credit_score_passed is True
        assert assessment.dti_passed is True
        assert application.risk_score < 40.0


def test_underwriting_high_dti_ineligible_case(app):
    with app.app_context():
        user = User(
            email="highdebt.borrower@example.com",
            first_name="Tom",
            last_name="Hardy",
            role=UserRole.CUSTOMER,
        )
        user.set_password("SecurePassword123")
        db.session.add(user)
        db.session.flush()

        profile = CustomerProfile(
            user_id=user.id,
            annual_income=24000.00,  # $2000/month
            monthly_debt=1200.00,    # High existing debt
            credit_score=520,        # Poor credit score
        )
        db.session.add(profile)

        product = LoanProduct.query.filter_by(code="PERSONAL_PRIME").first()

        application = LoanApplication(
            customer_id=user.id,
            product_id=product.id,
            requested_amount=40000.00,
            tenure_months=24,
            interest_rate=product.base_interest_rate,
            monthly_income_declared=2000.00,
            existing_monthly_debt=1200.00,
            status=ApplicationStatus.SUBMITTED,
        )
        db.session.add(application)
        db.session.commit()

        assessment = evaluate_loan_application(application)

        assert assessment.overall_result == UnderwritingOutcome.INELIGIBLE
        assert assessment.dti_passed is False
        assert application.risk_score >= 70.0
