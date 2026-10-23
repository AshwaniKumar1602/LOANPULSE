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
