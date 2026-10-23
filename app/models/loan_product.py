from datetime import datetime, timezone
from app.extensions import db


class LoanProduct(db.Model):
    __tablename__ = "loan_products"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)

    min_amount = db.Column(db.Numeric(14, 2), nullable=False)
    max_amount = db.Column(db.Numeric(14, 2), nullable=False)
    min_tenure_months = db.Column(db.Integer, nullable=False)
    max_tenure_months = db.Column(db.Integer, nullable=False)
    base_interest_rate = db.Column(db.Numeric(5, 2), nullable=False)  # Annual interest rate %

    min_credit_score = db.Column(db.Integer, nullable=False, default=650)
    max_dti_ratio = db.Column(db.Numeric(5, 2), nullable=False, default=50.00)  # Max allowable DTI %
    
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    applications = db.relationship("LoanApplication", back_populates="product", lazy="dynamic")

    def __repr__(self):
        return f"<LoanProduct {self.code}: {self.name} ({self.base_interest_rate}%)>"
