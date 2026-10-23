import uuid
from datetime import datetime, timezone
from app.extensions import db


class DocumentType:
    IDENTITY_PROOF = "IDENTITY_PROOF"
    INCOME_PROOF = "INCOME_PROOF"
    ADDRESS_PROOF = "ADDRESS_PROOF"
    BANK_STATEMENT = "BANK_STATEMENT"
    COLLATERAL_PROPERTY = "COLLATERAL_PROPERTY"

    ALL_TYPES = [
        IDENTITY_PROOF,
        INCOME_PROOF,
        ADDRESS_PROOF,
        BANK_STATEMENT,
        COLLATERAL_PROPERTY,
    ]


class DocumentStatus:
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class ApplicationDocument(db.Model):
    __tablename__ = "application_documents"

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("loan_applications.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    document_type = db.Column(db.String(50), nullable=False)
    file_uuid = db.Column(db.String(64), unique=True, nullable=False, default=lambda: str(uuid.uuid4()), index=True)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)
    mime_type = db.Column(db.String(100), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)  # in bytes

    verification_status = db.Column(db.String(30), nullable=False, default=DocumentStatus.PENDING, index=True)
    verification_notes = db.Column(db.Text, nullable=True)
    verified_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    verified_at = db.Column(db.DateTime, nullable=True)

    uploaded_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    application = db.relationship("LoanApplication", back_populates="documents")
    uploader = db.relationship("User", foreign_keys=[user_id])
    verifier = db.relationship("User", foreign_keys=[verified_by_id])

    def __repr__(self):
        return f"<ApplicationDocument {self.document_type} ({self.verification_status}) - App #{self.application_id}>"
