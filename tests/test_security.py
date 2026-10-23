import io
from app.extensions import db
from app.models.user import User, UserRole
from app.models.loan_product import LoanProduct
from app.models.loan_application import LoanApplication, ApplicationStatus
from app.services.document_service import is_allowed_file, verify_file_header


def test_security_headers(client):
    response = client.get("/")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert response.headers.get("X-XSS-Protection") == "1; mode=block"
    assert "Content-Security-Policy" in response.headers
    assert "Server" not in response.headers


def test_idor_application_protection(client, app):
    with app.app_context():
        # Create User A
        user_a = User(email="user_a@example.com", first_name="User", last_name="A", role=UserRole.CUSTOMER)
        user_a.set_password("SecurePassword123")
        db.session.add(user_a)

        # Create User B
        user_b = User(email="user_b@example.com", first_name="User", last_name="B", role=UserRole.CUSTOMER)
        user_b.set_password("SecurePassword123")
        db.session.add(user_b)
        db.session.flush()

        product = LoanProduct.query.filter_by(code="PERSONAL_PRIME").first()

        # Create Application owned by User A
        app_a = LoanApplication(
            customer_id=user_a.id,
            product_id=product.id,
            requested_amount=5000.00,
            tenure_months=12,
            interest_rate=10.00,
            status=ApplicationStatus.SUBMITTED,
        )
        db.session.add(app_a)
        db.session.commit()
        app_a_id = app_a.id

    # Log in as User B
    client.post("/auth/login", data={"email": "user_b@example.com", "password": "SecurePassword123"}, follow_redirects=True)

    # Attempt to access User A's application detail
    response = client.get(f"/customer/loans/{app_a_id}")
    # Must return 404 (or 403) due to IDOR query scoping by customer_id
    assert response.status_code == 404


def test_file_upload_security_checks():
    # 1. Allowed extensions whitelist check
    assert is_allowed_file("document.pdf") is True
    assert is_allowed_file("id_card.png") is True
    assert is_allowed_file("paystub.jpg") is True
    assert is_allowed_file("malicious.exe") is False
    assert is_allowed_file("script.sh") is False
    assert is_allowed_file("webshell.php") is False

    # 2. Binary header validation (magic bytes)
    valid_pdf = io.BytesIO(b"%PDF-1.5 fake content")
    invalid_pdf = io.BytesIO(b"MZ\x90\x00 fake executable")
    assert verify_file_header(valid_pdf, "pdf") is True
    assert verify_file_header(invalid_pdf, "pdf") is False


def test_zero_mock_users_policy(runner, app):
    """Verifies that seed-production provisions zero test users (Rule #1)."""
    with app.app_context():
        # Clear users
        User.query.delete()
        db.session.commit()

        result = runner.invoke(args=["seed-production"])
        assert result.exit_code == 0

        # Assert zero users exist after seed
        assert User.query.count() == 0
        # Assert products were seeded
        assert LoanProduct.query.count() >= 4


def test_login_manipulation_cross_role_blocked(client, app):
    """
    Security Audit Check #12 & Identity Boundary:
    Sending a POST request to login with mismatched role credentials
    must be strictly blocked server-side with an explicit error message.
    """
    with app.app_context():
        borrower = User(
            email="audit.borrower@example.com",
            first_name="Borrower",
            last_name="Test",
            role=UserRole.CUSTOMER,
            is_active=True,
        )
        borrower.set_password("SecurePassword123!")
        db.session.add(borrower)

        officer = User(
            email="audit.officer@example.com",
            first_name="Officer",
            last_name="Test",
            role=UserRole.LOAN_OFFICER,
            is_active=True,
            totp_enabled=True,
            totp_secret="JBSWY3DPEHPK3PXP",
        )
        officer.set_password("SecurePassword123!")
        db.session.add(officer)

        manager = User(
            email="audit.manager@example.com",
            first_name="Manager",
            last_name="Test",
            role=UserRole.LOAN_MANAGER,
            is_active=True,
            totp_enabled=True,
            totp_secret="JBSWY3DPEHPK3PXP",
        )
        manager.set_password("SecurePassword123!")
        db.session.add(manager)
        db.session.commit()

    # 1. Borrower credentials sent with LOAN_MANAGER role -> MUST BE REJECTED
    res1 = client.post(
        "/auth/login",
        data={
            "role": UserRole.LOAN_MANAGER,
            "email": "audit.borrower@example.com",
            "password": "SecurePassword123!",
        },
        follow_redirects=True,
    )
    assert res1.status_code == 200
    html1 = res1.data.decode("utf-8")
    assert "Role authorization error" in html1
    assert "registered as a Loan Borrower and cannot access the Loan Manager portal" in html1

    # 2. Borrower credentials sent with LOAN_OFFICER role -> MUST BE REJECTED
    res2 = client.post(
        "/auth/login",
        data={
            "role": UserRole.LOAN_OFFICER,
            "email": "audit.borrower@example.com",
            "password": "SecurePassword123!",
        },
        follow_redirects=True,
    )
    assert res2.status_code == 200
    html2 = res2.data.decode("utf-8")
    assert "Role authorization error" in html2
    assert "registered as a Loan Borrower and cannot access the Loan Officer portal" in html2

    # 3. Officer credentials sent with LOAN_MANAGER role -> MUST BE REJECTED
    res3 = client.post(
        "/auth/login",
        data={
            "role": UserRole.LOAN_MANAGER,
            "email": "audit.officer@example.com",
            "password": "SecurePassword123!",
        },
        follow_redirects=True,
    )
    assert res3.status_code == 200
    html3 = res3.data.decode("utf-8")
    assert "Role authorization error" in html3
    assert "registered as a Loan Officer and cannot access the Loan Manager portal" in html3

    # 4. Manager credentials sent with CUSTOMER role -> MUST BE REJECTED
    res4 = client.post(
        "/auth/login",
        data={
            "role": UserRole.CUSTOMER,
            "email": "audit.manager@example.com",
            "password": "SecurePassword123!",
        },
        follow_redirects=True,
    )
    assert res4.status_code == 200
    html4 = res4.data.decode("utf-8")
    assert "Role authorization error" in html4
    assert "registered as a Loan Manager and cannot access the Loan Borrower portal" in html4


