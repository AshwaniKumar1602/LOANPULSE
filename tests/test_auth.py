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
