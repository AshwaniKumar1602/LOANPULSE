from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SelectField, SubmitField
from wtforms.validators import DataRequired, Email, Length, EqualTo, Regexp
from app.models.user import UserRole


class LoginForm(FlaskForm):
    role = SelectField(
        "Sign In As",
        choices=[
            (UserRole.CUSTOMER, "Loan Borrower"),
            (UserRole.LOAN_OFFICER, "Loan Officer"),
            (UserRole.LOAN_MANAGER, "Loan Manager"),
        ],
        default=UserRole.CUSTOMER,
        validators=[DataRequired()],
    )
    email = StringField(
        "Email Address",
        validators=[DataRequired(), Email(), Length(max=255)],
        render_kw={"placeholder": "you@example.com", "autocomplete": "email"},
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired()],
        render_kw={"placeholder": "••••••••", "autocomplete": "current-password"},
    )
    remember_me = BooleanField("Keep me logged in for 30 days")
    submit = SubmitField("Sign In to Portal")


class RegisterForm(FlaskForm):
    first_name = StringField(
        "First Name",
        validators=[DataRequired(), Length(min=2, max=100)],
        render_kw={"placeholder": "Jane"},
    )
    last_name = StringField(
        "Last Name",
        validators=[DataRequired(), Length(min=2, max=100)],
        render_kw={"placeholder": "Doe"},
    )
    email = StringField(
        "Email Address",
        validators=[DataRequired(), Email(), Length(max=255)],
        render_kw={"placeholder": "jane.doe@example.com", "autocomplete": "email"},
    )
    phone = StringField(
        "Mobile Phone Number",
        validators=[
            DataRequired(),
            Length(min=10, max=20),
            Regexp(r"^\+?[0-9\s\-]+$", message="Please enter a valid phone number."),
        ],
        render_kw={"placeholder": "+1 (555) 000-0000"},
    )
    password = PasswordField(
        "Password",
        validators=[
            DataRequired(),
            Length(min=8, message="Password must be at least 8 characters long."),
        ],
        render_kw={"placeholder": "At least 8 characters", "autocomplete": "new-password"},
    )
    confirm_password = PasswordField(
        "Confirm Password",
        validators=[
            DataRequired(),
            EqualTo("password", message="Passwords must match exactly."),
        ],
        render_kw={"placeholder": "Re-enter password", "autocomplete": "new-password"},
    )
    submit = SubmitField("Create Free Account")


class MfaVerifyForm(FlaskForm):
    totp_token = StringField(
        "6-Digit Authentication Code",
        validators=[
            DataRequired(),
            Length(min=6, max=6, message="Please enter a 6-digit code."),
            Regexp(r"^[0-9]{6}$", message="Code must consist of 6 numeric digits."),
        ],
        render_kw={"placeholder": "123456", "autocomplete": "one-time-code", "maxlength": "6"},
    )
    submit = SubmitField("Verify & Continue")