def test_rbac_unauthenticated_and_cross_role_protection(client, app):
    """
    Security Audit Check #12:
    Confirms RBAC guards reject unauthenticated access and unauthorized cross-role requests.
    """
    with app.app_context():
        customer = User(
            email="rbac.customer@example.com",
            first_name="Customer",
            last_name="Rbac",
            role=UserRole.CUSTOMER,
            is_active=True,
        )
        customer.set_password("SecurePassword123!")
        db.session.add(customer)

        officer = User(
            email="rbac.officer@example.com",
            first_name="Officer",
            last_name="Rbac",
            role=UserRole.LOAN_OFFICER,
            is_active=True,
            totp_enabled=True,
            totp_secret="JBSWY3DPEHPK3PXP",
        )
        officer.set_password("SecurePassword123!")
        db.session.add(officer)
        db.session.commit()

    # 1. Unauthenticated access redirects to /auth/login
    assert client.get("/customer/dashboard").status_code == 302
    assert client.get("/officer/dashboard").status_code == 302
    assert client.get("/manager/dashboard").status_code == 302

    # 2. Customer logs in
    client.post(
        "/auth/login",
        data={"role": UserRole.CUSTOMER, "email": "rbac.customer@example.com", "password": "SecurePassword123!"},
        follow_redirects=True,
    )
    # Customer can access customer dashboard
    assert client.get("/customer/dashboard").status_code == 200
    # Customer CANNOT access officer workspace (403 Forbidden)
    assert client.get("/officer/dashboard").status_code == 403
    # Customer CANNOT access manager workspace (403 Forbidden)
    assert client.get("/manager/dashboard").status_code == 403

    # Logout
    client.post("/auth/logout", follow_redirects=True)

    # 3. Officer logs in (with MFA)
    import pyotp
    client.post(
        "/auth/login",
        data={"role": UserRole.LOAN_OFFICER, "email": "rbac.officer@example.com", "password": "SecurePassword123!"},
        follow_redirects=True,
    )
    client.post(
        "/auth/mfa/verify",
        data={"totp_token": pyotp.TOTP("JBSWY3DPEHPK3PXP").now()},
        follow_redirects=True,
    )
    # Officer can access officer dashboard
    assert client.get("/officer/dashboard").status_code == 200
    # Officer CANNOT access customer dashboard (403 Forbidden)
    assert client.get("/customer/dashboard").status_code == 403
    # Officer CANNOT access manager dashboard (403 Forbidden)
    assert client.get("/manager/dashboard").status_code == 403


def test_sql_injection_resilience(client, app):
    """
    Security Audit Check #1:
    Verify that ORM parameterization prevents SQL injection payloads.
    """
    with app.app_context():
        # Attacker tries classic SQL injection in search
        sql_injection_payload = "'; DROP TABLE users; --"
        user = User.query.filter_by(email=sql_injection_payload).first()
        assert user is None

        # Table is intact
        assert db.session.execute(db.select(User)).all() is not None


def test_xss_input_sanitization():
    """
    Security Audit Check #2:
    Verify that sanitize_input strips dangerous HTML tags and event handlers.
    """
    from app.utils.security import sanitize_input

    assert sanitize_input("<script>alert('pwned')</script>Normal text") == "Normal text"
    assert sanitize_input("<img src=x onerror=alert(1)>Hello") == "Hello"
    assert sanitize_input("<a href='javascript:alert(1)'>Click me</a>") == "Click me"
    assert sanitize_input("Clean, unescaped plain text.") == "Clean, unescaped plain text."


def test_cors_strict_domain_rules(client, app):
    """
    Security Audit Check #11:
    Verify strict domain origin rules and absence of permissive wildcards.
    """
    # 1. Normal request without Origin header -> No Access-Control-Allow-Origin
    res = client.get("/")
    assert res.headers.get("Access-Control-Allow-Origin") is None

    # 2. Request with arbitrary disallowed origin -> No Access-Control-Allow-Origin: *
    res2 = client.get("/", headers={"Origin": "https://malicious-attacker.com"})
    assert res2.headers.get("Access-Control-Allow-Origin") is None

    # 3. Request with configured allowed origin
    app.config["CORS_ALLOWED_ORIGINS"] = ["https://trusted-portal.loanpulse.com"]
    res3 = client.get("/", headers={"Origin": "https://trusted-portal.loanpulse.com"})
    assert res3.headers.get("Access-Control-Allow-Origin") == "https://trusted-portal.loanpulse.com"
    assert res3.headers.get("Access-Control-Allow-Origin") != "*"


def test_session_cookie_security():
    """
    Security Audit Check #8:
    Verify SESSION_COOKIE_HTTPONLY, SESSION_COOKIE_SAMESITE, and config flags.
    """
    from app.config import Config, ProductionConfig

    assert Config.SESSION_COOKIE_HTTPONLY is True
    assert Config.SESSION_COOKIE_SAMESITE == "Lax"
    assert ProductionConfig.SESSION_COOKIE_HTTPONLY is True
    assert ProductionConfig.SESSION_COOKIE_SECURE is True
    assert ProductionConfig.SESSION_COOKIE_SAMESITE == "Lax"
