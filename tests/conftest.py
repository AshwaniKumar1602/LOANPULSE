import pytest
from app import create_app
from app.extensions import db
from app.models.loan_product import LoanProduct
from app.models.user import User, UserRole
from app.models.customer import CustomerProfile


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        db.create_all()

        # Seed essential active loan product for testing
        product = LoanProduct(
            code="PERSONAL_PRIME",
            name="Personal Prime Loan",
            min_amount=1000.00,
            max_amount=50000.00,
            min_tenure_months=6,
            max_tenure_months=60,
            base_interest_rate=10.00,
            min_credit_score=640,
            max_dti_ratio=45.00,
            is_active=True,
        )
        db.session.add(product)
        db.session.commit()

        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def runner(app):
    return app.test_cli_runner()
