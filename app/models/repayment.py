from datetime import datetime, timezone
import random
from app.extensions import db


class RepaymentStatus:
    UPCOMING = "UPCOMING"
    PAID = "PAID"
    OVERDUE = "OVERDUE"
    PARTIALLY_PAID = "PARTIALLY_PAID"

    ALL_STATUSES = [UPCOMING, PAID, OVERDUE, PARTIALLY_PAID]


def generate_payment_ref():
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    random_hex = f"{random.randint(100000, 999999)}"
    return f"TXN-{date_str}-{random_hex}"


class RepaymentSchedule(db.Model):
    __tablename__ = "repayment_schedules"

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("loan_applications.id", ondelete="CASCADE"), nullable=False, index=True)
    
    installment_number = db.Column(db.Integer, nullable=False)
    due_date = db.Column(db.Date, nullable=False, index=True)
    
    principal_amount = db.Column(db.Numeric(14, 2), nullable=False)
    interest_amount = db.Column(db.Numeric(14, 2), nullable=False)
    total_installment = db.Column(db.Numeric(14, 2), nullable=False)  # Equated Monthly Installment
    remaining_principal = db.Column(db.Numeric(14, 2), nullable=False)
    
    paid_amount = db.Column(db.Numeric(14, 2), nullable=False, default=0.00)
    paid_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(30), nullable=False, default=RepaymentStatus.UPCOMING, index=True)
    penalty_applied = db.Column(db.Numeric(14, 2), nullable=False, default=0.00)

    # Relationships
    application = db.relationship("LoanApplication", back_populates="repayment_schedules")
    transactions = db.relationship("PaymentTransaction", back_populates="schedule", cascade="all, delete-orphan", lazy="dynamic")

    @property
    def outstanding_balance(self) -> float:
        total_due = float(self.total_installment) + float(self.penalty_applied)
        return max(0.0, round(total_due - float(self.paid_amount), 2))

    def __repr__(self):
        return f"<RepaymentSchedule App #{self.application_id} #{self.installment_number} Due={self.due_date} Status={self.status}>"


class PaymentTransaction(db.Model):
    __tablename__ = "payment_transactions"

    id = db.Column(db.Integer, primary_key=True)
    schedule_id = db.Column(db.Integer, db.ForeignKey("repayment_schedules.id", ondelete="CASCADE"), nullable=False, index=True)
    application_id = db.Column(db.Integer, db.ForeignKey("loan_applications.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    transaction_ref = db.Column(db.String(64), unique=True, nullable=False, default=generate_payment_ref, index=True)
    amount = db.Column(db.Numeric(14, 2), nullable=False)
    payment_method = db.Column(db.String(50), nullable=False, default="ONLINE_BANKING")
    status = db.Column(db.String(30), nullable=False, default="SUCCESS")
    
    transaction_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    schedule = db.relationship("RepaymentSchedule", back_populates="transactions")
    application = db.relationship("LoanApplication")
    customer = db.relationship("User")

    def __repr__(self):
        return f"<PaymentTransaction {self.transaction_ref} Amt={self.amount} Status={self.status}>"
