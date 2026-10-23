import os
import uuid
from werkzeug.utils import secure_filename
from app.config import Config
from app.extensions import db
from app.models.document import ApplicationDocument, DocumentStatus, DocumentType
from app.utils.security import sanitize_filename

# Signature header checking for true MIME verification
MAGIC_SIGNATURES = {
    "pdf": [b"%PDF-"],
    "png": [b"\x89PNG\r\n\x1a\n"],
    "jpg": [b"\xff\xd8\xff"],
    "jpeg": [b"\xff\xd8\xff"],
}

MIME_MAP = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
}


def is_allowed_file(filename: str) -> bool:
    """Checks extension against whitelist."""
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in Config.ALLOWED_EXTENSIONS


def verify_file_header(file_stream, ext: str) -> bool:
    """Verifies file binary header against expected magic numbers (Security Rule #4)."""
    ext = ext.lower()
    expected_signatures = MAGIC_SIGNATURES.get(ext)
    if not expected_signatures:
        return False

    current_pos = file_stream.tell()
    file_stream.seek(0)
    header = file_stream.read(16)
    file_stream.seek(current_pos)

    for sig in expected_signatures:
        if header.startswith(sig):
            return True
    return False


def save_uploaded_document(
    file_storage,
    application_id: int,
    user_id: int,
    document_type: str,
) -> ApplicationDocument:
    """
    Saves an uploaded document safely:
    - Verifies extension & binary header
    - Assigns random UUID filename to prevent directory traversal & script execution
    - Stores in isolated folder outside web root
    """
    if not file_storage or not file_storage.filename:
        raise ValueError("No file provided.")

    original_name = sanitize_filename(file_storage.filename)
    if not is_allowed_file(original_name):
        raise ValueError("Invalid file extension. Only PDF, PNG, and JPG files are permitted.")

    ext = original_name.rsplit(".", 1)[1].lower()

    # Binary header validation
    if not verify_file_header(file_storage.stream, ext):
        raise ValueError("File content does not match the declared file extension.")

    # Check file size (max 5MB)
    file_storage.stream.seek(0, os.SEEK_END)
    file_size = file_storage.stream.tell()
    file_storage.stream.seek(0)

    if file_size > Config.MAX_CONTENT_LENGTH:
        raise ValueError(f"File size exceeds the {Config.MAX_CONTENT_LENGTH // (1024*1024)}MB maximum limit.")

    # Generate secure UUID filename
    file_uuid = str(uuid.uuid4())
    stored_name = f"{file_uuid}.{ext}"

    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
    destination_path = os.path.join(Config.UPLOAD_FOLDER, stored_name)

    file_storage.save(destination_path)

    # Create document record
    doc = ApplicationDocument(
        application_id=application_id,
        user_id=user_id,
        document_type=document_type,
        file_uuid=file_uuid,
        original_filename=original_name,
        stored_filename=stored_name,
        mime_type=MIME_MAP.get(ext, "application/octet-stream"),
        file_size=file_size,
        verification_status=DocumentStatus.PENDING,
    )
    db.session.add(doc)
    db.session.commit()
    return doc


def get_document_file_path(document: ApplicationDocument) -> str:
    """Returns absolute file path to a stored document."""
    file_path = os.path.join(Config.UPLOAD_FOLDER, document.stored_filename)
    if not os.path.exists(file_path):
        raise FileNotFoundError("Requested document file does not exist on disk.")
    return file_path
