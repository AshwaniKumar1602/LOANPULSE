import pyotp
import pytest
from app.extensions import db
from app.models.user import User, UserRole
from app.models.customer import CustomerProfile
from app.models.loan_product import LoanProduct
from app.models.loan_application import LoanApplication, ApplicationStatus
from app.models.document import ApplicationDocument, DocumentStatus
from app.models.audit import DecisionAuditLog, AuditAction
from app.models.notification import Notification, NotificationType


def create_officer_user(email="officer.test@example.com", password="SecurePassword123!"):
    totp_secret = "JBSWY3DPEHPK3PXP"
    user = User(
        email=email,
        first_name="Oscar",
        last_name="Officer",
        role=UserRole.LOAN_OFFICER,
        is_active=True,
        totp_enabled=True,
        totp_secret=totp_secret,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user, totp_secret


def create_customer_user(email="customer.borrower@example.com", password="SecurePassword123!"):
    user = User(
        email=email,
        first_name="Alice",
        last_name="Borrower",
        role=UserRole.CUSTOMER,
        is_active=True,
    )
    user.set_password(password)
    profile = CustomerProfile(
        credit_score=710,
        annual_income=84000.0,
        monthly_debt=450.0,
        employment_type="SALARIED",
        tax_id_masked="***-**-9876",
    )
    user.customer_profile = profile
    db.session.add(user)
    db.session.commit()
    return user


def login_officer(client, email="officer.test@example.com", password="SecurePassword123!", totp_secret="JBSWY3DPEHPK3PXP"):
    # Step 1: Login credentials
    client.post(
        "/auth/login",
        data={"email": email, "password": password, "role": UserRole.LOAN_OFFICER},
        follow_redirects=True,
    )
    # Step 2: MFA verification
    token = pyotp.TOTP(totp_secret).now()
    client.post("/auth/mfa/verify", data={"totp_token": token}, follow_redirects=True)


def test_officer_rbac_enforcement(client, app):
    """Verifies that non-officers (e.g. CUSTOMER) are blocked with 403 Forbidden."""
    with app.app_context():
        create_customer_user("blocked.customer@example.com")

    # Log in as customer
    client.post(
        "/auth/login",
        data={"email": "blocked.customer@example.com", "password": "SecurePassword123!", "role": UserRole.CUSTOMER},
        follow_redirects=True,
    )

    # Customer attempts to access officer dashboard -> 403 Forbidden
    res = client.get("/officer/dashboard")
    assert res.status_code == 403

    # Customer attempts to access officer review -> 403 Forbidden
    res_review = client.get("/officer/loans/1/review")
    assert res_review.status_code == 403


def test_officer_role_normalization_and_helper(app):
    """Verifies User.has_role supports both ROLE_LOAN_OFFICER and LOAN_OFFICER."""
    with app.app_context():
        user, _ = create_officer_user("rolecheck.officer@example.com")
        assert user.has_role("ROLE_LOAN_OFFICER") is True
        assert user.has_role(UserRole.LOAN_OFFICER) is True
        assert user.has_role("ROLE_CUSTOMER") is False
        assert user.is_officer is True
        assert user.is_customer is False


def test_officer_queue_and_filters(client, app):
    """Verifies Queue rendering, status counters, and search filtering."""
    with app.app_context():
        officer, totp_sec = create_officer_user("queue.officer@example.com")
        cust1 = create_customer_user("applicant1@example.com")
        product = LoanProduct.query.filter_by(code="PERSONAL_PRIME").first()

        app1 = LoanApplication(
            customer_id=cust1.id,
            product_id=product.id,
            requested_amount=10000.0,
            tenure_months=24,
            interest_rate=10.0,
            status=ApplicationStatus.SUBMITTED,
        )
        app2 = LoanApplication(
            customer_id=cust1.id,
            product_id=product.id,
            requested_amount=20000.0,
            tenure_months=36,
            interest_rate=10.0,
            status=ApplicationStatus.UNDER_REVIEW,
        )
        db.session.add_all([app1, app2])
        db.session.commit()
        app1_num = app1.application_number

    login_officer(client, email="queue.officer@example.com", totp_secret=totp_sec)

    # Dashboard view
    res = client.get("/officer/dashboard")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Application Underwriting Queue" in html
    assert "New Submissions" in html
    assert "In Active Review" in html
    assert app1_num in html

    # Filter by status SUBMITTED
    res_filter = client.get("/officer/dashboard?status=SUBMITTED")
    assert res_filter.status_code == 200
    assert app1_num in res_filter.data.decode("utf-8")

    # Search filter by applicant email
    res_search = client.get("/officer/dashboard?q=applicant1")
    assert res_search.status_code == 200
    assert "applicant1@example.com" in res_search.data.decode("utf-8")


def test_officer_review_page_auto_advance_and_underwriting_matrix(client, app):
    """Verifies opening review auto-advances SUBMITTED -> UNDER_REVIEW and displays rule matrix."""
    with app.app_context():
        officer, totp_sec = create_officer_user("reviewer.officer@example.com")
        cust = create_customer_user("applicant.review@example.com")
        product = LoanProduct.query.filter_by(code="PERSONAL_PRIME").first()

        loan = LoanApplication(
            customer_id=cust.id,
            product_id=product.id,
            requested_amount=15000.0,
            tenure_months=36,
            interest_rate=10.0,
            status=ApplicationStatus.SUBMITTED,
            monthly_income_declared=7000.0,
            existing_monthly_debt=400.0,
        )
        db.session.add(loan)
        db.session.commit()
        loan_id = loan.id

    login_officer(client, email="reviewer.officer@example.com", totp_secret=totp_sec)

    # Visit review page
    res = client.get(f"/officer/loans/{loan_id}/review")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Applicant Financial Profile" in html
    assert "Requested Financing" in html
    assert "Automated Underwriting Engine Evaluation Matrix" in html
    assert "Credit Score Check" in html
    assert "Debt-to-Income (DTI)" in html

    # Verify status transitioned from SUBMITTED to UNDER_REVIEW
    with app.app_context():
        refreshed_loan = db.session.get(LoanApplication, loan_id)
        assert refreshed_loan.status == ApplicationStatus.UNDER_REVIEW

        # Audit log was created
        audit = DecisionAuditLog.query.filter_by(application_id=loan_id, action=AuditAction.UNDERWRITING_EVALUATED).first()
        assert audit is not None


def test_officer_document_verification_workflow(client, app):
    """Verifies officer document acceptance and rejection with customer notification."""
    with app.app_context():
        officer, totp_sec = create_officer_user("docverify.officer@example.com")
        cust = create_customer_user("applicant.docs@example.com")
        cust_id = cust.id
        product = LoanProduct.query.filter_by(code="PERSONAL_PRIME").first()

        loan = LoanApplication(
            customer_id=cust.id,
            product_id=product.id,
            requested_amount=5000.0,
            tenure_months=12,
            interest_rate=10.0,
            status=ApplicationStatus.UNDER_REVIEW,
        )
        db.session.add(loan)
        db.session.flush()

        doc = ApplicationDocument(
            application_id=loan.id,
            user_id=cust.id,
            document_type="IDENTITY_PROOF",
            original_filename="passport.pdf",
            stored_filename="test_passport.pdf",
            file_uuid="test-uuid-passport",
            file_size=20480,
            mime_type="application/pdf",
            verification_status=DocumentStatus.PENDING,
        )
        db.session.add(doc)
        db.session.commit()
        doc_id = doc.id
        loan_id = loan.id

    login_officer(client, email="docverify.officer@example.com", totp_secret=totp_sec)

    # 1. Accept / Verify document
    res_accept = client.post(
        f"/officer/documents/{doc_id}/verify",
        data={"verification_status": DocumentStatus.VERIFIED, "verification_notes": "Valid government ID verified."},
        follow_redirects=True,
    )
    assert res_accept.status_code == 200

    with app.app_context():
        checked_doc = db.session.get(ApplicationDocument, doc_id)
        assert checked_doc.verification_status == DocumentStatus.VERIFIED
        assert checked_doc.verification_notes == "Valid government ID verified."

    # 2. Reject document with reason -> triggers customer notification
    res_reject = client.post(
        f"/officer/documents/{doc_id}/verify",
        data={"verification_status": DocumentStatus.REJECTED, "verification_notes": "Image is blurry and unreadable."},
        follow_redirects=True,
    )
    assert res_reject.status_code == 200

    with app.app_context():
        checked_doc2 = db.session.get(ApplicationDocument, doc_id)
        assert checked_doc2.verification_status == DocumentStatus.REJECTED

        notif = Notification.query.filter_by(user_id=cust_id, type=NotificationType.DOCUMENT_REQUEST).first()
        assert notif is not None
        assert "blurry and unreadable" in notif.message


def test_officer_recommendation_and_forwarding_to_manager(client, app):
    """Verifies officer review notes, requesting resubmission, and recommending approval/rejection."""
    with app.app_context():
        officer, totp_sec = create_officer_user("rec.officer@example.com")
        cust = create_customer_user("applicant.rec@example.com")
        product = LoanProduct.query.filter_by(code="PERSONAL_PRIME").first()

        loan = LoanApplication(
            customer_id=cust.id,
            product_id=product.id,
            requested_amount=18000.0,
            tenure_months=36,
            interest_rate=10.0,
            status=ApplicationStatus.UNDER_REVIEW,
        )
        db.session.add(loan)
        db.session.commit()
        loan_id = loan.id

    login_officer(client, email="rec.officer@example.com", totp_secret=totp_sec)

    # 1. Save Underwriting Notes (Keep in UNDER_REVIEW)
    res_notes = client.post(
        f"/officer/loans/{loan_id}/recommend",
        data={
            "recommendation": ApplicationStatus.UNDER_REVIEW,
            "notes": "Verified applicant employment directly with HR payroll department.",
        },
        follow_redirects=True,
    )
    assert res_notes.status_code == 200
    with app.app_context():
        l = db.session.get(LoanApplication, loan_id)
        assert l.status == ApplicationStatus.UNDER_REVIEW

    # 2. Request Document Resubmission (PENDING_DOCS)
    res_docs = client.post(
        f"/officer/loans/{loan_id}/recommend",
        data={
            "recommendation": ApplicationStatus.PENDING_DOCS,
            "notes": "Please provide latest 3 months bank statements showing recurring salary credits.",
        },
        follow_redirects=True,
    )
    assert res_docs.status_code == 200
    with app.app_context():
        l = db.session.get(LoanApplication, loan_id)
        assert l.status == ApplicationStatus.PENDING_DOCS

    # 3. Forward to Manager: Recommend Approval
    res_appr = client.post(
        f"/officer/loans/{loan_id}/recommend",
        data={
            "recommendation": ApplicationStatus.RECOMMENDED_APPROVAL,
            "notes": "All checks passed. Strong credit score and stable employment. Recommend approval.",
        },
        follow_redirects=True,
    )
    assert res_appr.status_code == 200
    with app.app_context():
        l = db.session.get(LoanApplication, loan_id)
        assert l.status == ApplicationStatus.RECOMMENDED_APPROVAL


def test_officer_tampering_protection_on_finalized_loans(client, app):
    """Verifies officer cannot tamper with loans that have already been finalized by a Manager."""
    with app.app_context():
        officer, totp_sec = create_officer_user("tamper.officer@example.com")
        cust = create_customer_user("applicant.final@example.com")
        product = LoanProduct.query.filter_by(code="PERSONAL_PRIME").first()

        loan_approved = LoanApplication(
            customer_id=cust.id,
            product_id=product.id,
            requested_amount=10000.0,
            approved_amount=10000.0,
            tenure_months=24,
            interest_rate=10.0,
            status=ApplicationStatus.APPROVED,
        )
        db.session.add(loan_approved)
        db.session.commit()
        approved_id = loan_approved.id

    login_officer(client, email="tamper.officer@example.com", totp_secret=totp_sec)

    # Attempt to change status on already APPROVED loan
    res = client.post(
        f"/officer/loans/{approved_id}/recommend",
        data={
            "recommendation": ApplicationStatus.RECOMMENDED_REJECTION,
            "notes": "Attempting to overwrite finalized manager decision.",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200

    # Ensure status remained APPROVED
    with app.app_context():
        l = db.session.get(LoanApplication, approved_id)
        assert l.status == ApplicationStatus.APPROVED
