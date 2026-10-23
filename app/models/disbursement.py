from datetime import datetime, timezone
import random
from app.extensions import db


class DisbursementMethod:
    DIRECT_DEPOSIT = "DIRECT_DEPOSIT"
    BANK_TRANSFER = "BANK_TRANSFER"
    NEFT_RTGS = "NEFT_RTGS"
    CHEQUE = "CHEQUE"

    ALL_METHODS = [DIRECT_DEPOSIT, BANK_TRANSFER, NEFT_RTGS, CHEQUE]


class DisbursementStatus:
    PENDING = "PENDING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


def generate_disbursement_reference():
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    random_hex = f"{random.randint(100000, 999999)}"
    return f"DSB-{date_str}-{random_hex}"


class Disbursement(db.Model):
    __tablename__ = "disbursements"

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("loan_applications.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    authorized_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    disbursement_reference = db.Column(db.String(64), unique=True, nullable=False, default=generate_disbursement_reference, index=True)
    amount = db.Column(db.Numeric(14, 2), nullable=False)
    disbursement_method = db.Column(db.String(50), nullable=False, default=DisbursementMethod.DIRECT_DEPOSIT)
    
    # Masked PII - Security Rule #19
    bank_name = db.Column(db.String(100), nullable=False)
    bank_account_masked = db.Column(db.String(50), nullable=False)
    bank_routing_or_ifsc = db.Column(db.String(50), nullable=True)

    status = db.Column(db.String(30), nullable=False, default=DisbursementStatus.PROCESSED)
    notes = db.Column(db.Text, nullable=True)

    disbursed_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    application = db.relationship("LoanApplication", back_populates="disbursement")
    authorizer = db.relationship("User", foreign_keys=[authorized_by_id])

    def __repr__(self):
        return f"<Disbursement {self.disbursement_reference} Amt={self.amount} Status={self.status}>"
