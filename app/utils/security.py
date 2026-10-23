import base64
import io
import re
import pyotp
import qrcode
import bleach
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

ph = PasswordHasher()


def hash_password(password: str) -> str:
    """Argon2id password hashing (Security Rule #9)."""
    return ph.hash(password)


def verify_password(hashed: str, candidate: str) -> bool:
    """Argon2id password verification."""
    try:
        return ph.verify(hashed, candidate)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def generate_totp_secret() -> str:
    """Generates standard Base32 TOTP secret (Security Rule #10)."""
    return pyotp.random_base32()


def get_totp_uri(secret: str, email: str, issuer_name: str = "LoanPulse") -> str:
    """Generates otpauth URI for TOTP authenticators."""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=email, issuer_name=issuer_name)


def generate_totp_qr_data_uri(secret: str, email: str, issuer_name: str = "LoanPulse") -> str:
    """
    Generates a Base64-encoded Data URI for QR code directly in memory.
    Prevents writing sensitive MFA secrets or QR images to disk (Security Rule #10).
    """
    uri = get_totp_uri(secret, email, issuer_name)
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=6,
        border=2,
    )
    qr.add_data(uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    b64_data = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64_data}"


def verify_totp_token(secret: str, token: str) -> bool:
    """Verifies a 6-digit TOTP token with 1-step window drift tolerance."""
    if not secret or not token:
        return False
    totp = pyotp.TOTP(secret)
    return totp.verify(token.strip(), valid_window=1)


def mask_identifier(val: str, visible_suffix: int = 4) -> str:
    """
    Sanitizes sensitive identifiers (SSN, PAN, Bank Accounts) in logs and DB displays.
    Security Rule #19.
    """
    if not val:
        return ""
    clean = str(val).strip()
    if len(clean) <= visible_suffix:
        return "*" * len(clean)
    masked_length = len(clean) - visible_suffix
    return ("*" * masked_length) + clean[-visible_suffix:]


def sanitize_input(text: str) -> str:
    """
    XSS sanitization helper (Security Rule #2).
    Strips malicious HTML tags while preserving clean plain text.
    """
    if not text:
        return ""
    # Strip all HTML tags by default for form text inputs
    cleaned = bleach.clean(text, tags=[], strip=True)
    return cleaned.strip()


def sanitize_filename(filename: str) -> str:
    """Sanitizes uploaded filename, stripping paths and non-alphanumeric chars."""
    if not filename:
        return "unnamed_document"
    # Take only the basename
    clean = filename.split("/")[-1].split("\\")[-1]
    # Remove potentially dangerous characters
    clean = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", clean)
    return clean[:100]
