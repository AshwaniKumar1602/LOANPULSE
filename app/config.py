import os
import secrets
from datetime import timedelta
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Base Configuration with Security and Render Optimization."""

    # 1. Secret Key Management & Entropy Verification (Security Rule #7)
    SECRET_KEY = os.getenv("SECRET_KEY")
    if not SECRET_KEY:
        # In strict production environments, missing SECRET_KEY is a fatal security error
        if os.getenv("FLASK_ENV") == "production":
            raise RuntimeError(
                "CRITICAL SECURITY CONFIGURATION ERROR: SECRET_KEY environment variable is missing! "
                "Must be a high-entropy secret (min 32 bytes)."
            )
        # Fallback for development if not provided
        SECRET_KEY = secrets.token_hex(32)

    if len(SECRET_KEY) < 32 and os.getenv("FLASK_ENV") == "production":
        raise RuntimeError(
            "CRITICAL SECURITY CONFIGURATION ERROR: SECRET_KEY must have at least 32 characters (256-bit entropy)."
        )

    # 2. Database & Connection Pooling (Rule #2 & #5)
    raw_db_url = os.getenv("DATABASE_URL", "sqlite:///loanpulse_dev.db")
    if raw_db_url.startswith("postgres://"):
        raw_db_url = raw_db_url.replace("postgres://", "postgresql://", 1)
    
    SQLALCHEMY_DATABASE_URI = raw_db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Connection pooling settings optimized for Render free-tier and Neon PostgreSQL
    is_postgres = "postgresql" in SQLALCHEMY_DATABASE_URI
    if is_postgres:
        SQLALCHEMY_ENGINE_OPTIONS = {
            "pool_size": int(os.getenv("DB_POOL_SIZE", "5")),
            "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "2")),
            "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", "300")),
            "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", "30")),
            "pool_pre_ping": True,
            "connect_args": {"sslmode": "require"} if "sslmode=" not in SQLALCHEMY_DATABASE_URI else {},
        }
    else:
        # Local SQLite fallback for testing/dev
        SQLALCHEMY_ENGINE_OPTIONS = {
            "pool_pre_ping": True,
        }

    # 3. Session & Cookie Security (Security Rule #12)
    SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "loanpulse_session")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "False").lower() in ("true", "1", "t")
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    PERMANENT_SESSION_LIFETIME = timedelta(
        seconds=int(os.getenv("PERMANENT_SESSION_LIFETIME", "7200"))
    )

    # 4. File Upload Configuration (Security Rule #4)
    UPLOAD_FOLDER = os.path.abspath(os.getenv("UPLOAD_FOLDER", "uploads"))
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", str(5 * 1024 * 1024)))  # 5MB max
    ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}

    # 5. Rate Limiting (Security Rule #6)
    RATELIMIT_DEFAULT = os.getenv("RATELIMIT_DEFAULT", "200/day;50/hour")
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_STRATEGY = "fixed-window"
    RATELIMIT_HEADERS_ENABLED = True

    # 6. CSRF & Form Security (Security Rule #3)
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600

    # 7. Quality & Debug Settings (Security Rule #17)
    DEBUG = False
    TESTING = False


class DevelopmentConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = False


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True


class TestingConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SESSION_COOKIE_SECURE = False
    RATELIMIT_ENABLED = False
    UPLOAD_FOLDER = "/tmp/loanpulse_test_uploads"


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}
