import os
import stat
import importlib.util
from app.extensions import db
from app.models.user import User, UserRole
from app.models.loan_product import LoanProduct
from cli.commands import create_initial_products_command, create_staff_command, seed_production_command


def test_gunicorn_free_tier_configuration():
    """
    Phase 10: Verify gunicorn.conf.py enforces memory-optimized settings for Render free tier.
    workers=2, threads=2, max_requests=1000, max_requests_jitter=50.
    """
    gunicorn_path = os.path.abspath("gunicorn.conf.py")
    assert os.path.exists(gunicorn_path), "gunicorn.conf.py must exist in project root"

    spec = importlib.util.spec_from_file_location("gunicorn_conf", gunicorn_path)
    gunicorn_conf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gunicorn_conf)

    assert gunicorn_conf.workers == 2
    assert gunicorn_conf.threads == 2
    assert gunicorn_conf.worker_class == "gthread"
    assert gunicorn_conf.max_requests == 1000
    assert gunicorn_conf.max_requests_jitter == 50
    assert gunicorn_conf.server_tokens == "None"


def test_build_and_render_yaml_configuration():
    """
    Phase 10: Verify build.sh is executable and render.yaml has proper deployment instructions.
    """
    # 1. build.sh
    build_path = os.path.abspath("build.sh")
    assert os.path.exists(build_path), "build.sh must exist"
    mode = os.stat(build_path).st_mode
    assert bool(mode & stat.S_IXUSR), "build.sh must be marked executable (chmod +x)"

    with open(build_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "flask db upgrade" in content
    assert "flask create-initial-products" in content

    # 2. render.yaml
    render_path = os.path.abspath("render.yaml")
    assert os.path.exists(render_path), "render.yaml must exist"
    with open(render_path, "r", encoding="utf-8") as f:
        render_content = f.read()
    assert "buildCommand: \"./build.sh\"" in render_content or "buildCommand: ./build.sh" in render_content
    assert "startCommand: \"gunicorn -c gunicorn.conf.py wsgi:app\"" in render_content or "startCommand: gunicorn -c gunicorn.conf.py wsgi:app" in render_content
    assert "FLASK_ENV" in render_content
    assert "production" in render_content


def test_create_initial_products_cli(runner, app):
    """
    Phase 10: Verify 'flask create-initial-products' provisions initial institutional INR loan products.
    """
    with app.app_context():
        # Clear existing products to test fresh seed
        LoanProduct.query.delete()
        db.session.commit()

        res = runner.invoke(create_initial_products_command)
        assert res.exit_code == 0
        assert "Seeding production configuration..." in res.output

        # Verify products were created
        assert LoanProduct.query.count() >= 4
        personal = LoanProduct.query.filter_by(code="PERSONAL_LOAN").first()
        assert personal is not None
        assert personal.is_active is True

        # Verify idempotence
        res2 = runner.invoke(create_initial_products_command)
        assert res2.exit_code == 0


def test_create_staff_cli(runner, app):
    """
    Phase 10: Verify 'flask create-staff' provisions a staff user securely via CLI with no test users.
    """
    with app.app_context():
        # Clean specific test user if exists
        User.query.filter_by(email="production.officer@loanpulse.com").delete()
        db.session.commit()

        res = runner.invoke(
            create_staff_command,
            args=[
                "--email", "production.officer@loanpulse.com",
                "--first-name", "Pooja",
                "--last-name", "Sharma",
                "--role", UserRole.LOAN_OFFICER,
                "--password", "StrongProdPass2026!",
            ],
        )
        assert res.exit_code == 0
        assert "Staff member production.officer@loanpulse.com created" in res.output

        # Verify user in database
        staff = User.query.filter_by(email="production.officer@loanpulse.com").first()
        assert staff is not None
        assert staff.role == UserRole.LOAN_OFFICER
        assert staff.check_password("StrongProdPass2026!") is True
        assert staff.check_password("WrongPassword") is False
