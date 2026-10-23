from decimal import Decimal
import pyotp
import pytest
from app.extensions import db
from app.models.user import User, UserRole
from app.models.customer import CustomerProfile
from app.models.loan_product import LoanProduct
from app.services.calculator_service import (
    calculate_precise_emi,
    calculate_amortization_schedule_decimal,
)
from app.services.underwriting_engine import validate_product_eligibility
from cli.commands import seed_production_command


def create_manager(email="mgr.products@example.com", password="SecurePassword123!"):
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


def create_officer(email="off.products@example.com", password="SecurePassword123!"):
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


def create_customer(email="cust.products@example.com", password="SecurePassword123!"):
    user = User(
        email=email,
        first_name="Carla",
        last_name="Customer",
        role=UserRole.CUSTOMER,
        is_active=True,
    )
    user.set_password(password)
    profile = CustomerProfile(
        credit_score=720,
        annual_income=72000.0,
        monthly_debt=400.0,
        employment_type="SALARIED",
    )
    user.customer_profile = profile
    db.session.add(user)
    db.session.commit()
    return user


def login_manager(client, email="mgr.products@example.com", password="SecurePassword123!", totp_secret="JBSWY3DPEHPK3PXP"):
    client.post(
        "/auth/login",
        data={"email": email, "password": password, "role": UserRole.LOAN_MANAGER},
        follow_redirects=True,
    )
    token = pyotp.TOTP(totp_secret).now()
    client.post("/auth/mfa/verify", data={"totp_token": token}, follow_redirects=True)


# ------------------------------------------------------------------------------
# 1. Decimal EMI Arithmetic and Rounding Tests
# ------------------------------------------------------------------------------

def test_calculate_precise_emi_values():
    """Verifies reducing balance EMI calculation with exact Decimal precision."""
    # 1. Standard benchmark: $10,000 at 10% APR for 12 months = $879.16
    emi = calculate_precise_emi(10000, 10.0, 12)
    assert emi == Decimal("879.16")

    # 2. $25,000 at 9.5% APR for 36 months = $800.82
    emi2 = calculate_precise_emi(25000, 9.5, 36)
    assert emi2 == Decimal("800.82")

    # 3. 0% Interest Rate edge case = exact principal divided by tenure
    emi_zero_rate = calculate_precise_emi(12000, 0, 12)
    assert emi_zero_rate == Decimal("1000.00")

    # 4. Zero or negative principal/tenure returns Decimal("0.00")
    assert calculate_precise_emi(0, 10.0, 12) == Decimal("0.00")
    assert calculate_precise_emi(-5000, 10.0, 12) == Decimal("0.00")
    assert calculate_precise_emi(10000, 10.0, 0) == Decimal("0.00")


def test_amortization_schedule_decimal_final_installment_balancing():
    """
    Verifies that the amortization schedule correctly amortizes to 0.00 remaining balance
    and balances the last installment so that total principal paid matches original principal exactly.
    """
    principal = 25000.00
    rate = 9.5
    tenure = 36
    res = calculate_amortization_schedule_decimal(principal, rate, tenure)

    assert res["principal"] == "25000.00"
    assert res["tenure_months"] == 36
    assert len(res["schedule"]) == 36

    # Verify final installment closing balance is 0.00
    final_entry = res["schedule"][-1]
    assert final_entry["remaining_balance"] == "0.00"

    # Verify sum of all principal components equals initial principal exactly
    total_principal_paid = sum(Decimal(row["principal_component"]) for row in res["schedule"])
    assert total_principal_paid == Decimal("25000.00")

    # Verify total payment equals principal + total interest
    total_paid = Decimal(res["total_payment"])
    total_interest = Decimal(res["total_interest"])
    assert total_paid == Decimal("25000.00") + total_interest


def test_education_loan_moratorium_amortization():
    """Verifies education loan moratorium schedule where principal payments are deferred."""
    principal = 50000.00
    rate = 7.5
    tenure = 24
    moratorium = 6
    res = calculate_amortization_schedule_decimal(principal, rate, tenure, moratorium_months=moratorium)

    assert len(res["schedule"]) == 24
    # First 6 months are moratorium: principal payment is 0.00
    for i in range(moratorium):
        month_item = res["schedule"][i]
        assert month_item["is_moratorium"] is True
        assert Decimal(month_item["principal_component"]) == Decimal("0.00")
        assert Decimal(month_item["remaining_balance"]) == Decimal("50000.00")

    # Final month closing balance is 0.00
    assert res["schedule"][-1]["remaining_balance"] == "0.00"


# ------------------------------------------------------------------------------
# 2. Production Seeding and Configured Loan Types Tests
# ------------------------------------------------------------------------------

