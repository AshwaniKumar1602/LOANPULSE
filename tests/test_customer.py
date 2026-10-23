import io
import pytest
from app.extensions import db
from app.models.user import User, UserRole
from app.models.customer import CustomerProfile
from app.models.loan_product import LoanProduct
from app.models.loan_application import LoanApplication, ApplicationStatus
from app.models.repayment import RepaymentSchedule, RepaymentStatus
from app.models.notification import Notification, NotificationType
from datetime import date, timedelta


def create_customer(email, password="SecurePassword123!"):
    user = User(
        email=email,
        first_name="Jane",
        last_name="Borrower",
        role=UserRole.CUSTOMER,
        is_active=True,
    )
    user.set_password(password)
    profile = CustomerProfile(
        credit_score=720,
        annual_income=75000.0,
        monthly_debt=500.0,
        employment_type="SALARIED",
    )
    user.customer_profile = profile
    db.session.add(user)
    db.session.commit()
    return user


def test_customer_dashboard_unauthenticated(client):
    res = client.get("/customer/dashboard")
    assert res.status_code == 302
    assert "/auth/login" in res.headers["Location"]


def test_customer_dashboard_access(client, app):
    with app.app_context():
        customer = create_customer("jane.dashboard@example.com")
        customer_id = customer.id

    client.post(
        "/auth/login",
        data={"email": "jane.dashboard@example.com", "password": "SecurePassword123!", "role": UserRole.CUSTOMER},
        follow_redirects=True,
    )

    res = client.get("/customer/dashboard")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Borrower Dashboard" in html
    assert "Welcome, Jane" in html
    assert "Active Borrowing" in html
    assert "My Applications" in html


def test_customer_apply_loan_and_auto_underwriting(client, app):
    with app.app_context():
        customer = create_customer("jane.apply@example.com")
        customer_id = customer.id
        product = LoanProduct.query.filter_by(code="PERSONAL_PRIME").first()
        prod_id = product.id

    client.post(
        "/auth/login",
        data={"email": "jane.apply@example.com", "password": "SecurePassword123!", "role": UserRole.CUSTOMER},
        follow_redirects=True,
    )

    # Submit application via /customer/loans/apply
    apply_res = client.post(
        "/customer/loans/apply",
        data={
            "product_id": prod_id,
            "requested_amount": "15000",
            "tenure_months": "36",
            "purpose": "Home renovation and improvement",
            "employment_type": "SALARIED",
            "monthly_income": "6250",
            "existing_monthly_debt": "400",
            "tax_id": "123-45-6789",
        },
        follow_redirects=True,
    )
    assert apply_res.status_code == 200

    with app.app_context():
        loan = LoanApplication.query.filter_by(customer_id=customer_id).first()
        assert loan is not None
        assert loan.requested_amount == 15000.0
        assert loan.tenure_months == 36
        assert loan.status in [ApplicationStatus.UNDER_REVIEW, ApplicationStatus.SUBMITTED]
        assert loan.underwriting is not None
        assert loan.underwriting.debt_to_income_ratio > 0


