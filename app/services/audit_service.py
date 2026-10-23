from flask import request
from app.extensions import db
from app.models.audit import DecisionAuditLog


def log_audit(
    action: str,
    application_id: int = None,
    actor_id: int = None,
    previous_status: str = None,
    new_status: str = None,
    notes: str = None,
    ip_address: str = None,
):
    """
    Records an immutable audit event for compliance and security tracking.
    """
    if not ip_address and request:
        try:
            ip_address = request.headers.get("X-Forwarded-For", request.remote_addr)
            if ip_address and "," in ip_address:
                ip_address = ip_address.split(",")[0].strip()
        except Exception:
            ip_address = None

    log_entry = DecisionAuditLog(
        application_id=application_id,
        actor_id=actor_id,
        action=action,
        previous_status=previous_status,
        new_status=new_status,
        notes=notes,
        ip_address=ip_address,
    )
    db.session.add(log_entry)
    db.session.commit()
    return log_entry