def test_production_seed_command_creates_default_products(app, runner):
    """
    Verifies seed-production seeds the 4 required institutional products
    plus the legacy product, with zero dummy users or mock records.
    """
    with app.app_context():
        # Clean current products to test fresh seeding
        LoanProduct.query.delete()
        db.session.commit()

        result = runner.invoke(seed_production_command)
        assert result.exit_code == 0
        assert "Seeding production configuration..." in result.output

        # Verify 4 institutional loan products
        personal = LoanProduct.query.filter_by(code="PERSONAL_LOAN").first()
        assert personal is not None
        assert personal.secured is False
        assert float(personal.min_amount) == 1000.00
        assert float(personal.max_amount) == 50000.00
        assert personal.loan_category == "PERSONAL"

        car = LoanProduct.query.filter_by(code="CAR_VEHICLE_LOAN").first()
        assert car is not None
        assert car.secured is True
        assert car.max_tenure_months == 84  # 7 years max
        assert float(car.base_interest_rate) == 6.99
        assert car.loan_category == "VEHICLE"

        health = LoanProduct.query.filter_by(code="HEALTH_MEDICAL_LOAN").first()
        assert health is not None
        assert health.secured is False
        assert health.processing_speed == "INSTANT"
        assert health.loan_category == "MEDICAL"

        edu = LoanProduct.query.filter_by(code="EDUCATION_LOAN").first()
        assert edu is not None
        assert edu.moratorium_months == 12
        assert edu.max_tenure_months == 120
        assert edu.loan_category == "EDUCATION"

        # Verify legacy compatibility product
        legacy = LoanProduct.query.filter_by(code="PERSONAL_PRIME").first()
        assert legacy is not None

        # Verify idempotence: re-running seed command does not raise duplicate error
        result2 = runner.invoke(seed_production_command)
        assert result2.exit_code == 0


# ------------------------------------------------------------------------------
# 3. Manager Product Lifecycle (Create, Edit, Toggle Status)
# ------------------------------------------------------------------------------

def test_manager_product_lifecycle(client, app):
    """Verifies manager can create, edit, and toggle active status of loan products."""
    with app.app_context():
        mgr, secret = create_manager("mgr.crud@example.com")

    login_manager(client, "mgr.crud@example.com", totp_secret=secret)

    # 1. View product list
    resp = client.get("/manager/products")
    assert resp.status_code == 200
    assert b"Credit Products" in resp.data

    # 2. Create new product
    create_payload = {
        "code": "GREEN_ENERGY_LOAN",
        "name": "Green Solar and Clean Energy Loan",
        "description": "Eco-friendly financing for residential solar panels and batteries.",
        "loan_category": "PERSONAL",
        "min_amount": "2000.00",
        "max_amount": "40000.00",
        "min_tenure_months": "12",
        "max_tenure_months": "60",
        "base_interest_rate": "6.50",
        "min_credit_score": "660",
        "max_dti_ratio": "45.00",
        "min_income_required": "2800.00",
        "secured": "y",
        "moratorium_months": "0",
        "processing_speed": "STANDARD",
        "is_active": "y",
    }
    create_resp = client.post("/manager/products/create", data=create_payload, follow_redirects=True)
    assert create_resp.status_code == 200
    assert b"created successfully" in create_resp.data

    with app.app_context():
        p = LoanProduct.query.filter_by(code="GREEN_ENERGY_LOAN").first()
        assert p is not None
        assert p.name == "Green Solar and Clean Energy Loan"
        assert p.secured is True
        assert p.min_income_required == 2800.00
        prod_id = p.id

    # 3. Edit product
    edit_payload = {
        "name": "Green Solar Premium Loan",
        "description": "Updated description with lower promotional rate.",
        "loan_category": "PERSONAL",
        "min_amount": "2000.00",
        "max_amount": "50000.00",
        "min_tenure_months": "12",
        "max_tenure_months": "72",
        "base_interest_rate": "5.99",
        "min_credit_score": "670",
        "max_dti_ratio": "40.00",
        "min_income_required": "3000.00",
        "secured": "y",
        "moratorium_months": "0",
        "processing_speed": "EXPRESS",
        "is_active": "y",
    }
    edit_resp = client.post(f"/manager/products/{prod_id}/edit", data=edit_payload, follow_redirects=True)
    assert edit_resp.status_code == 200
    assert b"updated successfully" in edit_resp.data

    with app.app_context():
        updated_p = db.session.get(LoanProduct, prod_id)
        assert updated_p.name == "Green Solar Premium Loan"
        assert float(updated_p.base_interest_rate) == 5.99
        assert float(updated_p.max_amount) == 50000.00

    # 4. Toggle status to deactivated
    toggle_resp = client.post(f"/manager/products/{prod_id}/toggle-status", follow_redirects=True)
    assert toggle_resp.status_code == 200
    assert b"has been deactivated" in toggle_resp.data

    with app.app_context():
        toggled_p = db.session.get(LoanProduct, prod_id)
        assert toggled_p.is_active is False

    # 5. Toggle status back to activated
    toggle_resp2 = client.post(f"/manager/products/{prod_id}/toggle-status", follow_redirects=True)
    assert toggle_resp2.status_code == 200
    assert b"has been activated" in toggle_resp2.data

    with app.app_context():
        toggled_p2 = db.session.get(LoanProduct, prod_id)
        assert toggled_p2.is_active is True


