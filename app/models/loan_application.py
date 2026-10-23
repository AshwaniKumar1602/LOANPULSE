from datetime import datetime, timezone
import random
from app.extensions import db


class ApplicationStatus:
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    PENDING_DOCS = "PENDING_DOCS"
    RECOMMENDED_APPROVAL = "RECOMMENDED_APPROVAL"
    RECOMMENDED_REJECTION = "RECOMMENDED_REJECTION"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    DISBURSED = "DISBURSED"
    COMPLETED = "COMPLETED"
    DEFAULTED = "DEFAULTED"

    ALL_STATUSES = [
        DRAFT,
        SUBMITTED,
        UNDER_REVIEW,
        PENDING_DOCS,
        RECOMMENDED_APPROVAL,
        RECOMMENDED_REJECTION,
        APPROVED,
        REJECTED,
        DISBURSED,
        COMPLETED,
        DEFAULTED,
    ]

    # Deterministic Lifecycle State Machine (Phase 8: Transition Integrity)
    VALID_TRANSITIONS = {
        DRAFT: {SUBMITTED},
        SUBMITTED: {UNDER_REVIEW, PENDING_DOCS, REJECTED},
        UNDER_REVIEW: {
            PENDING_DOCS,
            RECOMMENDED_APPROVAL,
            RECOMMENDED_REJECTION,
            APPROVED,
            REJECTED,
        },
        PENDING_DOCS: {
            UNDER_REVIEW,
            SUBMITTED,
            RECOMMENDED_APPROVAL,
            RECOMMENDED_REJECTION,
            REJECTED,
        },
        RECOMMENDED_APPROVAL: {APPROVED, REJECTED, UNDER_REVIEW},
        RECOMMENDED_REJECTION: {APPROVED, REJECTED, UNDER_REVIEW},
        APPROVED: {DISBURSED, REJECTED},
        DISBURSED: {COMPLETED, DEFAULTED},
        COMPLETED: set(),
        REJECTED: set(),
        DEFAULTED: set(),
    }


def generate_application_number():
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    random_digits = f"{random.randint(1000, 9999)}"
    return f"LP-{date_str}-{random_digits}"


class LoanApplication(db.Model):
    __tablename__ = "loan_applications"

    id = db.Column(db.Integer, primary_key=True)
    application_number = db.Column(db.String(50), unique=True, nullable=False, default=generate_application_number, index=True)
    
    customer_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("loan_products.id"), nullable=False, index=True)
    
    requested_amount = db.Column(db.Numeric(14, 2), nullable=False)
    approved_amount = db.Column(db.Numeric(14, 2), nullable=True)
    tenure_months = db.Column(db.Integer, nullable=False)
    interest_rate = db.Column(db.Numeric(5, 2), nullable=False)  # Effective APR %

    monthly_income_declared = db.Column(db.Numeric(14, 2), nullable=False, default=0.00)
    existing_monthly_debt = db.Column(db.Numeric(14, 2), nullable=False, default=0.00)
    purpose = db.Column(db.Text, nullable=True)
    
    status = db.Column(db.String(40), nullable=False, default=ApplicationStatus.DRAFT, index=True)
    
    # Automated Underwriting Rules evaluation output
    risk_score = db.Column(db.Numeric(5, 2), nullable=True)  # 0 to 100 (lower is safer)
    automated_decision = db.Column(db.String(30), nullable=True)  # ELIGIBLE, INELIGIBLE, REFER
    automated_notes = db.Column(db.Text, nullable=True)

    submitted_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    customer = db.relationship("User", back_populates="applications", foreign_keys=[customer_id])
    product = db.relationship("LoanProduct", back_populates="applications")
    documents = db.relationship("ApplicationDocument", back_populates="application", cascade="all, delete-orphan", lazy="dynamic")
    underwriting = db.relationship("UnderwritingAssessment", back_populates="application", uselist=False, cascade="all, delete-orphan")
    audit_logs = db.relationship("DecisionAuditLog", back_populates="application", cascade="all, delete-orphan", lazy="dynamic", order_by="desc(DecisionAuditLog.created_at)")
    disbursement = db.relationship("Disbursement", back_populates="application", uselist=False, cascade="all, delete-orphan")
    repayment_schedules = db.relationship("RepaymentSchedule", back_populates="application", cascade="all, delete-orphan", lazy="dynamic", order_by="RepaymentSchedule.installment_number")

    def can_transition_to(self, target_status: str) -> bool:
        """Verifies whether the target status transition is valid according to the lifecycle state machine."""
        allowed = ApplicationStatus.VALID_TRANSITIONS.get(self.status, set())
        return target_status in allowed

    def transition_to(self, target_status: str) -> bool:
        """
        Validates and executes a state transition. Raises ValueError if transition is invalid.
        """
        if target_status == self.status:
            return True  # Idempotent no-op

        if not self.can_transition_to(target_status):
            raise ValueError(
                f"Invalid lifecycle transition from '{self.status}' to '{target_status}' for Application #{self.application_number}."
            )

        self.status = target_status
        return True

    def calculate_estimated_monthly_emi(self) -> float:
        """Calculates standard reducing balance Equated Monthly Installment (EMI) using Python Decimal arithmetic."""
        from app.services.calculator_service import calculate_precise_emi
        principal = self.approved_amount or self.requested_amount or 0.0
        emi_dec = calculate_precise_emi(principal, self.interest_rate or 0.0, self.tenure_months or 0)
        return float(emi_dec)

    def __repr__(self):
        return f"<LoanApplication {self.application_number} [{self.status}] Amt={self.requested_amount}>"
