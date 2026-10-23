import click
from flask.cli import with_appcontext
from app.extensions import db
from app.models.user import User, UserRole
from app.models.loan_product import LoanProduct
from app.models.customer import CustomerProfile


@click.command("seed-production")
@with_appcontext
def seed_production_command():
    """
    Seeds essential configuration seeds ONLY:
    - Default active loan product types (Personal, Home, Auto, SME Business).
    Zero test users, zero fake applications, zero mock repayment records (Rule #1).
    """
    click.echo("Seeding production configuration...")

    default_products = [
        {
            "code": "PERSONAL_LOAN",
            "name": "Personal Prime Loan",
            "description": "Unsecured personal loan for medical, travel, consolidation, or lifestyle needs with rapid underwriting.",
            "min_amount": 1000.00,
            "max_amount": 50000.00,
            "min_tenure_months": 6,
            "max_tenure_months": 60,
            "base_interest_rate": 10.99,
            "min_credit_score": 640,
            "max_dti_ratio": 45.00,
            "is_active": True,
        },
        {
            "code": "HOME_LOAN",
            "name": "Residential Mortgage & Home Loan",
            "description": "Long-term secured residential mortgage for purchasing, constructing, or renovating real estate property.",
            "min_amount": 50000.00,
            "max_amount": 1500000.00,
            "min_tenure_months": 60,
            "max_tenure_months": 360,
            "base_interest_rate": 6.75,
            "min_credit_score": 680,
            "max_dti_ratio": 42.00,
            "is_active": True,
        },
        {
            "code": "AUTO_LOAN",
            "name": "Vehicle & Auto Finance",
            "description": "Fixed-rate auto financing for new and certified pre-owned passenger vehicles with flexible down payment options.",
            "min_amount": 5000.00,
            "max_amount": 100000.00,
            "min_tenure_months": 12,
            "max_tenure_months": 84,
            "base_interest_rate": 7.49,
            "min_credit_score": 620,
            "max_dti_ratio": 48.00,
            "is_active": True,
        },
        {
            "code": "SME_BUSINESS_LOAN",
            "name": "SME Commercial Growth Loan",
            "description": "Working capital, inventory financing, and expansion credit lines for small and medium-sized enterprises.",
            "min_amount": 25000.00,
            "max_amount": 500000.00,
            "min_tenure_months": 12,
            "max_tenure_months": 120,
            "base_interest_rate": 8.95,
            "min_credit_score": 660,
            "max_dti_ratio": 50.00,
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