def test_manager_product_validation_errors(client, app):
    """Verifies cross-field range validation rejects invalid limits and tenure."""
    with app.app_context():
        mgr, secret = create_manager("mgr.validation@example.com")

    login_manager(client, "mgr.validation@example.com", totp_secret=secret)

    # Max amount less than min amount
    invalid_amount_payload = {
        "code": "INVALID_AMOUNT",
        "name": "Invalid Amount Product",
        "loan_category": "PERSONAL",
        "min_amount": "50000.00",
        "max_amount": "10000.00",  # max < min
        "min_tenure_months": "12",
        "max_tenure_months": "36",
        "base_interest_rate": "8.50",
        "min_credit_score": "600",
        "max_dti_ratio": "45.00",
        "min_income_required": "2000.00",
        "is_active": "y",
    }
    resp1 = client.post("/manager/products/create", data=invalid_amount_payload, follow_redirects=True)
    assert resp1.status_code == 200
    assert b"Maximum loan amount must be greater than or equal to minimum amount" in resp1.data

    # Max tenure less than min tenure
    invalid_tenure_payload = {
        "code": "INVALID_TENURE",
        "name": "Invalid Tenure Product",
        "loan_category": "PERSONAL",
        "min_amount": "1000.00",
        "max_amount": "10000.00",
        "min_tenure_months": "48",
        "max_tenure_months": "24",  # max < min
        "base_interest_rate": "8.50",
        "min_credit_score": "600",
        "max_dti_ratio": "45.00",
        "min_income_required": "2000.00",
        "is_active": "y",
    }
    resp2 = client.post("/manager/products/create", data=invalid_tenure_payload, follow_redirects=True)
    assert resp2.status_code == 200
    assert b"Maximum tenure must be greater than or equal to minimum tenure" in resp2.data


# ------------------------------------------------------------------------------
# 4. Read-Only Catalogue Access and Non-Manager RBAC
# ------------------------------------------------------------------------------

def test_read_only_catalogue_access_by_roles(client, app):
    """
    Verifies that prospective borrowers, customers, and loan officers can access
    the read-only catalogue /products, but non-managers cannot access manager endpoints.
    """
    with app.app_context():
        create_customer("customer.cat@example.com")
        create_officer("officer.cat@example.com")

    # 1. Unauthenticated guest can access /products
    guest_resp = client.get("/products")
    assert guest_resp.status_code == 200
    assert b"Institutional Loan Product Offerings" in guest_resp.data

    # 2. Customer can access /products
    client.post(
        "/auth/login",
        data={"email": "customer.cat@example.com", "password": "SecurePassword123!", "role": UserRole.CUSTOMER},
        follow_redirects=True,
    )
    cust_cat_resp = client.get("/products")
    assert cust_cat_resp.status_code == 200
    assert b"Institutional Loan Product Offerings" in cust_cat_resp.data

    # 3. Customer blocked from manager product endpoints (403 Forbidden)
    cust_mgr_resp = client.get("/manager/products")
    assert cust_mgr_resp.status_code == 403
    cust_create_resp = client.get("/manager/products/create")
    assert cust_create_resp.status_code == 403

    client.post("/auth/logout", follow_redirects=True)

    # 4. Loan Officer can access /products
    client.post(
        "/auth/login",
        data={"email": "officer.cat@example.com", "password": "SecurePassword123!", "role": UserRole.LOAN_OFFICER},
        follow_redirects=True,
    )
    token = pyotp.TOTP("JBSWY3DPEHPK3PXP").now()
    client.post("/auth/mfa/verify", data={"totp_token": token}, follow_redirects=True)

    off_cat_resp = client.get("/products")
    assert off_cat_resp.status_code == 200

    # Officer blocked from manager product create/edit/toggle
    off_mgr_resp = client.get("/manager/products")
    assert off_mgr_resp.status_code == 403


