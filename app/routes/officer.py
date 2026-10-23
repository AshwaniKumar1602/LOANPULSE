from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app.extensions import db
from app.models.user import UserRole, User
from app.models.loan_product import LoanProduct
from app.models.loan_application import LoanApplication, ApplicationStatus
from app.models.document import ApplicationDocument, DocumentStatus
from app.models.audit import AuditAction
from app.models.notification import NotificationType
from app.forms.management_forms import OfficerRecommendationForm, DocumentVerificationForm
from app.utils.decorators import role_required, mfa_enforced_for_staff
from app.utils.security import sanitize_input
from app.services.underwriting_engine import evaluate_loan_application
from app.services.audit_service import log_audit
from app.services.notification_service import create_notification

officer_bp = Blueprint("officer", __name__, url_prefix="/officer")


@officer_bp.before_request
@login_required
@role_required(UserRole.LOAN_OFFICER, UserRole.LOAN_MANAGER, UserRole.ADMIN)
@mfa_enforced_for_staff
def officer_guard():
    """Restricts access to authenticated staff with verified 2FA (Security Rules #10 & #13)."""
    pass


@officer_bp.route("/dashboard")
def dashboard():
    status_filter = request.args.get("status", "").strip()
    product_filter = request.args.get("product_id", type=int)
    search_query = request.args.get("q", "").strip()

    query = LoanApplication.query

    # Status filter
    if status_filter:
        query = query.filter(LoanApplication.status == status_filter)
    else:
        # Default: show active queue
        query = query.filter(LoanApplication.status.in_([
            ApplicationStatus.SUBMITTED,
            ApplicationStatus.UNDER_REVIEW,
            ApplicationStatus.PENDING_DOCS,
            ApplicationStatus.RECOMMENDED_APPROVAL,
            ApplicationStatus.RECOMMENDED_REJECTION,
        ]))

    if product_filter:
        query = query.filter(LoanApplication.product_id == product_filter)

    if search_query:
        query = query.join(User).filter(
            db.or_(
                LoanApplication.application_number.ilike(f"%{search_query}%"),
                User.first_name.ilike(f"%{search_query}%"),
                User.last_name.ilike(f"%{search_query}%"),
                User.email.ilike(f"%{search_query}%"),
            )
        )

    applications = query.order_by(LoanApplication.created_at.desc()).all()
    products = LoanProduct.query.order_by(LoanProduct.name.asc()).all()

    # Metric counts
    submitted_count = LoanApplication.query.filter_by(status=ApplicationStatus.SUBMITTED).count()
    under_review_count = LoanApplication.query.filter_by(status=ApplicationStatus.UNDER_REVIEW).count()
    pending_docs_count = LoanApplication.query.filter_by(status=ApplicationStatus.PENDING_DOCS).count()

    return render_template(
        "officer/dashboard.html",
        applications=applications,
        products=products,
        current_status=status_filter,
        current_product=product_filter,
        search_query=search_query,
        submitted_count=submitted_count,
        under_review_count=under_review_count,
        pending_docs_count=pending_docs_count,
    )


@officer_bp.route("/loans/<int:app_id>/review")
def review(app_id: int):
    application = LoanApplication.query.get_or_404(app_id)

    # Automatically advance SUBMITTED to UNDER_REVIEW on first officer inspection
    if application.status == ApplicationStatus.SUBMITTED:
        application.status = ApplicationStatus.UNDER_REVIEW
        if not application.underwriting:
            evaluate_loan_application(application, evaluator_id=current_user.id)
        log_audit(
            action=AuditAction.UNDERWRITING_EVALUATED,
            application_id=application.id,
            actor_id=current_user.id,
            previous_status=ApplicationStatus.SUBMITTED,
            new_status=ApplicationStatus.UNDER_REVIEW,
            notes=f"Officer {current_user.full_name} initiated manual review and underwriting.",
        )
        db.session.commit()

    recommend_form = OfficerRecommendationForm()
    verify_form = DocumentVerificationForm()

    documents = application.documents.all()
    audit_logs = application.audit_logs.limit(15).all()

    return render_template(
        "officer/review.html",
        application=application,
        documents=documents,
        recommend_form=recommend_form,
        verify_form=verify_form,
        audit_logs=audit_logs,
    )


FINAL_STATUSES = [
    ApplicationStatus.APPROVED,
    ApplicationStatus.DISBURSED,
    ApplicationStatus.REJECTED,
    ApplicationStatus.COMPLETED,
]

ALLOWED_OFFICER_ACTIONS = [
    ApplicationStatus.RECOMMENDED_APPROVAL,
    ApplicationStatus.RECOMMENDED_REJECTION,
    ApplicationStatus.PENDING_DOCS,
    ApplicationStatus.UNDER_REVIEW,
]


