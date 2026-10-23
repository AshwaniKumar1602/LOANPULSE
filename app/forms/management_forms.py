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
        "Officer Action & Recommendation",
        choices=[
            ("RECOMMENDED_APPROVAL", "Forward to Manager: Recommend Approval"),
            ("RECOMMENDED_REJECTION", "Forward to Manager: Recommend Rejection"),
            ("PENDING_DOCS", "Request Document Resubmission / Clarification (Notify Borrower)"),
            ("UNDER_REVIEW", "Save Underwriting Review Notes (Keep Under Active Review)"),
        ],
        validators=[DataRequired()],
    )
    notes = TextAreaField(
        "Underwriter Review Notes & Observations",
        validators=[DataRequired(), Length(min=10, max=2000)],
        render_kw={"rows": 4, "placeholder": "Detail your rationale, risk mitigants, and verification results..."},
    )
    submit = SubmitField("Record Officer Assessment & Submit")


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
        validators=[Optional(), NumberRange(min=0.0)],
        render_kw={"step": "100"},
    )
    interest_rate = DecimalField(
        "Final Annual Interest Rate (%)",
        validators=[Optional(), NumberRange(min=0.0, max=100.0)],
        render_kw={"step": "0.10"},
    )
    remarks = TextAreaField(
        "Official Manager Decision Remarks",
        validators=[DataRequired(), Length(min=10, max=1500)],
        render_kw={"rows": 4, "placeholder": "State formal approval or rejection terms and conditions..."},
    )
    submit = SubmitField("Finalize Managerial Decision")

    def validate(self, extra_validators=None):
        initial_validation = super().validate(extra_validators=extra_validators)
        if not initial_validation:
            return False

        if self.decision.data == "APPROVE":
            if not self.approved_amount.data or float(self.approved_amount.data) < 100.0:
                self.approved_amount.errors.append("Approved principal must be at least $100.00.")
                return False
            if not self.interest_rate.data or float(self.interest_rate.data) < 1.0:
                self.interest_rate.errors.append("Final interest rate must be at least 1.0% APR.")
                return False
        return True


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
    code = StringField("Product Code", validators=[DataRequired(), Length(max=50)], render_kw={"placeholder": "e.g. PERSONAL_LOAN"})
    name = StringField("Product Display Name", validators=[DataRequired(), Length(max=100)], render_kw={"placeholder": "e.g. Personal Prime Loan"})
    description = TextAreaField("Description", validators=[Optional()], render_kw={"rows": 3, "placeholder": "Loan product description, target borrower segment, collateral policy..."})
    loan_category = SelectField(
        "Loan Category",
        choices=[
            ("PERSONAL", "Personal Loan (Unsecured, Flexible)"),
            ("VEHICLE", "Car / Vehicle Loan (Secured, Max 7 Yrs)"),
            ("MEDICAL", "Health / Medical Loan (Subsidized, Instant)"),
            ("EDUCATION", "Student Education Loan (Moratorium, Low Rate)"),
            ("BUSINESS", "Commercial SME Growth Loan"),
        ],
        default="PERSONAL",
        validators=[DataRequired()],
    )
    min_amount = DecimalField("Min Loan Amount ($)", validators=[DataRequired(), NumberRange(min=100.0)], render_kw={"step": "100"})
    max_amount = DecimalField("Max Loan Amount ($)", validators=[DataRequired(), NumberRange(min=500.0)], render_kw={"step": "500"})
    min_tenure_months = IntegerField("Min Tenure (Months)", validators=[DataRequired(), NumberRange(min=1)], render_kw={"placeholder": "e.g. 6"})
    max_tenure_months = IntegerField("Max Tenure (Months)", validators=[DataRequired(), NumberRange(min=1)], render_kw={"placeholder": "e.g. 60"})
    base_interest_rate = DecimalField("Base Annual Rate (% APR)", validators=[DataRequired(), NumberRange(min=0.1, max=100.0)], render_kw={"step": "0.05", "placeholder": "e.g. 10.50"})
    min_credit_score = IntegerField("Min Credit Score", validators=[DataRequired(), NumberRange(min=300, max=850)], default=650)
    max_dti_ratio = DecimalField("Max Allowable DTI (%)", validators=[DataRequired(), NumberRange(min=10.0, max=100.0)], default=50.00, render_kw={"step": "1.0"})
    min_income_required = DecimalField("Min Monthly Income ($)", validators=[DataRequired(), NumberRange(min=0.0)], default=2000.00, render_kw={"step": "100"})
    moratorium_months = IntegerField("Moratorium Period (Months)", validators=[Optional(), NumberRange(min=0, max=36)], default=0)
    processing_speed = SelectField(
        "Processing Speed SLA",
        choices=[
            ("STANDARD", "Standard Processing (24-48 Hours)"),
            ("EXPRESS", "Express Priority (Same Day)"),
            ("INSTANT", "Instant Automated Processing"),
        ],
        default="STANDARD",
    )
    secured = BooleanField("Secured Collateral Required", default=False)
    is_active = BooleanField("Active Product (Open for Origination)", default=True)
    submit = SubmitField("Save Loan Product Configuration")

    def validate(self, extra_validators=None):
        initial_validation = super().validate(extra_validators=extra_validators)
        if not initial_validation:
            return False

        if self.min_amount.data and self.max_amount.data and self.max_amount.data < self.min_amount.data:
            self.max_amount.errors.append("Maximum loan amount must be greater than or equal to minimum amount.")
            return False

        if self.min_tenure_months.data and self.max_tenure_months.data and self.max_tenure_months.data < self.min_tenure_months.data:
            self.max_tenure_months.errors.append("Maximum tenure must be greater than or equal to minimum tenure.")
            return False

        return True
