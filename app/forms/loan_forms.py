from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import (
    StringField,
    DecimalField,
    IntegerField,
    SelectField,
    TextAreaField,
    SubmitField,
)
from wtforms.validators import DataRequired, NumberRange, Length, Optional
from app.models.document import DocumentType


class LoanApplicationForm(FlaskForm):
    product_id = SelectField("Loan Product", coerce=int, validators=[DataRequired()])
    
    requested_amount = DecimalField(
        "Requested Loan Amount (₹)",
        validators=[
            DataRequired(),
            NumberRange(min=500.0, max=50000000.0, message="Amount must be between ₹500 and ₹5,00,00,000."),
        ],
        render_kw={"placeholder": "250000.00", "step": "1000"},
    )
    
    tenure_months = IntegerField(
        "Tenure (Months)",
        validators=[
            DataRequired(),
            NumberRange(min=3, max=360, message="Tenure must be between 3 and 360 months."),
        ],
        render_kw={"placeholder": "36"},
    )
    
    monthly_income = DecimalField(
        "Verified Monthly Income (₹)",
        validators=[
            DataRequired(),
            NumberRange(min=100.0, message="Monthly income must be at least ₹100."),
        ],
        render_kw={"placeholder": "50000.00", "step": "1000"},
    )
    
    existing_monthly_debt = DecimalField(
        "Existing Monthly Debt Obligations (₹)",
        validators=[
            Optional(),
            NumberRange(min=0.0, message="Debt cannot be negative."),
        ],
        default=0.00,
        render_kw={"placeholder": "0.00", "step": "500"},
    )
    
    tax_id = StringField(
        "Tax ID / PAN (Permanent Account Number)",
        validators=[DataRequired(), Length(min=4, max=30)],
        render_kw={"placeholder": "ABCDE1234F"},
    )
    
    employment_type = SelectField(
        "Employment Type",
        choices=[
            ("SALARIED", "Salaried Employee"),
            ("SELF_EMPLOYED", "Self-Employed Professional"),
            ("BUSINESS", "Business Owner / Enterprise"),
            ("OTHER", "Other"),
        ],
        validators=[DataRequired()],
    )
    
    purpose = TextAreaField(
        "Purpose of Loan",
        validators=[Optional(), Length(max=1000)],
        render_kw={"rows": 3, "placeholder": "Describe what you plan to fund with this loan..."},
    )
    
    save_draft = SubmitField("Save as Draft")
    submit = SubmitField("Submit Application for Review")


class DocumentUploadForm(FlaskForm):
    document_type = SelectField(
        "Document Category",
        choices=[
            (DocumentType.IDENTITY_PROOF, "Government Photo ID (Passport / Driver's License)"),
            (DocumentType.INCOME_PROOF, "Proof of Income (Recent Paystubs / Tax Return)"),
            (DocumentType.BANK_STATEMENT, "Bank Statements (Last 3-6 Months)"),
            (DocumentType.ADDRESS_PROOF, "Proof of Residence (Utility Bill / Lease)"),
            (DocumentType.COLLATERAL_PROPERTY, "Collateral / Property Documentation (If applicable)"),
        ],
        validators=[DataRequired()],
    )
    
    document_file = FileField(
        "Select Document File",
        validators=[
            FileRequired(message="Please choose a file to upload."),
            FileAllowed(["pdf", "png", "jpg", "jpeg"], "Only PDF, PNG, and JPG formats are accepted."),
        ],
    )
    
    submit = SubmitField("Upload Securely")


class RepaymentPaymentForm(FlaskForm):
    amount = DecimalField(
        "Payment Amount (₹)",
        validators=[DataRequired(), NumberRange(min=1.0)],
        render_kw={"placeholder": "0.00", "step": "0.01"},
    )
    payment_method = SelectField(
        "Payment Method",
        choices=[
            ("UPI", "UPI (Google Pay / PhonePe / Paytm / BHIM)"),
            ("NET_BANKING", "Net Banking (IMPS / NEFT)"),
            ("DEBIT_CARD", "Debit Card / RuPay"),
            ("NACH_MANDATE", "Auto-Debit NACH e-Mandate"),
        ],
        validators=[DataRequired()],
    )
    submit = SubmitField("Authorize Payment Now")