def test_customer_idor_isolation(client, app):
    """Verifies strict server-side IDOR prevention across customer routes."""
    with app.app_context():
        cust_a = create_customer("cust_a@example.com")
        cust_b = create_customer("cust_b@example.com")
        product = LoanProduct.query.filter_by(code="PERSONAL_PRIME").first()

        loan_a = LoanApplication(
            customer_id=cust_a.id,
            product_id=product.id,
            requested_amount=10000.0,
            tenure_months=24,
            interest_rate=10.0,
            status=ApplicationStatus.DISBURSED,
        )
        db.session.add(loan_a)
        db.session.flush()

        schedule_a = RepaymentSchedule(
            application_id=loan_a.id,
            installment_number=1,
            due_date=date.today() + timedelta(days=30),
            principal_amount=400.0,
            interest_amount=83.33,
            total_installment=483.33,
            remaining_principal=9600.0,
            status=RepaymentStatus.UPCOMING,
        )
        notif_a = Notification(
            user_id=cust_a.id,
            title="Loan Disbursed",
            message="Your loan has been disbursed.",
            type=NotificationType.DISBURSEMENT,
        )
        db.session.add_all([schedule_a, notif_a])
        db.session.commit()

        loan_a_id = loan_a.id
        sched_a_id = schedule_a.id
        notif_a_id = notif_a.id

    # Log in as Customer B
    client.post(
        "/auth/login",
        data={"email": "cust_b@example.com", "password": "SecurePassword123!", "role": UserRole.CUSTOMER},
        follow_redirects=True,
    )

    # 1. Customer B attempts to view Customer A's application detail -> 404
    r1 = client.get(f"/customer/loans/{loan_a_id}")
    assert r1.status_code == 404

    # 2. Customer B attempts to view Customer A's repayment schedule -> 404
    r2 = client.get(f"/customer/loans/{loan_a_id}/repayments")
    assert r2.status_code == 404

    # 3. Customer B attempts to export Customer A's repayment CSV -> 404
    r3 = client.get(f"/customer/loans/{loan_a_id}/repayments/export")
    assert r3.status_code == 404

    # 4. Customer B attempts to pay Customer A's installment -> 404
    r4 = client.get(f"/customer/repayments/{sched_a_id}/pay")
    assert r4.status_code == 404

    # 5. Customer B attempts to mark Customer A's notification as read -> 404
    r5 = client.post(f"/customer/notifications/{notif_a_id}/read")
    assert r5.status_code == 404


def test_customer_streamed_repayment_csv_export(client, app):
    """Verifies memory-safe generator CSV streaming for loan repayment schedule."""
    with app.app_context():
        customer = create_customer("jane.repayments@example.com")
        product = LoanProduct.query.filter_by(code="PERSONAL_PRIME").first()

        loan = LoanApplication(
            customer_id=customer.id,
            product_id=product.id,
            requested_amount=12000.0,
            approved_amount=12000.0,
            tenure_months=12,
            interest_rate=10.0,
            status=ApplicationStatus.DISBURSED,
        )
        db.session.add(loan)
        db.session.flush()

        s1 = RepaymentSchedule(
            application_id=loan.id,
            installment_number=1,
            due_date=date(2026, 1, 15),
            principal_amount=950.0,
            interest_amount=100.0,
            total_installment=1050.0,
            remaining_principal=11050.0,
            status=RepaymentStatus.UPCOMING,
        )
        s2 = RepaymentSchedule(
            application_id=loan.id,
            installment_number=2,
            due_date=date(2026, 2, 15),
            principal_amount=958.0,
            interest_amount=92.0,
            total_installment=1050.0,
            remaining_principal=10092.0,
            status=RepaymentStatus.UPCOMING,
        )
        db.session.add_all([s1, s2])
        db.session.commit()
        loan_id = loan.id
        app_num = loan.application_number

    client.post(
        "/auth/login",
        data={"email": "jane.repayments@example.com", "password": "SecurePassword123!", "role": UserRole.CUSTOMER},
        follow_redirects=True,
    )

    res = client.get(f"/customer/loans/{loan_id}/repayments/export")
    assert res.status_code == 200
    assert res.mimetype == "text/csv"
    assert f"repayment_schedule_{app_num}.csv" in res.headers["Content-Disposition"]

    content = res.data.decode("utf-8")
    assert "Installment Number" in content
    assert "Due Date" in content
    assert "Total Installment" in content
    assert "Principal Component" in content
    assert "Interest Component" in content
    assert "2026-01-15" in content
    assert "2026-02-15" in content


