import pyotp
from app.extensions import db
from app.models.loan_product import LoanProduct
from app.models.user import User, UserRole


def test_index_page_capabilities_and_cta(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.data.decode("utf-8")

    # Check 4 Core System Capabilities
    assert "Loan Processing" in html
    assert "Eligibility Calculator" in html
    assert "Application Tracking" in html
    assert "Automated Notifications" in html

    # Check server-rendered CTAs for registration and login
    assert "/auth/register" in html
    assert "/auth/login" in html
    assert "/calculator" in html

    # Zero hardcoded mock credentials on landing page
    assert "admin@example.com" not in html
    assert "password123" not in html.lower()
    assert "demo user" not in html.lower()


def test_login_persona_tab_selector(client):
    response = client.get("/auth/login")
    assert response.status_code == 200
    html = response.data.decode("utf-8")

    # Check that 3 personas are presented
    assert "Borrower" in html
    assert "Loan Officer" in html
    assert "Loan Manager" in html
    assert "persona-tab" in html
    assert "selectPersona" in html

    # Zero mock test credentials prefilled or suggested
    assert "demo" not in html.lower()
    assert "testuser" not in html.lower()


def test_navbar_role_aware_shell(client, app):
    """
    Phase 3 requirement:
    Responsive navbar aware of user roles with active indicators and CSRF-protected logout.
    """
    totp_secret = "JBSWY3DPEHPK3PXP"
    with app.app_context():
        officer = User(
            email="nav.officer@example.com",
            first_name="Nina",
            last_name="Nav",
            role=UserRole.LOAN_OFFICER,
            is_active=True,
            totp_enabled=True,
            totp_secret=totp_secret,
        )
        officer.set_password("Password123!")
        db.session.add(officer)
        db.session.commit()

    # Log in as officer
    client.post(
        "/auth/login",
        data={
            "role": UserRole.LOAN_OFFICER,
            "email": "nav.officer@example.com",
            "password": "Password123!",
        },
        follow_redirects=True,
    )

    # Complete 2FA verification step
    token = pyotp.TOTP(totp_secret).now()
    client.post(
        "/auth/mfa/verify",
        data={"totp_token": token},
        follow_redirects=True,
    )

    # Inspect officer dashboard navbar
    res = client.get("/officer/dashboard")
    assert res.status_code == 200
    html = res.data.decode("utf-8")

    # Check officer-specific workspace links & CSRF logout form
    assert "Underwriting Queue" in html
    assert 'action="/auth/logout"' in html
    assert 'name="csrf_token"' in html
    assert "user-dropdown-menu" in html


def test_calculator_page_render(client):
    response = client.get("/calculator")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "Equated Monthly Installment (EMI) Calculator" in html
    assert "calc-amount" in html


def test_ui_components_macro_import(app):
    with app.test_request_context():
        from flask import render_template_string
        template_str = """
        {% import 'components/ui_components.html' as ui %}
        {{ ui.button('Apply Now', variant='primary', size='md') }}
        {{ ui.stat_card('Active Volume', '$25,000', subtitle='1 active loan') }}
        """
        rendered = render_template_string(template_str)
        assert "Apply Now" in rendered
        assert "Active Volume" in rendered
        assert "$25,000" in rendered
        assert "bg-amber-500" in rendered
