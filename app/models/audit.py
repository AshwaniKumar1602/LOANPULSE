from datetime import datetime, timezone
from app.extensions import db


class AuditAction:
    APPLICATION_CREATED = "APPLICATION_CREATED"
    DRAFT_SAVED = "DRAFT_SAVED"
    APPLICATION_SUBMITTED = "APPLICATION_SUBMITTED"
    APPLICATION_RESUBMITTED = "APPLICATION_RESUBMITTED"
    DOCUMENT_UPLOADED = "DOCUMENT_UPLOADED"
    DOCUMENT_VERIFIED = "DOCUMENT_VERIFIED"
    DOCUMENT_REJECTED = "DOCUMENT_REJECTED"
    UNDERWRITING_EVALUATED = "UNDERWRITING_EVALUATED"
    OFFICER_RECOMMENDATION = "OFFICER_RECOMMENDATION"
    MANAGER_APPROVED = "MANAGER_APPROVED"
    MANAGER_REJECTED = "MANAGER_REJECTED"
    DISBURSEMENT_INITIATED = "DISBURSEMENT_INITIATED"
    DISBURSEMENT_COMPLETED = "DISBURSEMENT_COMPLETED"
    REPAYMENT_RECORDED = "REPAYMENT_RECORDED"
    APPLICATION_CLOSED = "APPLICATION_CLOSED"


class DecisionAuditLog(db.Model):
    __tablename__ = "decision_audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("loan_applications.id", ondelete="CASCADE"), nullable=True, index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    
    action = db.Column(db.String(60), nullable=False, index=True)
    previous_status = db.Column(db.String(40), nullable=True)
    new_status = db.Column(db.String(40), nullable=True)
    
    notes = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)  # Supports IPv4 and IPv6

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    # Relationships
    application = db.relationship("LoanApplication", back_populates="audit_logs")
    actor = db.relationship("User", foreign_keys=[actor_id])

    def __repr__(self):
        return f"<DecisionAuditLog App #{self.application_id} Action={self.action} Actor={self.actor_id}>"
