from functools import wraps
from flask import abort, flash, redirect, request, session, url_for
from flask_login import current_user
from app.models.user import UserRole


def role_required(*allowed_roles: str):
    """
    Enforces server-side role authorization (Security Rule #13).
    Prevents unauthorized access even if UI elements are tampered with.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash("Please log in to continue.", "warning")
                return redirect(url_for("auth.login", next=request.url))

            if not current_user.is_active:
                flash("Your account has been deactivated. Please contact support.", "danger")
                return redirect(url_for("auth.logout"))

            if current_user.role not in allowed_roles:
                abort(403)

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def mfa_enforced_for_staff(f):
    """
    Ensures Loan Officers & Managers configure and verify TOTP MFA (Security Rule #10).
    Redirects staff to MFA verification or setup if pending.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login", next=request.url))

        # Check if user is staff (Officer, Manager, Admin)
        if current_user.role in (UserRole.LOAN_OFFICER, UserRole.LOAN_MANAGER, UserRole.ADMIN):
            # If MFA not configured yet, force initial setup
            if not current_user.totp_enabled:
                flash("Multi-Factor Authentication (MFA) is required for staff accounts. Please configure your authenticator app.", "info")
                return redirect(url_for("auth.mfa_setup"))

            # If MFA is configured, verify current session has passed MFA check
            if not session.get("mfa_verified"):
                flash("Please verify your 2FA authentication code to continue.", "warning")
                return redirect(url_for("auth.mfa_verify", next=request.url))

        return f(*args, **kwargs)

    return decorated_function
