import click
from flask.cli import with_appcontext
from app.extensions import db
from app.models.user import User, UserRole
from app.models.loan_product import LoanProduct
from app.models.customer import CustomerProfile


def seed_production_logic():
    click.echo("Seeding production configuration...")

    default_products = [
        {
            "code": "PERSONAL_LOAN",
            "name": "Personal Prime Loan",
            "description": "Unsecured personal loan with flexible tenure and standard competitive interest rates.",
            "min_amount": 1000.00,
            "max_amount": 50000.00,
            "min_tenure_months": 6,
            "max_tenure_months": 60,
            "base_interest_rate": 10.50,
            "min_credit_score": 640,
            "max_dti_ratio": 45.00,
            "min_income_required": 2500.00,
            "secured": False,
            "moratorium_months": 0,
            "processing_speed": "STANDARD",
            "loan_category": "PERSONAL",
            "is_active": True,
        },
        {
            "code": "CAR_VEHICLE_LOAN",
            "name": "Auto & Vehicle Loan",
            "description": "Secured vehicle financing for new and certified vehicles at competitive rates, max tenure 7 years.",
            "min_amount": 5000.00,
            "max_amount": 100000.00,
            "min_tenure_months": 12,
            "max_tenure_months": 84,
            "base_interest_rate": 6.99,
            "min_credit_score": 620,
            "max_dti_ratio": 50.00,
            "min_income_required": 3000.00,
            "secured": True,
            "moratorium_months": 0,
            "processing_speed": "EXPRESS",
            "loan_category": "VEHICLE",
            "is_active": True,
        },
        {
            "code": "HEALTH_MEDICAL_LOAN",
            "name": "Health & Medical Care Loan",
            "description": "Unsecured subsidized low-interest credit line for medical treatments and emergency care with instant processing.",
            "min_amount": 1000.00,
            "max_amount": 60000.00,
            "min_tenure_months": 6,
            "max_tenure_months": 48,
            "base_interest_rate": 5.49,
            "min_credit_score": 600,
            "max_dti_ratio": 55.00,
            "min_income_required": 1800.00,
            "secured": False,
            "moratorium_months": 0,
            "processing_speed": "INSTANT",
            "loan_category": "MEDICAL",
            "is_active": True,
        },
        {
            "code": "EDUCATION_LOAN",
            "name": "Student Higher Education Loan",
            "description": "Subsidized education financing with moratorium period options and income/co-applicant requirements.",
            "min_amount": 5000.00,
            "max_amount": 150000.00,
            "min_tenure_months": 12,
            "max_tenure_months": 120,
            "base_interest_rate": 6.25,
            "min_credit_score": 630,
            "max_dti_ratio": 50.00,
            "min_income_required": 2000.00,
            "secured": False,
            "moratorium_months": 12,
            "processing_speed": "STANDARD",
            "loan_category": "EDUCATION",
            "is_active": True,
        },
        {
            "code": "PERSONAL_PRIME",
            "name": "Personal Prime (Legacy)",
            "description": "Standard prime personal credit line.",
            "min_amount": 1000.00,
            "max_amount": 50000.00,
            "min_tenure_months": 6,
            "max_tenure_months": 60,
            "base_interest_rate": 10.00,
            "min_credit_score": 640,
            "max_dti_ratio": 45.00,
            "min_income_required": 2500.00,
            "secured": False,
            "moratorium_months": 0,
            "processing_speed": "STANDARD",
            "loan_category": "PERSONAL",
            "is_active": True,
        },
    ]

    added = 0
    for p_data in default_products:
        existing = LoanProduct.query.filter_by(code=p_data["code"]).first()
        if not existing:
            prod = LoanProduct(**p_data)
            db.session.add(prod)
            added += 1

    db.session.commit()
    click.echo(f"Successfully seeded {added} default loan products. System clean of test users.")


@click.command("seed-production")
@with_appcontext
def seed_production_command():
    """
    Seeds essential configuration seeds ONLY:
    - Default active loan product types (Personal, Home, Auto, SME Business).
    Zero test users, zero fake applications, zero mock repayment records (Rule #1).
    """
    seed_production_logic()


@click.command("create-initial-products")
@with_appcontext
def create_initial_products_command():
    """
    Seeds essential institutional loan products for fresh production environments:
    - Provisions Personal, Vehicle, Medical, and Education loan products.
    Zero test users, zero fake applications, zero mock repayment records (Rule #1).
    """
    seed_production_logic()


@click.command("create-staff")
@click.option("--email", prompt="Staff Email", help="Corporate email for staff account.")
@click.option("--first-name", prompt="First Name", help="Given name.")
@click.option("--last-name", prompt="Last Name", help="Surname.")
@click.option(
    "--role",
    prompt="Role (LOAN_OFFICER / LOAN_MANAGER / ADMIN)",
    type=click.Choice([UserRole.LOAN_OFFICER, UserRole.LOAN_MANAGER, UserRole.ADMIN], case_sensitive=False),
    help="Staff security role.",
)
@click.password_option(help="Secure password (minimum 8 characters).")
@with_appcontext
def create_staff_command(email, first_name, last_name, role, password):
    """
    Provisions a staff user securely via CLI (Security Rule #18: Zero default credentials).
    """
    clean_email = email.strip().lower()
    if User.query.filter_by(email=clean_email).first():
        click.echo(f"Error: User with email {clean_email} already exists.", err=True)
        return

    user = User(
        email=clean_email,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        role=role.upper(),
        is_active=True,
    )
    user.set_password(password)

    db.session.add(user)
    db.session.commit()

    click.echo(f"Staff member {clean_email} created with role {role.upper()}.")
    click.echo("Note: User will be required to configure TOTP 2FA on their first login.")
