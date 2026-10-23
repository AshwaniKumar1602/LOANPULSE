from datetime import datetime, timezone
from app.extensions import db


class KycStatus:
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class CustomerProfile(db.Model):
    __tablename__ = "customer_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    
    dob = db.Column(db.Date, nullable=True)
    employment_type = db.Column(db.String(50), nullable=False, default="SALARIED")  # SALARIED, SELF_EMPLOYED, BUSINESS, RETIRED
    annual_income = db.Column(db.Numeric(14, 2), nullable=False, default=0.00)
    monthly_debt = db.Column(db.Numeric(14, 2), nullable=False, default=0.00)
    credit_score = db.Column(db.Integer, nullable=True)  # Estimated 300-850
    kyc_status = db.Column(db.String(30), nullable=False, default=KycStatus.PENDING)

    # Masked PII - Security Rule #19 (avoid saving full tax identifiers in plain text)
    tax_id_masked = db.Column(db.String(50), nullable=True)  # e.g. "XXXX-XX-1234" or "ABCDE****F"
    
    address_line = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    state = db.Column(db.String(100), nullable=True)
    postal_code = db.Column(db.String(30), nullable=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationship
    user = db.relationship("User", back_populates="customer_profile")

    @property
    def monthly_income(self) -> float:
        if self.annual_income:
            return float(self.annual_income) / 12.0
        return 0.0

    def __repr__(self):
        return f"<CustomerProfile UserID={self.user_id} KYC={self.kyc_status}>"