@officer_bp.route("/documents/<int:doc_id>/verify", methods=["POST"])
def verify_document(doc_id: int):
    document = ApplicationDocument.query.get_or_404(doc_id)
    
    # State validation: Prevent tampering with finalized loans
    if document.application.status in FINAL_STATUSES:
        flash("Cannot modify verification records for finalized applications.", "danger")
        return redirect(url_for("officer.review", app_id=document.application_id))

    form = DocumentVerificationForm()

    if form.validate_on_submit():
        new_status = form.verification_status.data
        if new_status not in [DocumentStatus.VERIFIED, DocumentStatus.REJECTED]:
            abort(400)

        notes = sanitize_input(form.verification_notes.data or "")

        document.verification_status = new_status
        document.verification_notes = notes
        document.verified_by_id = current_user.id
        document.verified_at = datetime.now(timezone.utc)

        action = AuditAction.DOCUMENT_VERIFIED if new_status == DocumentStatus.VERIFIED else AuditAction.DOCUMENT_REJECTED
        log_audit(
            action=action,
            application_id=document.application_id,
            actor_id=current_user.id,
            notes=f"Document '{document.document_type}' marked as {new_status}. Notes: {notes}",
        )

        # Notify customer if document rejected
        if new_status == DocumentStatus.REJECTED:
            create_notification(
                user_id=document.user_id,
                title="Document Requires Re-upload",
                message=f"Your {document.document_type} was rejected: {notes}. Please upload a clear replacement.",
                notification_type=NotificationType.DOCUMENT_REQUEST,
                link=url_for("customer.application_detail", app_id=document.application_id),
            )

        db.session.commit()
        flash(f"Document marked as {new_status}.", "success")
    else:
        flash("Invalid verification submission.", "danger")

    return redirect(url_for("officer.review", app_id=document.application_id))


@officer_bp.route("/loans/<int:app_id>/underwrite", methods=["POST"])
def run_underwriting(app_id: int):
    application = LoanApplication.query.get_or_404(app_id)

    # State validation
    if application.status in FINAL_STATUSES:
        flash("Finalized applications cannot be re-evaluated.", "warning")
        return redirect(url_for("officer.review", app_id=application.id))

    assessment = evaluate_loan_application(application, evaluator_id=current_user.id)

    log_audit(
        action=AuditAction.UNDERWRITING_EVALUATED,
        application_id=application.id,
        actor_id=current_user.id,
        notes=f"Officer {current_user.full_name} re-evaluated underwriting rules: Result={assessment.overall_result}, Risk Score={application.risk_score}.",
    )

    flash(f"Rule assessment completed: {assessment.overall_result} (Risk Score: {application.risk_score})", "info")
    return redirect(url_for("officer.review", app_id=application.id))


@officer_bp.route("/loans/<int:app_id>/recommend", methods=["POST"])
def submit_recommendation(app_id: int):
    application = LoanApplication.query.get_or_404(app_id)

    # State validation: Reject status transitions on finalized loans
    if application.status in FINAL_STATUSES:
        flash(f"Application #{application.application_number} has already received a final decision ({application.status}) and cannot be modified.", "danger")
        return redirect(url_for("officer.review", app_id=application.id))

    form = OfficerRecommendationForm()

    if form.validate_on_submit():
        rec = form.recommendation.data
        if rec not in ALLOWED_OFFICER_ACTIONS:
            abort(400)

        notes = sanitize_input(form.notes.data)
        old_status = application.status
        application.status = rec

        log_audit(
            action=AuditAction.OFFICER_RECOMMENDATION,
            application_id=application.id,
            actor_id=current_user.id,
            previous_status=old_status,
            new_status=rec,
            notes=f"Recommendation: {rec}. Officer notes: {notes}",
        )

        # 1. Under review notes update
        if rec == ApplicationStatus.UNDER_REVIEW:
            db.session.commit()
            flash("Underwriting review notes recorded. Application remains under active review.", "info")
            return redirect(url_for("officer.review", app_id=application.id))

        # 2. Document clarification / resubmission request
        if rec == ApplicationStatus.PENDING_DOCS:
            create_notification(
                user_id=application.customer_id,
                title="Additional Documents Required",
                message=f"Loan officer requested information for #{application.application_number}: {notes}",
                notification_type=NotificationType.DOCUMENT_REQUEST,
                link=url_for("customer.application_detail", app_id=application.id),
            )
            db.session.commit()
            flash("Application marked as PENDING DOCS. Customer notified to submit required documentation.", "warning")
            return redirect(url_for("officer.dashboard"))

        # 3. Forward to Loan Manager for approval or rejection
        db.session.commit()
        label = "Recommended for Approval" if rec == ApplicationStatus.RECOMMENDED_APPROVAL else "Recommended for Rejection"
        flash(f"Application #{application.application_number} successfully {label} and forwarded to Manager Approvals Queue.", "success")
        return redirect(url_for("officer.dashboard"))

    for field, errors in form.errors.items():
        for error in errors:
            flash(f"Error: {error}", "danger")

    return redirect(url_for("officer.review", app_id=application.id))
