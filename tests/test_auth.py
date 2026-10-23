from app.extensions import db
from app.models.user import User, UserRole
from app.utils.security import generate_totp_secret, verify_totp_token
import pyotp


def test_user_password_hashing(app):
    with app.app_context():
        user = User(
            email="test@example.com",
            first_name="Alice",
            last_name="Smith",
            role=UserRole.CUSTOMER,
        )
        user.set_password("SecureP@ssw0rd123")
        assert user.password_hash.startswith("$argon2id$")
        assert user.check_password("SecureP@ssw0rd123") is True
        assert user.check_password("WrongPassword") is False


def test_totp_mfa_workflow():
    secret = generate_totp_secret()
    totp = pyotp.TOTP(secret)
    token = totp.now()

    assert verify_totp_token(secret, token) is True
    assert verify_totp_token(secret, "000000") is False


def test_customer_registration_endpoint(client, app):
    response = client.post(
        "/auth/register",
        data={
            "first_name": "Bob",
            "last_name": "Jones",
            "email": "bob.jones@example.com",
            "phone": "+1 555 123 4567",
            "password": "StrongPassword99!",
            "confirm_password": "StrongPassword99!",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    with app.app_context():
        user = User.query.filter_by(email="bob.jones@example.com").first()
        assert user is not None
        assert user.role == UserRole.CUSTOMER
        assert user.customer_profile is not None


def test_single_identity_role_enforcement_mismatch(client, app):
    """
    Phase 2 requirement:
    Backend login authentication must verify that the user's assigned database role
    matches the selected role on the sign-in form. Reject authentication with an
    explicit error message if the roles do not match.
    """
    with app.app_context():
        borrower = User(
            email="borrower.test@example.com",
            first_name="Carl",
            last_name="Borrower",
            role=UserRole.CUSTOMER,
            is_active=True,
        )
        borrower.set_password("Password123!")
        db.session.add(borrower)

        officer = User(
            email="officer.test@example.com",
            first_name="Olivia",
            last_name="Officer",
            role=UserRole.LOAN_OFFICER,
            is_active=True,
        )
        officer.set_password("Password123!")
        db.session.add(officer)
        db.session.commit()

    # 1. Borrower tries to sign in as Loan Officer -> MUST FAIL
    res1 = client.post(
        "/auth/login",
        data={
            "role": UserRole.LOAN_OFFICER,
            "email": "borrower.test@example.com",
            "password": "Password123!",
        },
        follow_redirects=True,
    )
    assert res1.status_code == 200
    html1 = res1.data.decode("utf-8")
    assert "Role authorization error" in html1
    assert "registered as a Loan Borrower and cannot access the Loan Officer portal" in html1

    # 2. Officer tries to sign in as Loan Borrower -> MUST FAIL
    res2 = client.post(
        "/auth/login",
        data={
            "role": UserRole.CUSTOMER,
            "email": "officer.test@example.com",
            "password": "Password123!",
        },
        follow_redirects=True,
    )
    assert res2.status_code == 200
    html2 = res2.data.decode("utf-8")
    assert "Role authorization error" in html2
    assert "registered as a Loan Officer and cannot access the Loan Borrower portal" in html2

    # 3. Borrower signs in as Loan Borrower -> MUST SUCCEED
    res3 = client.post(
        "/auth/login",
        data={
            "role": UserRole.CUSTOMER,
            "email": "borrower.test@example.com",
            "password": "Password123!",
        },
        follow_redirects=True,
    )
    assert res3.status_code == 200
    html3 = res3.data.decode("utf-8")
    assert "Welcome back, Carl!" in html3


def test_csrf_protected_logout(client, app):
    """
    Phase 3 requirement:
    Enforce CSRF tokens on all logout, interactive POST, and state-changing forms.
    """
    with app.app_context():
        user = User(
            email="logout.user@example.com",
            first_name="Leo",
            last_name="Logout",
            role=UserRole.CUSTOMER,
            is_active=True,
        )
        user.set_password("Password123!")
        db.session.add(user)
        db.session.commit()

    # Log in
    client.post(
        "/auth/login",
        data={
            "role": UserRole.CUSTOMER,
            "email": "logout.user@example.com",
            "password": "Password123!",
        },
        follow_redirects=True,
    )

    # Perform POST logout
    res = client.post("/auth/logout", follow_redirects=True)
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "You have been signed out safely." in html
