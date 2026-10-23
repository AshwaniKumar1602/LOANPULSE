from datetime import datetime, timezone
from app.extensions import db


class NotificationType:
    APPLICATION_STATUS = "APPLICATION_STATUS"
    DOCUMENT_REQUEST = "DOCUMENT_REQUEST"
    DISBURSEMENT = "DISBURSEMENT"
    EMI_DUE = "EMI_DUE"
    SECURITY_ALERT = "SECURITY_ALERT"


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    type = db.Column(db.String(50), nullable=False, default=NotificationType.APPLICATION_STATUS)
    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)
    link = db.Column(db.String(255), nullable=True)
    is_read = db.Column(db.Boolean, default=False, nullable=False, index=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    # Relationships
    user = db.relationship("User", back_populates="notifications")

    def __repr__(self):
        return f"<Notification UserID={self.user_id} Title='{self.title}' Read={self.is_read}>"
