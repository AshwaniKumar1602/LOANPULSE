import uuid
from datetime import datetime, timezone
from flask_login import UserMixin
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from app.extensions import db

ph = PasswordHasher()


class UserRole:
    CUSTOMER = "CUSTOMER"
    LOAN_OFFICER = "LOAN_OFFICER"
    LOAN_MANAGER = "LOAN_MANAGER"
    ADMIN = "ADMIN"

    ALL_ROLES = [CUSTOMER, LOAN_OFFICER, LOAN_MANAGER, ADMIN]


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(30), nullable=True)
    role = db.Column(db.String(30), nullable=False, default=UserRole.CUSTOMER, index=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    # TOTP MFA Support (Security Rule #10)
    totp_secret = db.Column(db.String(64), nullable=True)
    totp_enabled = db.Column(db.Boolean, default=False, nullable=False)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    customer_profile = db.relationship("CustomerProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    applications = db.relationship("LoanApplication", back_populates="customer", foreign_keys="LoanApplication.customer_id", lazy="dynamic")
    notifications = db.relationship("Notification", back_populates="user", cascade="all, delete-orphan", lazy="dynamic", order_by="desc(Notification.created_at)")

    def set_password(self, password: str):
        """Hashes password using secure Argon2id algorithm (Security Rule #9)."""
        if not password or len(password) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        self.password_hash = ph.hash(password)

    def check_password(self, password: str) -> bool:
        """Verifies password using Argon2id."""
        if not self.password_hash or not password:
            return False
        try:
            return ph.verify(self.password_hash, password)
        except VerifyMismatchError:
            return False
        except Exception:
            return False

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def has_role(self, *roles: str) -> bool:
        return self.role in roles

    @property
    def is_customer(self) -> bool:
        return self.role == UserRole.CUSTOMER

    @property
    def is_officer(self) -> bool:
        return self.role == UserRole.LOAN_OFFICER

    @property
    def is_manager(self) -> bool:
        return self.role in (UserRole.LOAN_MANAGER, UserRole.ADMIN)

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"
