import os
from datetime import datetime, timezone
from flask import Flask, render_template, request, jsonify
from app.config import config_by_name
from app.extensions import db, migrate, login_manager, csrf, limiter
from app.models.user import User, UserRole
from app.models.notification import Notification


def create_app(config_name=None):
    """
    Application Factory for LoanPulse (LoanMaster).
    Enforces production security defaults and Render free-tier connection recycling.
    """
    if config_name is None:
        config_name = os.getenv("FLASK_ENV", "development").lower()

    app = Flask(__name__)
    config_cls = config_by_name.get(config_name, config_by_name["default"])
    app.config.from_object(config_cls)

    # Initialize Flask extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    # Flask-Login user loader
    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # Render Optimization (Rule #2): Explicitly remove db session to prevent connection pool leaks
    @app.teardown_appcontext
    def teardown_db_context(exception=None):
        db.session.remove()

    # Register blueprints
    from app.routes.main import main_bp
    from app.routes.auth import auth_bp
    from app.routes.customer import customer_bp
    from app.routes.officer import officer_bp
    from app.routes.manager import manager_bp
    from app.routes.api import api_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(customer_bp)
    app.register_blueprint(officer_bp)
    app.register_blueprint(manager_bp)
    app.register_blueprint(api_bp)

    # Register CLI commands
    from cli.commands import seed_production_command, create_staff_command

    app.cli.add_command(seed_production_command)
    app.cli.add_command(create_staff_command)

    # Security Headers Middleware (Security Rules #1, #2, #11, #12, #17)
    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        
        # Disable server signature banner
        response.headers.pop("Server", None)

        # Content-Security-Policy (allows Tailwind, FontAwesome icons, fonts, and inline styles for charts/tokens)
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
            "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self'; "
            "frame-ancestors 'self';"
        )
        response.headers["Content-Security-Policy"] = csp
        return response

    # Global Template Context Processor
    @app.context_processor
    def inject_global_vars():
        from flask_login import current_user
        unread_notifs_count = 0
        if current_user.is_authenticated:
            try:
                unread_notifs_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
            except Exception:
                unread_notifs_count = 0

        return {
            "current_year": datetime.now(timezone.utc).year,
            "UserRole": UserRole,
            "unread_notifs_count": unread_notifs_count,
        }

    # Error Handlers
    @app.errorhandler(400)
    def bad_request_error(e):
        return render_template("errors/400.html"), 400

    @app.errorhandler(403)
    def forbidden_error(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found_error(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(429)
    def ratelimit_handler(e):
        return render_template("errors/429.html"), 429

    @app.errorhandler(500)
    def internal_server_error(e):
        db.session.rollback()
        return render_template("errors/500.html"), 500

    return app
