from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, current_user, login_required
from app.extensions import db, limiter
from app.models.user import User, UserRole
from app.models.customer import CustomerProfile
from app.forms.auth_forms import LoginForm, RegisterForm, MfaVerifyForm
from app.utils.security import (
    generate_totp_secret,
    generate_totp_qr_data_uri,
    verify_totp_token,
    sanitize_input,
)

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = RegisterForm()
    if form.validate_on_submit():
        email = sanitize_input(form.email.data.strip().lower())

        # Check if email already registered
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash("An account with this email address already exists. Please sign in.", "warning")
            return redirect(url_for("auth.login"))

        user = User(
            email=email,
            first_name=sanitize_input(form.first_name.data.strip()),
            last_name=sanitize_input(form.last_name.data.strip()),
            phone=sanitize_input(form.phone.data.strip()),
            role=UserRole.CUSTOMER,
            is_active=True,
        )
        user.set_password(form.password.data)

        db.session.add(user)
        db.session.flush()

        # Initialize blank customer profile
        profile = CustomerProfile(user_id=user.id)
        db.session.add(profile)
        db.session.commit()

        flash("Account created successfully! Please sign in with your credentials.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html", form=form)


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    if current_user.is_authenticated:
        return _redirect_by_role(current_user)

    form = LoginForm()
    if form.validate_on_submit():
        email = sanitize_input(form.email.data.strip().lower())
        user = User.query.filter_by(email=email).first()

        if not user or not user.check_password(form.password.data):
            flash("Invalid email or password. Please verify your credentials.", "danger")
            return render_template("auth/login.html", form=form)

        if not user.is_active:
            flash("This account has been deactivated. Please contact support.", "danger")
            return render_template("auth/login.html", form=form)

        # Clear session to prevent session fixation attacks
        session.clear()
        login_user(user, remember=form.remember_me.data)

        # Staff MFA Check (Security Rule #10)
        if user.role in (UserRole.LOAN_OFFICER, UserRole.LOAN_MANAGER, UserRole.ADMIN):
            if not user.totp_enabled:
                flash("Security requirement: Please configure Two-Factor Authentication (2FA) for your staff account.", "info")
                return redirect(url_for("auth.mfa_setup"))
            else:
                session["mfa_verified"] = False
                return redirect(url_for("auth.mfa_verify"))

        flash(f"Welcome back, {user.first_name}!", "success")
        next_page = request.args.get("next")
        if next_page and next_page.startswith("/"):
            return redirect(next_page)
        return _redirect_by_role(user)

    return render_template("auth/login.html", form=form)


@auth_bp.route("/mfa/setup", methods=["GET", "POST"])
@login_required
def mfa_setup():
    """Sets up TOTP MFA for a user."""
    # If user doesn't have a temporary secret, generate one in session
    if "pending_totp_secret" not in session:
        session["pending_totp_secret"] = generate_totp_secret()

    totp_secret = session["pending_totp_secret"]
    qr_data_uri = generate_totp_qr_data_uri(totp_secret, current_user.email)

    form = MfaVerifyForm()
    if form.validate_on_submit():
        token = form.totp_token.data
        if verify_totp_token(totp_secret, token):
            current_user.totp_secret = totp_secret
            current_user.totp_enabled = True
            db.session.commit()

            session.pop("pending_totp_secret", None)
            session["mfa_verified"] = True
            flash("Two-Factor Authentication (2FA) successfully enabled!", "success")
            return _redirect_by_role(current_user)
        else:
            flash("Invalid authentication code. Please check your authenticator app and try again.", "danger")

    return render_template("auth/mfa_setup.html", form=form, qr_data_uri=qr_data_uri, secret=totp_secret)


@auth_bp.route("/mfa/verify", methods=["GET", "POST"])
@login_required
@limiter.limit("10 per minute")
def mfa_verify():
    """Verifies TOTP MFA token on login."""
    if not current_user.totp_enabled:
        return redirect(url_for("auth.mfa_setup"))

    if session.get("mfa_verified"):
        return _redirect_by_role(current_user)

    form = MfaVerifyForm()
    if form.validate_on_submit():
        token = form.totp_token.data
        if verify_totp_token(current_user.totp_secret, token):
            session["mfa_verified"] = True
            flash("2FA Verification confirmed. Welcome to LoanPulse!", "success")
            next_page = request.args.get("next")
            if next_page and next_page.startswith("/"):
                return redirect(next_page)
            return _redirect_by_role(current_user)
        else:
            flash("Invalid authentication code. Please try again.", "danger")

    return render_template("auth/mfa_verify.html", form=form)


@auth_bp.route("/logout")
def logout():
    session.clear()
    logout_user()
    flash("You have been signed out safely.", "info")
    return redirect(url_for("auth.login"))


def _redirect_by_role(user: User):
    if user.role == UserRole.CUSTOMER:
        return redirect(url_for("customer.dashboard"))
    elif user.role == UserRole.LOAN_OFFICER:
        return redirect(url_for("officer.dashboard"))
    elif user.role in (UserRole.LOAN_MANAGER, UserRole.ADMIN):
        return redirect(url_for("manager.dashboard"))
    return redirect(url_for("main.index"))