# ------------------------------------------------------------------------------
# 5. Rule Engine Eligibility Validation (Service & API)
# ------------------------------------------------------------------------------

def test_server_side_eligibility_validation_service(app):
    """Tests validate_product_eligibility rule engine against limits, income, and DTI."""
    with app.app_context():
        product = LoanProduct.query.filter_by(code="PERSONAL_PRIME").first()
        product.min_income_required = 3000.00
        db.session.commit()

        # 1. Fully eligible applicant
        res_eligible = validate_product_eligibility(
            product=product,
            requested_amount=15000.00,
            tenure_months=36,
            monthly_income=6000.00,
            existing_debt=500.00,
            credit_score=750,
        )
        assert res_eligible["is_eligible"] is True
        assert len(res_eligible["reasons"]) == 0
        assert res_eligible["estimated_emi"] > 0

        # 2. Exceeds max amount
        res_high_amount = validate_product_eligibility(
            product=product,
            requested_amount=80000.00,  # max is 50000
            tenure_months=36,
            monthly_income=6000.00,
            existing_debt=500.00,
            credit_score=750,
        )
        assert res_high_amount["is_eligible"] is False
        assert any("Requested amount" in r for r in res_high_amount["reasons"])

        # 3. Insufficient monthly income
        res_low_income = validate_product_eligibility(
            product=product,
            requested_amount=10000.00,
            tenure_months=36,
            monthly_income=2000.00,  # min required is 3000
            existing_debt=200.00,
            credit_score=750,
        )
        assert res_low_income["is_eligible"] is False
        assert any("Monthly income" in r for r in res_low_income["reasons"])

        # 4. Excessive DTI ratio
        res_high_dti = validate_product_eligibility(
            product=product,
            requested_amount=40000.00,
            tenure_months=24,
            monthly_income=3200.00,
            existing_debt=1400.00,  # high debt creates high DTI
            credit_score=750,
        )
        assert res_high_dti["is_eligible"] is False
        assert any("DTI ratio" in r for r in res_high_dti["reasons"])


def test_api_eligibility_check_endpoint(client, app):
    """Tests POST /api/eligibility/check JSON endpoint."""
    with app.app_context():
        product = LoanProduct.query.filter_by(code="PERSONAL_PRIME").first()
        prod_id = product.id

    # 1. Eligible check
    payload = {
        "product_id": prod_id,
        "requested_amount": 12000,
        "tenure_months": 24,
        "monthly_income": 5000,
        "existing_debt": 300,
        "credit_score": 700,
    }
    resp = client.post("/api/eligibility/check", json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["is_eligible"] is True
    assert "estimated_emi" in data
    assert "dti_ratio" in data

    # 2. Product not found returns 404
    resp_404 = client.post("/api/eligibility/check", json={"product_id": 99999})
    assert resp_404.status_code == 404

    # 3. Invalid parameters return 400
    resp_400 = client.post("/api/eligibility/check", json={"product_id": prod_id, "requested_amount": -500})
    assert resp_400.status_code == 400


# ------------------------------------------------------------------------------
# 6. EMI Calculator API Endpoints
# ------------------------------------------------------------------------------

def test_api_calculator_compute(client, app):
    """Tests GET and POST /api/calculator and /api/calculator/compute endpoints."""
    # 1. GET request with query args
    get_resp = client.get("/api/calculator/compute?amount=25000&interest_rate=9.5&tenure_months=36")
    assert get_resp.status_code == 200
    get_data = get_resp.get_json()
    assert get_data["monthly_emi"] == 800.82
    assert get_data["total_payment"] > 25000.00
    assert len(get_data["schedule"]) == 36

    # 2. POST request with JSON
    post_payload = {
        "principal": 10000,
        "interest_rate": 10.0,
        "tenure_months": 12,
    }
    post_resp = client.post("/api/calculator", json=post_payload)
    assert post_resp.status_code == 200
    post_data = post_resp.get_json()
    assert post_data["monthly_emi"] == 879.16

    # 3. Pre-filling rate from product_id
    with app.app_context():
        p = LoanProduct.query.filter_by(code="PERSONAL_PRIME").first()
        prod_id = p.id

    preset_resp = client.post("/api/calculator/compute", json={"amount": 10000, "tenure": 12, "product_id": prod_id})
    assert preset_resp.status_code == 200
    assert preset_resp.get_json()["monthly_emi"] == 879.16

    # 4. Invalid input validation
    err_resp = client.post("/api/calculator/compute", json={"amount": -100, "tenure": 12, "interest_rate": 10})
    assert err_resp.status_code == 400
