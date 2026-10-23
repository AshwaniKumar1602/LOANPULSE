from flask_wtf import FlaskForm
from wtforms import (
    StringField,
    DecimalField,
    IntegerField,
    SelectField,
    TextAreaField,
    BooleanField,
    SubmitField,
)
from wtforms.validators import DataRequired, NumberRange, Length, Optional
from app.models.document import DocumentStatus


class OfficerRecommendationForm(FlaskForm):
    recommendation = SelectField(
        "Officer Recommendation",
        choices=[
            ("RECOMMENDED_APPROVAL", "Recommend for Approval"),
            ("RECOMMENDED_REJECTION", "Recommend for Rejection"),
            ("PENDING_DOCS", "Request More Documents / Applicant Clarification"),
        ],
        validators=[DataRequired()],
    )
    notes = TextAreaField(
        "Underwriter Review Notes & Observations",
        validators=[DataRequired(), Length(min=10, max=2000)],
        render_kw={"rows": 4, "placeholder": "Detail your rationale, risk mitigants, and verification results..."},
    )
    submit = SubmitField("Submit Recommendation to Manager")


class DocumentVerificationForm(FlaskForm):
    verification_status = SelectField(
        "Verification Status",
        choices=[
            (DocumentStatus.VERIFIED, "Mark Verified & Accepted"),
            (DocumentStatus.REJECTED, "Reject Document (Requires Re-upload)"),
        ],
        validators=[DataRequired()],
    )
    verification_notes = TextAreaField(
        "Verification Comments",
        validators=[Optional(), Length(max=500)],
        render_kw={"rows": 2, "placeholder": "Legibility, address match, validity date notes..."},
    )
    submit = SubmitField("Save Verification Status")


class ManagerDecisionForm(FlaskForm):
    decision = SelectField(
        "Manager Decision",
        choices=[
            ("APPROVE", "Approve Loan Application"),
            ("REJECT", "Reject Loan Application"),
        ],
        validators=[DataRequired()],
    )
    approved_amount = DecimalField(
        "Approved Principal ($)",
        validators=[DataRequired(), NumberRange(min=100.0)],
        render_kw={"step": "100"},
    )
    interest_rate = DecimalField(
        "Final Annual Interest Rate (%)",
        validators=[DataRequired(), NumberRange(min=1.0, max=100.0)],
        render_kw={"step": "0.10"},
    )
    remarks = TextAreaField(
        "Official Manager Decision Remarks",
        validators=[DataRequired(), Length(min=10, max=1500)],
        render_kw={"rows": 4, "placeholder": "State formal approval or rejection terms and conditions..."},
    )
    submit = SubmitField("Finalize Managerial Decision")


class DisbursementForm(FlaskForm):
    bank_name = StringField(
        "Beneficiary Bank Name",
        validators=[DataRequired(), Length(max=100)],
        render_kw={"placeholder": "Chase / Bank of America / Wells Fargo"},
    )
    bank_account = StringField(
        "Beneficiary Account Number",
        validators=[DataRequired(), Length(min=6, max=30)],
        render_kw={"placeholder": "1234567890"},
    )
    bank_routing = StringField(
        "Routing Number / IFSC Code",
        validators=[DataRequired(), Length(min=4, max=20)],
        render_kw={"placeholder": "021000021"},
    )
    disbursement_method = SelectField(
        "Disbursement Channel",
        choices=[
            ("DIRECT_DEPOSIT", "Direct ACH Deposit"),
            ("BANK_TRANSFER", "Domestic Wire / Transfer"),
            ("NEFT_RTGS", "NEFT / RTGS"),
            ("CHEQUE", "Cashier Check"),
        ],
        validators=[DataRequired()],
    )
    notes = TextAreaField(
        "Disbursement Notes",
        validators=[Optional(), Length(max=500)],
        render_kw={"rows": 2, "placeholder": "Authorization code or reference notes..."},
    )
    submit = SubmitField("Disburse Funds & Generate EMI Schedule")


class LoanProductForm(FlaskForm):
    code = StringField("Product Code", validators=[DataRequired(), Length(max=50)])
    name = StringField("Product Display Name", validators=[DataRequired(), Length(max=100)])
    description = TextAreaField("Description", validators=[Optional()])
    min_amount = DecimalField("Min Amount ($)", validators=[DataRequired(), NumberRange(min=100.0)])
    max_amount = DecimalField("Max Amount ($)", validators=[DataRequired(), NumberRange(min=500.0)])
    min_tenure_months = IntegerField("Min Tenure (Months)", validators=[DataRequired(), NumberRange(min=1)])
    max_tenure_months = IntegerField("Max Tenure (Months)", validators=[DataRequired(), NumberRange(min=1)])
    base_interest_rate = DecimalField("Base Annual Rate (%)", validators=[DataRequired(), NumberRange(min=0.1, max=100.0)])
    min_credit_score = IntegerField("Min Credit Score", validators=[DataRequired(), NumberRange(min=300, max=850)])
    max_dti_ratio = DecimalField("Max DTI (%)", validators=[DataRequired(), NumberRange(min=10.0, max=100.0)])
    is_active = BooleanField("Active Product", default=True)
    submit = SubmitField("Save Product")
