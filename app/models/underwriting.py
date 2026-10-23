from datetime import datetime, timezone
from app.extensions import db


class UnderwritingOutcome:
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    REFER = "REFER"


class UnderwritingAssessment(db.Model):
    __tablename__ = "underwriting_assessments"

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("loan_applications.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    evaluator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    debt_to_income_ratio = db.Column(db.Numeric(5, 2), nullable=False)
    estimated_emi = db.Column(db.Numeric(14, 2), nullable=False)
    emi_to_income_ratio = db.Column(db.Numeric(5, 2), nullable=False)
    
    credit_score_passed = db.Column(db.Boolean, nullable=False, default=False)
    dti_passed = db.Column(db.Boolean, nullable=False, default=False)
    income_passed = db.Column(db.Boolean, nullable=False, default=False)
    
    overall_result = db.Column(db.String(30), nullable=False, default=UnderwritingOutcome.REFER)
    rule_breakdown = db.Column(db.JSON, nullable=True)  # Detailed dictionary of individual rule evaluation results
    notes = db.Column(db.Text, nullable=True)

    evaluated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    application = db.relationship("LoanApplication", back_populates="underwriting")
    evaluator = db.relationship("User", foreign_keys=[evaluator_id])

    def __repr__(self):
        return f"<UnderwritingAssessment App #{self.application_id} Result={self.overall_result} DTI={self.debt_to_income_ratio}%>"
