from datetime import date
from decimal import Decimal
import io
import pyotp
import pytest
from app.extensions import db
from app.models.user import User, UserRole
from app.models.customer import CustomerProfile
from app.models.loan_product import LoanProduct
from app.models.loan_application import LoanApplication, ApplicationStatus
from app.models.document import ApplicationDocument, DocumentStatus, DocumentType
from app.models.disbursement import Disbursement, DisbursementStatus
from app.models.repayment import RepaymentSchedule, RepaymentStatus
from app.models.audit import DecisionAuditLog, AuditAction
from app.models.notification import Notification, NotificationType
from app.utils.formatters import inr_currency, parse_inr


def create_customer(email="inr.borrower@example.com", password="SecurePassword123!"):
    user = User(
        email=email,
        first_name="Rohan",
        last_name="Sharma",
        role=UserRole.CUSTOMER,
        is_active=True,
    )
    user.set_password(password)
    profile = CustomerProfile(
        credit_score=750,
        annual_income=1200000.0,  # ₹12 Lakhs/year = ₹1,00,000/mo
        monthly_debt=15000.0,
        employment_type="SALARIED",
        tax_id_masked="ABCDE1234F",
    )
    user.customer_profile = profile
    db.session.add(user)
    db.session.commit()
    return user


def create_officer(email="inr.officer@example.com", password="SecurePassword123!"):
    totp_secret = "JBSWY3DPEHPK3PXP"
    user = User(
        email=email,
        first_name="Pooja",
        last_name="Patel",
        role=UserRole.LOAN_OFFICER,
        is_active=True,
        totp_enabled=True,
        totp_secret=totp_secret,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user, totp_secret


def create_manager(email="inr.manager@example.com", password="SecurePassword123!"):
    totp_secret = "JBSWY3DPEHPK3PXP"
    user = User(
        email=email,
        first_name="Vikram",
        last_name="Mehta",
        role=UserRole.LOAN_MANAGER,
        is_active=True,
        totp_enabled=True,
        totp_secret=totp_secret,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user, totp_secret


def login_user_mfa(client, email, password, role, totp_secret):
    client.post(
        "/auth/login",
        data={"email": email, "password": password, "role": role},
        follow_redirects=True,
    )
    token = pyotp.TOTP(totp_secret).now()
    client.post("/auth/mfa/verify", data={"totp_token": token}, follow_redirects=True)


# ------------------------------------------------------------------------------
# 1. INR Currency Formatting & Filter Tests
# ------------------------------------------------------------------------------

def test_inr_currency_formatting_filter():
    """Verifies that inr_currency correctly groups digits according to the Indian numbering system."""
    # Under 1,000
    assert inr_currency(0) == "₹0.00"
    assert inr_currency(100) == "₹100.00"
    assert inr_currency(999.5) == "₹999.50"

    # Thousands
    assert inr_currency(1000) == "₹1,000.00"
    assert inr_currency(25000) == "₹25,000.00"
    assert inr_currency(99999) == "₹99,999.00"

    # Lakhs (1,00,000+)
    assert inr_currency(100000) == "₹1,00,000.00"
    assert inr_currency(1050000.50) == "₹10,50,000.50"
    assert inr_currency(5000000) == "₹50,00,000.00"

    # Crores (1,00,00,000+)
    assert inr_currency(12345678.90) == "₹1,23,45,678.90"
    assert inr_currency(100000000) == "₹10,00,00,000.00"

    # Negative amounts
    assert inr_currency(-50000) == "-₹50,000.00"

    # Edge cases
    assert inr_currency(None) == "₹0.00"
    assert inr_currency("") == "₹0.00"
    assert inr_currency("invalid") == "₹0.00"

    # Without currency symbol
    assert inr_currency(100000, show_symbol=False) == "1,00,000.00"

    # Parse INR helper
    assert parse_inr("₹1,25,000.50") == Decimal("125000.50")
    assert parse_inr("50000") == Decimal("50000.00")


def test_jinja_inr_currency_template_rendering(app):
    """Verifies Jinja template filter registration and rendering in templates."""
    with app.test_request_context():
        from flask import render_template_string
        rendered = render_template_string(
            "Principal: {{ amount | inr_currency }} | Without symbol: {{ amount | inr(show_symbol=False) }}",
            amount=250000.00,
        )
        assert "Principal: ₹2,50,000.00" in rendered
        assert "Without symbol: 2,50,000.00" in rendered


# ------------------------------------------------------------------------------
# 2. Lifecycle State Machine Deterministic Transition Tests
# ------------------------------------------------------------------------------

def test_application_state_machine_valid_and_invalid_transitions():
    """Verifies that LoanApplication.transition_to enforces valid state machine transitions."""
    app_loan = LoanApplication(status=ApplicationStatus.DRAFT)

    # DRAFT -> SUBMITTED is valid
    assert app_loan.can_transition_to(ApplicationStatus.SUBMITTED) is True
    assert app_loan.transition_to(ApplicationStatus.SUBMITTED) is True
    assert app_loan.status == ApplicationStatus.SUBMITTED

    # SUBMITTED -> DISBURSED is invalid (cannot skip review & approval)
    assert app_loan.can_transition_to(ApplicationStatus.DISBURSED) is False
    with pytest.raises(ValueError) as excinfo:
        app_loan.transition_to(ApplicationStatus.DISBURSED)
    assert "Invalid lifecycle transition" in str(excinfo.value)

    # SUBMITTED -> UNDER_REVIEW is valid
    assert app_loan.transition_to(ApplicationStatus.UNDER_REVIEW) is True

    # UNDER_REVIEW -> PENDING_DOCS is valid
    assert app_loan.transition_to(ApplicationStatus.PENDING_DOCS) is True

    # PENDING_DOCS -> UNDER_REVIEW is valid (resubmission)
    assert app_loan.transition_to(ApplicationStatus.UNDER_REVIEW) is True

    # UNDER_REVIEW -> RECOMMENDED_APPROVAL is valid
    assert app_loan.transition_to(ApplicationStatus.RECOMMENDED_APPROVAL) is True

    # RECOMMENDED_APPROVAL -> APPROVED is valid
    assert app_loan.transition_to(ApplicationStatus.APPROVED) is True

    # APPROVED -> DISBURSED is valid
    assert app_loan.transition_to(ApplicationStatus.DISBURSED) is True

    # DISBURSED -> COMPLETED is valid
    assert app_loan.transition_to(ApplicationStatus.COMPLETED) is True

    # COMPLETED is terminal: cannot transition back to DRAFT or UNDER_REVIEW
    assert app_loan.can_transition_to(ApplicationStatus.DRAFT) is False
    with pytest.raises(ValueError):
        app_loan.transition_to(ApplicationStatus.DRAFT)


# ------------------------------------------------------------------------------
# 3. Draft Application Lifecycle (Create Draft, Edit, Final Submit)
# ------------------------------------------------------------------------------

def test_customer_draft_creation_edit_and_submission(client, app):
    """Verifies borrower can save draft applications, edit them, and submit for underwriting."""
    with app.app_context():
        cust = create_customer("draft.user@example.com")
        cust_id = cust.id
        product = LoanProduct.query.filter_by(code="PERSONAL_PRIME").first()
        prod_id = product.id

    client.post(
        "/auth/login",
        data={"email": "draft.user@example.com", "password": "SecurePassword123!", "role": UserRole.CUSTOMER},
        follow_redirects=True,
    )

    # 1. Save as Draft
    draft_res = client.post(
        "/customer/loans/apply",
        data={
            "action": "draft",
            "product_id": prod_id,
            "requested_amount": "250000",
            "tenure_months": "36",
            "purpose": "Preliminary home interior planning",
            "employment_type": "SALARIED",
            "monthly_income": "80000",
            "existing_monthly_debt": "10000",
            "tax_id": "ABCDE1234F",
        },
        follow_redirects=True,
    )
    assert draft_res.status_code == 200
    assert b"saved as draft" in draft_res.data

    with app.app_context():
        loan = LoanApplication.query.filter_by(customer_id=cust_id).first()
        assert loan is not None
        assert loan.status == ApplicationStatus.DRAFT
        assert loan.submitted_at is None
        assert loan.underwriting is None  # Underwriting not run on draft
        loan_id = loan.id

        # Check Draft Audit Log
        draft_audit = DecisionAuditLog.query.filter_by(application_id=loan_id, action=AuditAction.DRAFT_SAVED).first()
        assert draft_audit is not None
        assert "₹2,50,000.00" in draft_audit.notes

    # 2. Edit Draft via /customer/loans/<id>/edit
    edit_page = client.get(f"/customer/loans/{loan_id}/edit")
    assert edit_page.status_code == 200
    assert b"Edit Draft Application" in edit_page.data

    edit_res = client.post(
        f"/customer/loans/{loan_id}/edit",
        data={
            "action": "draft",
            "product_id": prod_id,
            "requested_amount": "300000",  # Increased amount
            "tenure_months": "48",         # Increased tenure
            "purpose": "Updated renovation plan with modular kitchen",
            "employment_type": "SALARIED",
            "monthly_income": "85000",
            "existing_monthly_debt": "10000",
            "tax_id": "ABCDE1234F",
        },
        follow_redirects=True,
    )
    assert edit_res.status_code == 200
    assert b"Draft application updated successfully" in edit_res.data

    with app.app_context():
        l_updated = db.session.get(LoanApplication, loan_id)
        assert l_updated.status == ApplicationStatus.DRAFT
        assert float(l_updated.requested_amount) == 300000.00
        assert l_updated.tenure_months == 48

    # 3. Final Submit from Edit Screen
    submit_res = client.post(
        f"/customer/loans/{loan_id}/edit",
        data={
            "action": "submit",
            "product_id": prod_id,
            "requested_amount": "300000",
            "tenure_months": "48",
            "purpose": "Final submitted renovation loan request",
            "employment_type": "SALARIED",
            "monthly_income": "85000",
            "existing_monthly_debt": "10000",
            "tax_id": "ABCDE1234F",
        },
        follow_redirects=True,
    )
    assert submit_res.status_code == 200
    assert b"submitted" in submit_res.data

    with app.app_context():
        l_submitted = db.session.get(LoanApplication, loan_id)
        assert l_submitted.status == ApplicationStatus.SUBMITTED
        assert l_submitted.submitted_at is not None
        assert l_submitted.underwriting is not None  # Auto underwriting executed

    # 4. Attempting to edit an already submitted application is blocked
    block_edit = client.get(f"/customer/loans/{loan_id}/edit", follow_redirects=True)
    assert b"Only draft applications can be edited" in block_edit.data


# ------------------------------------------------------------------------------
# 4. Document Resubmission Workflow (PENDING_DOCS -> UNDER_REVIEW)
# ------------------------------------------------------------------------------

def test_document_resubmission_lifecycle(client, app):
    """Verifies loan officer requests resubmission, customer re-uploads and resubmits."""
    with app.app_context():
        cust = create_customer("resubmit.borrower@example.com")
        cust_id = cust.id
        off, off_secret = create_officer("resubmit.officer@example.com")
        product = LoanProduct.query.filter_by(code="PERSONAL_PRIME").first()

        loan = LoanApplication(
            customer_id=cust_id,
            product_id=product.id,
            requested_amount=200000.0,
            tenure_months=24,
            interest_rate=10.0,
            status=ApplicationStatus.UNDER_REVIEW,
        )
        db.session.add(loan)
        db.session.commit()
        loan_id = loan.id

    # 1. Officer requests document resubmission
    login_user_mfa(client, "resubmit.officer@example.com", "SecurePassword123!", UserRole.LOAN_OFFICER, off_secret)
    res_officer = client.post(
        f"/officer/loans/{loan_id}/recommend",
        data={
            "recommendation": ApplicationStatus.PENDING_DOCS,
            "notes": "Salary slip from employer is illegible. Please re-upload verified PDF.",
        },
        follow_redirects=True,
    )
    assert res_officer.status_code == 200

    with app.app_context():
        l = db.session.get(LoanApplication, loan_id)
        assert l.status == ApplicationStatus.PENDING_DOCS

    client.post("/auth/logout", follow_redirects=True)

    # 2. Customer views application details and sees PENDING_DOCS action alert
    client.post(
        "/auth/login",
        data={"email": "resubmit.borrower@example.com", "password": "SecurePassword123!", "role": UserRole.CUSTOMER},
        follow_redirects=True,
    )
    cust_view = client.get(f"/customer/loans/{loan_id}")
    assert cust_view.status_code == 200
    assert b"Action Required: Document Resubmission Requested" in cust_view.data

    # 3. Customer uploads replacement document
    pdf_bytes = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    upload_res = client.post(
        f"/customer/loans/{loan_id}/documents/upload",
        data={
            "document_type": DocumentType.INCOME_PROOF,
            "document_file": (io.BytesIO(pdf_bytes), "latest_salary_slip.pdf"),
        },
        follow_redirects=True,
    )
    assert upload_res.status_code == 200

    # 4. Customer clicks resubmit
    resubmit_res = client.post(f"/customer/loans/{loan_id}/resubmit", follow_redirects=True)
    assert resubmit_res.status_code == 200
    assert b"successfully resubmitted" in resubmit_res.data

    with app.app_context():
        l_resubmitted = db.session.get(LoanApplication, loan_id)
        assert l_resubmitted.status == ApplicationStatus.UNDER_REVIEW

        # Verify audit log recorded
        audit = DecisionAuditLog.query.filter_by(application_id=loan_id, action=AuditAction.APPLICATION_RESUBMITTED).first()
        assert audit is not None
        assert audit.previous_status == ApplicationStatus.PENDING_DOCS
        assert audit.new_status == ApplicationStatus.UNDER_REVIEW


# ------------------------------------------------------------------------------
# 5. Full End-to-End Disbursement and Repayment Workflow in INR
# ------------------------------------------------------------------------------

def test_full_lifecycle_disbursement_and_repayment_inr(client, app):
    """
    End-to-end verification:
    Customer application -> Manager approval -> Disbursement with IFSC in INR ->
    Schedule generation -> Installment repayment -> Full settlement.
    """
    with app.app_context():
        cust = create_customer("lifecycle.borrower@example.com")
        cust_id = cust.id
        mgr, mgr_secret = create_manager("lifecycle.manager@example.com")
        product = LoanProduct.query.filter_by(code="PERSONAL_PRIME").first()

        loan = LoanApplication(
            customer_id=cust_id,
            product_id=product.id,
            requested_amount=100000.0,
            tenure_months=2,
            interest_rate=12.0,
            status=ApplicationStatus.RECOMMENDED_APPROVAL,
        )
        db.session.add(loan)
        db.session.commit()
        loan_id = loan.id

    # 1. Manager Approves Application
    login_user_mfa(client, "lifecycle.manager@example.com", "SecurePassword123!", UserRole.LOAN_MANAGER, mgr_secret)
    appr_res = client.post(
        f"/manager/loans/{loan_id}/decision",
        data={
            "decision": "APPROVE",
            "approved_amount": "100000.00",
            "interest_rate": "12.00",
            "remarks": "Approved with standard prime INR terms.",
        },
        follow_redirects=True,
    )
    assert appr_res.status_code == 200

    with app.app_context():
        l = db.session.get(LoanApplication, loan_id)
        assert l.status == ApplicationStatus.APPROVED

    # 2. Manager Authorizes Disbursement
    disb_res = client.post(
        f"/manager/loans/{loan_id}/disburse",
        data={
            "bank_name": "State Bank of India",
            "bank_account": "987654321012",
            "bank_routing": "SBIN0001234",
            "disbursement_method": "NEFT_RTGS",
            "notes": "Electronic transfer via RBI NEFT gateway.",
        },
        follow_redirects=True,
    )
    assert disb_res.status_code == 200
    assert b"successfully disbursed" in disb_res.data

    with app.app_context():
        l = db.session.get(LoanApplication, loan_id)
        assert l.status == ApplicationStatus.DISBURSED
        assert l.disbursement is not None
        assert l.disbursement.bank_name == "State Bank of India"
        assert l.disbursement.bank_routing_or_ifsc == "SBIN0001234"
        assert l.disbursement.bank_account_masked == "********1012"

        # Verify schedules generated
        schedules = l.repayment_schedules.order_by(RepaymentSchedule.installment_number.asc()).all()
        assert len(schedules) == 2
        # Sum of principal components equals ₹1,00,000.00
        assert sum(s.principal_amount for s in schedules) == Decimal("100000.00")
        first_sched_id = schedules[0].id
        first_emi_val = schedules[0].total_installment
        second_sched_id = schedules[1].id
        second_emi_val = schedules[1].total_installment

    client.post("/auth/logout", follow_redirects=True)

    # 3. Customer checks Repayment Schedule in INR
    client.post(
        "/auth/login",
        data={"email": "lifecycle.borrower@example.com", "password": "SecurePassword123!", "role": UserRole.CUSTOMER},
        follow_redirects=True,
    )
    sched_page = client.get(f"/customer/loans/{loan_id}/repayments")
    assert sched_page.status_code == 200
    assert b"\xe2\x82\xb9" in sched_page.data  # ₹ symbol rendered
    assert b"Currency: INR" in sched_page.data

    # 4. Customer Pays Installment 1
    pay_res1 = client.post(
        f"/customer/repayments/{first_sched_id}/pay",
        data={
            "amount": str(first_emi_val),
            "payment_method": "UPI",
        },
        follow_redirects=True,
    )
    assert pay_res1.status_code == 200
    assert b"processed successfully" in pay_res1.data

    with app.app_context():
        s1 = db.session.get(RepaymentSchedule, first_sched_id)
        assert s1.status == RepaymentStatus.PAID
        l = db.session.get(LoanApplication, loan_id)
        assert l.status == ApplicationStatus.DISBURSED

    # 5. Customer Pays Final Installment 2 -> Transitions to COMPLETED
    pay_res2 = client.post(
        f"/customer/repayments/{second_sched_id}/pay",
        data={
            "amount": str(second_emi_val),
            "payment_method": "NET_BANKING",
        },
        follow_redirects=True,
    )
    assert pay_res2.status_code == 200

    with app.app_context():
        s2 = db.session.get(RepaymentSchedule, second_sched_id)
        assert s2.status == RepaymentStatus.PAID
        l_settled = db.session.get(LoanApplication, loan_id)
        assert l_settled.status == ApplicationStatus.COMPLETED


# ------------------------------------------------------------------------------
# 6. Rejection Workflow and Audit Trail
# ------------------------------------------------------------------------------

def test_manager_rejection_workflow(client, app):
    """Verifies manager formal rejection records remarks, notifies customer, and blocks further transitions."""
    with app.app_context():
        cust = create_customer("reject.borrower@example.com")
        cust_id = cust.id
        mgr, mgr_secret = create_manager("reject.manager@example.com")
        product = LoanProduct.query.filter_by(code="PERSONAL_PRIME").first()

        loan = LoanApplication(
            customer_id=cust_id,
            product_id=product.id,
            requested_amount=80000.0,
            tenure_months=12,
            interest_rate=12.0,
            status=ApplicationStatus.RECOMMENDED_APPROVAL,
        )
        db.session.add(loan)
        db.session.commit()
        loan_id = loan.id

    login_user_mfa(client, "reject.manager@example.com", "SecurePassword123!", UserRole.LOAN_MANAGER, mgr_secret)
    reject_res = client.post(
        f"/manager/loans/{loan_id}/decision",
        data={
            "decision": "REJECT",
            "remarks": "High debt service commitments exceed portfolio institutional risk tolerances.",
        },
        follow_redirects=True,
    )
    assert reject_res.status_code == 200

    with app.app_context():
        l = db.session.get(LoanApplication, loan_id)
        assert l.status == ApplicationStatus.REJECTED

        # Notification recorded with remarks
        notif = Notification.query.filter_by(user_id=cust_id).first()
        assert notif is not None
        assert "rejected" in notif.message
        assert "institutional risk" in notif.message

        # State machine blocks transition from REJECTED to APPROVED
        assert l.can_transition_to(ApplicationStatus.APPROVED) is False
        with pytest.raises(ValueError):
            l.transition_to(ApplicationStatus.APPROVED)
