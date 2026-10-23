from datetime import date, datetime, timezone, timedelta
from app.extensions import db
from app.models.repayment import RepaymentSchedule, PaymentTransaction, RepaymentStatus
from app.models.loan_application import LoanApplication, ApplicationStatus
from app.models.audit import AuditAction
from app.services.audit_service import log_audit


def add_months_to_date(source_date: date, months: int) -> date:
    """Adds `months` to a given date handling month boundaries cleanly."""
    month = source_date.month - 1 + months
    year = source_date.year + month // 12
    month = month % 12 + 1
    day = min(source_date.day, [31, 29 if year % 4 == 0 and not year % 100 == 0 or year % 400 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day)


def generate_amortization_schedule(application: LoanApplication, disbursement_date: date = None) -> list[RepaymentSchedule]:
    """
    Generates standard reducing-balance monthly repayment schedule for an approved loan.
    """
    if not disbursement_date:
        disbursement_date = date.today()

    principal = float(application.approved_amount or application.requested_amount)
    annual_rate = float(application.interest_rate)
    tenure_months = int(application.tenure_months)

    emi = application.calculate_estimated_monthly_emi()
    monthly_rate = (annual_rate / 100.0) / 12.0

    # Clean existing schedules if regenerating
    RepaymentSchedule.query.filter_by(application_id=application.id).delete()

    schedules = []
    current_principal = principal

    for i in range(1, tenure_months + 1):
        due_date = add_months_to_date(disbursement_date, i)

        interest_component = round(current_principal * monthly_rate, 2)
        principal_component = round(emi - interest_component, 2)

        # For the final installment, balance exactly to zero
        if i == tenure_months or principal_component > current_principal:
            principal_component = round(current_principal, 2)
            total_installment = round(principal_component + interest_component, 2)
            remaining = 0.00
        else:
            total_installment = round(emi, 2)
            remaining = round(current_principal - principal_component, 2)

        current_principal = remaining

        schedule_row = RepaymentSchedule(
            application_id=application.id,
            installment_number=i,
            due_date=due_date,
            principal_amount=principal_component,
            interest_amount=interest_component,
            total_installment=total_installment,
            remaining_principal=remaining,
            paid_amount=0.00,
            status=RepaymentStatus.UPCOMING,
        )
        schedules.append(schedule_row)
        db.session.add(schedule_row)

    db.session.commit()
    return schedules


def record_repayment(
    schedule: RepaymentSchedule,
    amount: float,
    payment_method: str = "ONLINE_BANKING",
    customer_id: int = None,
) -> PaymentTransaction:
    """
    Records a payment transaction against a specific repayment schedule installment.
    Updates schedule status and checks for total loan completion.
    """
    if amount <= 0:
        raise ValueError("Payment amount must be greater than zero.")

    app = schedule.application
    if not customer_id:
        customer_id = app.customer_id

    # Create transaction
    txn = PaymentTransaction(
        schedule_id=schedule.id,
        application_id=app.id,
        customer_id=customer_id,
        amount=amount,
        payment_method=payment_method,
        status="SUCCESS",
        transaction_date=datetime.now(timezone.utc),
    )
    db.session.add(txn)

    # Update schedule row
    new_paid_total = float(schedule.paid_amount) + amount
    schedule.paid_amount = new_paid_total

    total_due = float(schedule.total_installment) + float(schedule.penalty_applied)
    if new_paid_total >= total_due:
        schedule.status = RepaymentStatus.PAID
        schedule.paid_date = date.today()
    else:
        schedule.status = RepaymentStatus.PARTIALLY_PAID

    db.session.flush()

    # Check if all installments for this application are now PAID
    unpaid_count = RepaymentSchedule.query.filter(
        RepaymentSchedule.application_id == app.id,
        RepaymentSchedule.status != RepaymentStatus.PAID,
    ).count()

    if unpaid_count == 0:
        old_status = app.status
        app.status = ApplicationStatus.COMPLETED
        log_audit(
            action=AuditAction.APPLICATION_CLOSED,
            application_id=app.id,
            actor_id=customer_id,
            previous_status=old_status,
            new_status=ApplicationStatus.COMPLETED,
            notes="All loan repayment installments settled in full. Loan marked COMPLETED.",
        )

    db.session.commit()
    return txn


def refresh_overdue_schedules():
    """Checks upcoming schedules past their due date and marks them OVERDUE."""
    today = date.today()
    overdue_items = RepaymentSchedule.query.filter(
        RepaymentSchedule.status.in_([RepaymentStatus.UPCOMING, RepaymentStatus.PARTIALLY_PAID]),
        RepaymentSchedule.due_date < today,
    ).all()

    for item in overdue_items:
        item.status = RepaymentStatus.OVERDUE
        # Standard 2% late fee penalty simulation
        if item.penalty_applied == 0:
            item.penalty_applied = round(float(item.total_installment) * 0.02, 2)

    if overdue_items:
        db.session.commit()
    return len(overdue_items)
