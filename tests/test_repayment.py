from datetime import date
from app.extensions import db
from app.models.user import User, UserRole
from app.models.loan_product import LoanProduct
from app.models.loan_application import LoanApplication, ApplicationStatus
from app.models.repayment import RepaymentSchedule, RepaymentStatus
from app.services.repayment_engine import generate_amortization_schedule, record_repayment


def test_amortization_schedule_math(app):
    with app.app_context():
        user = User(
            email="repay.tester@example.com",
            first_name="Sam",
            last_name="Winchester",
            role=UserRole.CUSTOMER,
        )
        user.set_password("SecurePassword123")
        db.session.add(user)
        db.session.flush()

        product = LoanProduct.query.filter_by(code="PERSONAL_PRIME").first()

        application = LoanApplication(
            customer_id=user.id,
            product_id=product.id,
            requested_amount=12000.00,
            approved_amount=12000.00,
            tenure_months=12,
            interest_rate=12.00,
            status=ApplicationStatus.APPROVED,
        )
        db.session.add(application)
        db.session.commit()

        schedules = generate_amortization_schedule(application, disbursement_date=date(2026, 1, 1))

        # Check total installments match tenure
        assert len(schedules) == 12

        # Sum of principal components must match approved amount exactly
        total_principal = sum(float(s.principal_amount) for s in schedules)
        assert abs(total_principal - 12000.00) < 0.05

        # Final remaining principal must be 0
        assert float(schedules[-1].remaining_principal) == 0.00


def test_record_repayment_full_lifecycle(app):
    with app.app_context():
        user = User(
            email="pay.tester@example.com",
            first_name="Dean",
            last_name="Winchester",
            role=UserRole.CUSTOMER,
        )
        user.set_password("SecurePassword123")
        db.session.add(user)
        db.session.flush()

        product = LoanProduct.query.filter_by(code="PERSONAL_PRIME").first()

        application = LoanApplication(
            customer_id=user.id,
            product_id=product.id,
            requested_amount=1000.00,
            approved_amount=1000.00,
            tenure_months=2,
            interest_rate=10.00,
            status=ApplicationStatus.DISBURSED,
        )
        db.session.add(application)
        db.session.commit()

        schedules = generate_amortization_schedule(application)
        first_installment = schedules[0]

        # Pay installment #1
        due_amount = float(first_installment.total_installment)
        txn = record_repayment(first_installment, amount=due_amount, customer_id=user.id)

        assert txn.status == "SUCCESS"
        assert first_installment.status == RepaymentStatus.PAID
        assert application.status == ApplicationStatus.DISBURSED

        # Pay installment #2 to settle loan
        second_installment = schedules[1]
        record_repayment(second_installment, amount=float(second_installment.total_installment), customer_id=user.id)

        assert second_installment.status == RepaymentStatus.PAID
        # Application should transition to COMPLETED
        assert application.status == ApplicationStatus.COMPLETED
