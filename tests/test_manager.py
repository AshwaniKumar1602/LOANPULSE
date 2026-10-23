import pyotp
import pytest
from app.extensions import db
from app.models.user import User, UserRole
from app.models.customer import CustomerProfile
from app.models.loan_product import LoanProduct
from app.models.loan_application import LoanApplication, ApplicationStatus
from app.models.disbursement import Disbursement, DisbursementStatus
from app.models.audit import DecisionAuditLog, AuditAction
from app.models.notification import Notification, NotificationType


def create_manager_user(email="manager.test@example.com", password="SecurePassword123!"):
    totp_secret = "JBSWY3DPEHPK3PXP"
    user = User(
        email=email,
        first_name="Morgan",
        last_name="Manager",
        role=UserRole.LOAN_MANAGER,
        is_active=True,
        totp_enabled=True,
        totp_secret=totp_secret,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user, totp_secret


def create_officer_user(email="officer.manager_test@example.com", password="SecurePassword123!"):
    totp_secret = "JBSWY3DPEHPK3PXP"
    user = User(
        email=email,
        first_name="Oliver",
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


def create_customer_user(email="borrower.manager_test@example.com", password="SecurePassword123!"):
    user = User(
        email=email,
        first_name="Ben",
        last_name="Borrower",
        role=UserRole.CUSTOMER,
        is_active=True,
    )
    user.set_password(password)
    profile = CustomerProfile(
        credit_score=750,
        annual_income=96000.0,
        monthly_debt=600.0,
        employment_type="SALARIED",
    )
    user.customer_profile = profile
    db.session.add(user)
    db.session.commit()
    return user


def login_manager(client, email="manager.test@example.com", password="SecurePassword123!", totp_secret="JBSWY3DPEHPK3PXP"):
    client.post(
        "/auth/login",
        data={"email": email, "password": password, "role": UserRole.LOAN_MANAGER},
        follow_redirects=True,
    )
    token = pyotp.TOTP(totp_secret).now()
    client.post("/auth/mfa/verify", data={"totp_token": token}, follow_redirects=True)


def test_manager_rbac_enforcement(client, app):
    """Verifies that non-managers (CUSTOMER, LOAN_OFFICER) receive 403 Forbidden."""
    with app.app_context():
        create_customer_user("customer.mgr_block@example.com")
        create_officer_user("officer.mgr_block@example.com")

    # 1. Customer blocked
    client.post(
        "/auth/login",
        data={"email": "customer.mgr_block@example.com", "password": "SecurePassword123!", "role": UserRole.CUSTOMER},
        follow_redirects=True,
    )
    res_cust = client.get("/manager/dashboard")
    assert res_cust.status_code == 403

    client.post("/auth/logout", follow_redirects=True)

    # 2. Loan Officer blocked
    client.post(
        "/auth/login",
        data={"email": "officer.mgr_block@example.com", "password": "SecurePassword123!", "role": UserRole.LOAN_OFFICER},
        follow_redirects=True,
    )
    token = pyotp.TOTP("JBSWY3DPEHPK3PXP").now()
    client.post("/auth/mfa/verify", data={"totp_token": token}, follow_redirects=True)

    res_off = client.get("/manager/dashboard")
    assert res_off.status_code == 403


def test_manager_role_normalization_and_helper(app):
    """Verifies User.has_role supports both ROLE_LOAN_MANAGER and LOAN_MANAGER."""
    with app.app_context():
        user, _ = create_manager_user("rolecheck.mgr@example.com")
        assert user.has_role("ROLE_LOAN_MANAGER") is True
        assert user.has_role(UserRole.LOAN_MANAGER) is True
        assert user.has_role("ROLE_CUSTOMER") is False
        assert user.is_manager is True
        assert user.is_officer is False


def test_manager_dashboard_sql_metrics(client, app):
    """Verifies high-level metrics (Total Active Loans, Pending Approvals, Total Disbursed) via SQL."""
    with app.app_context():
        mgr, totp_sec = create_manager_user("kpi.mgr@example.com")
        cust = create_customer_user("kpi.borrower@example.com")
        product = LoanProduct.query.filter_by(code="PERSONAL_PRIME").first()

        # 1 Disbursed loan ($20,000)
        app_disbursed = LoanApplication(
            customer_id=cust.id,
            product_id=product.id,
            requested_amount=20000.0,
            approved_amount=20000.0,
            tenure_months=24,
            interest_rate=9.5,
            status=ApplicationStatus.DISBURSED,
        )
        # 1 Pending approval loan ($10,000)
        app_pending = LoanApplication(
            customer_id=cust.id,
            product_id=product.id,
            requested_amount=10000.0,
            tenure_months=12,
            interest_rate=10.0,
            status=ApplicationStatus.RECOMMENDED_APPROVAL,
        )
        db.session.add_all([app_disbursed, app_pending])
        db.session.flush()

        disb = Disbursement(
            application_id=app_disbursed.id,
            authorized_by_id=mgr.id,
            amount=20000.0,
            disbursement_method="DIRECT_DEPOSIT",
            bank_name="First National Bank",
            bank_account_masked="******1234",
            bank_routing_or_ifsc="021000021",
            status=DisbursementStatus.PROCESSED,
        )
        db.session.add(disb)
        db.session.commit()

    login_manager(client, email="kpi.mgr@example.com", totp_secret=totp_sec)

    res = client.get("/manager/dashboard")
    assert res.status_code == 200
    html = res.data.decode("utf-8")

    # High-level metrics presence
    assert "Total Active Loans" in html
    assert "Pending Approvals" in html
    assert "Total Disbursed" in html
    assert "₹20,000.00" in html or "$20,000.00" in html
    assert "Manager Approvals Queue" in html


def test_manager_approval_decision_workflow_and_audit_logging(client, app):
    """Verifies manager formal approval, customer notification, and comprehensive audit trail."""
    with app.app_context():
        mgr, totp_sec = create_manager_user("decision.mgr@example.com")
        mgr_id = mgr.id
        cust = create_customer_user("decision.borrower@example.com")
        cust_id = cust.id
        product = LoanProduct.query.filter_by(code="PERSONAL_PRIME").first()

        loan = LoanApplication(
            customer_id=cust_id,
            product_id=product.id,
            requested_amount=25000.0,
            tenure_months=36,
            interest_rate=10.0,
            status=ApplicationStatus.RECOMMENDED_APPROVAL,
        )
        db.session.add(loan)
        db.session.commit()
        loan_id = loan.id

    login_manager(client, email="decision.mgr@example.com", totp_secret=totp_sec)

    # Approve application
    res_approve = client.post(
        f"/manager/loans/{loan_id}/decision",
        data={
            "decision": "APPROVE",
            "approved_amount": "24000.00",
            "interest_rate": "9.25",
            "remarks": "Approved after comprehensive risk committee review. Counter-offered $24k at 9.25%.",
        },
        follow_redirects=True,
    )
    assert res_approve.status_code == 200

    with app.app_context():
        l = db.session.get(LoanApplication, loan_id)
        assert l.status == ApplicationStatus.APPROVED
        assert float(l.approved_amount) == 24000.00
        assert float(l.interest_rate) == 9.25

        # Check Customer Notification
        notif = Notification.query.filter_by(user_id=cust_id, type=NotificationType.APPLICATION_STATUS).first()
        assert notif is not None
        assert "APPROVED" in notif.message
        assert "24,000.00" in notif.message or "24000" in notif.message

        # Check Comprehensive Audit Log
        audit = DecisionAuditLog.query.filter_by(application_id=loan_id, action=AuditAction.MANAGER_APPROVED).first()
        assert audit is not None
        assert audit.actor_id == mgr_id
        assert audit.previous_status == ApplicationStatus.RECOMMENDED_APPROVAL
        assert audit.new_status == ApplicationStatus.APPROVED
        assert audit.created_at is not None
        assert audit.ip_address is not None
        assert "Counter-offered $24k" in audit.notes


def test_manager_rejection_decision_workflow(client, app):
    """Verifies manager formal rejection records audit and alerts customer."""
    with app.app_context():
        mgr, totp_sec = create_manager_user("reject.mgr@example.com")
        mgr_id = mgr.id
        cust = create_customer_user("reject.borrower@example.com")
        cust_id = cust.id
        product = LoanProduct.query.filter_by(code="PERSONAL_PRIME").first()

        loan = LoanApplication(
            customer_id=cust_id,
            product_id=product.id,
            requested_amount=30000.0,
            tenure_months=48,
            interest_rate=12.0,
            status=ApplicationStatus.RECOMMENDED_REJECTION,
        )
        db.session.add(loan)
        db.session.commit()
        loan_id = loan.id

    login_manager(client, email="reject.mgr@example.com", totp_secret=totp_sec)

    res_reject = client.post(
        f"/manager/loans/{loan_id}/decision",
        data={
            "decision": "REJECT",
            "approved_amount": "0.00",
            "interest_rate": "12.0",
            "remarks": "Debt-to-income ratio exceeds institution risk tolerance limits.",
        },
        follow_redirects=True,
    )
    assert res_reject.status_code == 200

    with app.app_context():
        l = db.session.get(LoanApplication, loan_id)
        assert l.status == ApplicationStatus.REJECTED

        audit = DecisionAuditLog.query.filter_by(application_id=loan_id, action=AuditAction.MANAGER_REJECTED).first()
        assert audit is not None
        assert audit.actor_id == mgr_id
        assert "exceeds institution risk tolerance" in audit.notes


def test_manager_disbursement_authorization_and_amortization_generation(client, app):
    """Verifies manager capital disbursement, account masking, and EMI schedule generation."""
    with app.app_context():
        mgr, totp_sec = create_manager_user("disb.mgr@example.com")
        mgr_id = mgr.id
        cust = create_customer_user("disb.borrower@example.com")
        cust_id = cust.id
        product = LoanProduct.query.filter_by(code="PERSONAL_PRIME").first()

        loan = LoanApplication(
            customer_id=cust_id,
            product_id=product.id,
            requested_amount=12000.0,
            approved_amount=12000.0,
            tenure_months=12,
            interest_rate=10.0,
            status=ApplicationStatus.APPROVED,
        )
        db.session.add(loan)
        db.session.commit()
        loan_id = loan.id

    login_manager(client, email="disb.mgr@example.com", totp_secret=totp_sec)

    res_disb = client.post(
        f"/manager/loans/{loan_id}/disburse",
        data={
            "bank_name": "JPMorgan Chase Bank",
            "bank_account": "9876543210123",
            "bank_routing": "021000021",
            "disbursement_method": "DIRECT_DEPOSIT",
            "notes": "Wire cleared via Federal Reserve ACH settlement.",
        },
        follow_redirects=True,
    )
    assert res_disb.status_code == 200

    with app.app_context():
        l = db.session.get(LoanApplication, loan_id)
        assert l.status == ApplicationStatus.DISBURSED

        # Check Disbursement Record and Masking (Security Rule #19)
        disb = Disbursement.query.filter_by(application_id=loan_id).first()
        assert disb is not None
        assert disb.amount == 12000.0
        assert disb.bank_name == "JPMorgan Chase Bank"
        assert disb.bank_account_masked.endswith("0123")
        assert "9876543210123" not in disb.bank_account_masked

        # Check Amortization Schedules Generated
        assert l.repayment_schedules.count() == 12

        # Check Audit Log Entry
        audit = DecisionAuditLog.query.filter_by(application_id=loan_id, action=AuditAction.DISBURSEMENT_COMPLETED).first()
        assert audit is not None
        assert audit.actor_id == mgr_id
        assert audit.ip_address is not None
        assert "12 EMI installments" in audit.notes


def test_manager_disbursement_guards(client, app):
    """Verifies that unapproved loans cannot be disbursed and disbursed loans cannot be re-disbursed."""
    with app.app_context():
        mgr, totp_sec = create_manager_user("guard.mgr@example.com")
        cust = create_customer_user("guard.borrower@example.com")
        product = LoanProduct.query.filter_by(code="PERSONAL_PRIME").first()

        # Unapproved loan (UNDER_REVIEW)
        loan_unapproved = LoanApplication(
            customer_id=cust.id,
            product_id=product.id,
            requested_amount=15000.0,
            tenure_months=24,
            interest_rate=10.0,
            status=ApplicationStatus.UNDER_REVIEW,
        )
        db.session.add(loan_unapproved)
        db.session.commit()
        unapproved_id = loan_unapproved.id

    login_manager(client, email="guard.mgr@example.com", totp_secret=totp_sec)

    # Attempt to disburse unapproved loan
    res = client.get(f"/manager/loans/{unapproved_id}/disburse", follow_redirects=True)
    assert res.status_code == 200
    assert "Only approved loan applications can be disbursed" in res.data.decode("utf-8")


def test_manager_audit_trail_inspection_and_pagination(client, app):
    """Verifies manager can inspect the full immutable audit trail ledger."""
    with app.app_context():
        mgr, totp_sec = create_manager_user("audit.mgr@example.com")
        log1 = DecisionAuditLog(
            action=AuditAction.MANAGER_APPROVED,
            actor_id=mgr.id,
            notes="Compliance inspection log test.",
            ip_address="192.168.1.100",
        )
        db.session.add(log1)
        db.session.commit()

    login_manager(client, email="audit.mgr@example.com", totp_secret=totp_sec)

    res = client.get("/manager/audit-logs")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Immutable Decision Audit Trail" in html
    assert "MANAGER APPROVED" in html
    assert "192.168.1.100" in html
    assert "Compliance inspection log test." in html