def test_customer_notifications_management(client, app):
    """Verifies notification feed rendering, individual mark-read, and mark-all-read."""
    with app.app_context():
        customer = create_customer("jane.notifications@example.com")
        customer_id = customer.id
        n1 = Notification(
            user_id=customer_id,
            title="Application Under Review",
            message="Your loan application is being reviewed by our officer.",
            type=NotificationType.APPLICATION_STATUS,
            is_read=False,
        )
        n2 = Notification(
            user_id=customer_id,
            title="Document Received",
            message="Your paystub was uploaded successfully.",
            type=NotificationType.DOCUMENT_REQUEST,
            is_read=False,
        )
        db.session.add_all([n1, n2])
        db.session.commit()
        n1_id = n1.id

    client.post(
        "/auth/login",
        data={"email": "jane.notifications@example.com", "password": "SecurePassword123!", "role": UserRole.CUSTOMER},
        follow_redirects=True,
    )

    # 1. Access Notification Center
    res = client.get("/customer/notifications")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Notification Feed" in html
    assert "Application Under Review" in html
    assert "Document Received" in html

    # 2. Mark single notification as read
    res_read = client.post(f"/customer/notifications/{n1_id}/read", follow_redirects=True)
    assert res_read.status_code == 200

    with app.app_context():
        checked_n1 = db.session.get(Notification, n1_id)
        assert checked_n1.is_read is True

    # 3. Mark all notifications as read
    res_all = client.post("/customer/notifications/read-all", follow_redirects=True)
    assert res_all.status_code == 200

    with app.app_context():
        unread_count = Notification.query.filter_by(user_id=customer_id, is_read=False).count()
        assert unread_count == 0


def test_customer_document_upload_and_secure_download(client, app):
    """Verifies secure document upload (MIME magic check, UUID storage) and download IDOR prevention."""
    with app.app_context():
        customer = create_customer("jane.docs@example.com")
        customer_id = customer.id
        cust_stranger = create_customer("stranger.docs@example.com")
        stranger_id = cust_stranger.id
        product = LoanProduct.query.filter_by(code="PERSONAL_PRIME").first()

        loan = LoanApplication(
            customer_id=customer_id,
            product_id=product.id,
            requested_amount=8000.0,
            tenure_months=24,
            interest_rate=10.0,
            status=ApplicationStatus.SUBMITTED,
        )
        db.session.add(loan)
        db.session.commit()
        loan_id = loan.id

    client.post(
        "/auth/login",
        data={"email": "jane.docs@example.com", "password": "SecurePassword123!", "role": UserRole.CUSTOMER},
        follow_redirects=True,
    )

    # Valid PDF with magic header b"%PDF-"
    valid_pdf_bytes = b"%PDF-1.4\n%test content of customer income verification document\n%%EOF"
    upload_res = client.post(
        f"/customer/loans/{loan_id}/documents/upload",
        data={
            "document_type": "INCOME_PROOF",
            "document_file": (io.BytesIO(valid_pdf_bytes), "income_stub.pdf"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert upload_res.status_code == 200

    with app.app_context():
        from app.models.document import ApplicationDocument
        doc = ApplicationDocument.query.filter_by(application_id=loan_id).first()
        assert doc is not None
        assert doc.user_id == customer_id
        assert doc.document_type == "INCOME_PROOF"
        assert doc.original_filename == "income_stub.pdf"
        assert doc.file_uuid is not None
        doc_uuid = doc.file_uuid

    # Download by owner customer -> 200
    down_res = client.get(f"/customer/documents/{doc_uuid}/download")
    assert down_res.status_code == 200
    assert down_res.mimetype == "application/pdf"
    assert b"%PDF-1.4" in down_res.data

    # Sign out first before switching identity
    client.post("/auth/logout", follow_redirects=True)

    # Log in as stranger customer
    client.post(
        "/auth/login",
        data={"email": "stranger.docs@example.com", "password": "SecurePassword123!", "role": UserRole.CUSTOMER},
        follow_redirects=True,
    )

    # Stranger attempts to download -> 403 Forbidden
    down_stranger = client.get(f"/customer/documents/{doc_uuid}/download")
    assert down_stranger.status_code == 403

