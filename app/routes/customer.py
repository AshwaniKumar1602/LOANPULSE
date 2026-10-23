import os
from datetime import datetime, timezone, date
from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    request,
    abort,
    send_file,
)
from flask_login import login_required, current_user
from app.extensions import db, limiter
from app.models.user import UserRole
from app.models.loan_product import LoanProduct
from app.models.loan_application import LoanApplication, ApplicationStatus
from app.models.document import ApplicationDocument, DocumentStatus, DocumentType
from app.models.repayment import RepaymentSchedule, RepaymentStatus
from app.models.audit import AuditAction
from app.models.notification import Notification, NotificationType
from app.forms.loan_forms import LoanApplicationForm, DocumentUploadForm, RepaymentPaymentForm
from app.utils.decorators import role_required
from app.utils.security import mask_identifier, sanitize_input
from app.services.underwriting_engine import evaluate_loan_application
from app.services.document_service import save_uploaded_document, get_document_file_path
from app.services.audit_service import log_audit
from app.services.notification_service import create_notification
from app.services.repayment_engine import record_repayment, refresh_overdue_schedules

customer_bp = Blueprint("customer", __name__, url_prefix="/customer")


@customer_bp.before_request
@login_required
@role_required(UserRole.CUSTOMER)
def customer_guard():
    """Restricts blueprint strictly to verified customer accounts (Security Rule #13)."""
    pass


@customer_bp.route("/dashboard")
def dashboard():
    refresh_overdue_schedules()

    # Scope all queries to current_user.id (Security Rule #5 & #14: IDOR Prevention)
    applications = LoanApplication.query.filter_by(customer_id=current_user.id).order_by(LoanApplication.created_at.desc()).all()
    
    # Active loans (DISBURSED)
    active_loans = [app for app in applications if app.status == ApplicationStatus.DISBURSED]
    total_borrowed = sum(float(app.approved_amount or app.requested_amount) for app in active_loans)

    # Next upcoming EMI
    next_emi = (
        RepaymentSchedule.query.join(LoanApplication)
        .filter(
            LoanApplication.customer_id == current_user.id,
            RepaymentSchedule.status.in_([RepaymentStatus.UPCOMING, RepaymentStatus.OVERDUE]),
        )
        .order_by(RepaymentSchedule.due_date.asc())
        .first()
    )

    # Unread notifications
    notifications = Notification.query.filter_by(user_id=current_user.id, is_read=False).order_by(Notification.created_at.desc()).limit(5).all()

    return render_template(
        "customer/dashboard.html",
        applications=applications,
        active_loans=active_loans,
        total_borrowed=total_borrowed,
        next_emi=next_emi,
        notifications=notifications,
    )


@customer_bp.route("/loans/apply", methods=["GET", "POST"])
@limiter.limit("10 per hour")
def apply():
    form = LoanApplicationForm()
    products = LoanProduct.query.filter_by(is_active=True).order_by(LoanProduct.name.asc()).all()
    form.product_id.choices = [(p.id, f"{p.name} (APR: {p.base_interest_rate}%)") for p in products]

    if not products:
        flash("No loan products are currently open for new applications.", "warning")
        return redirect(url_for("customer.dashboard"))

    # Pre-select product if passed in query string
    preselected_id = request.args.get("product_id", type=int)
    if request.method == "GET" and preselected_id:
        form.product_id.data = preselected_id

    if form.validate_on_submit():
        product = LoanProduct.query.get_or_404(form.product_id.data)

        # Update profile info
        profile = current_user.customer_profile
        profile.employment_type = form.employment_type.data
        profile.annual_income = float(form.monthly_income.data) * 12.0
        profile.monthly_debt = float(form.existing_monthly_debt.data or 0.0)
        profile.tax_id_masked = mask_identifier(form.tax_id.data)

        # Create application
        application = LoanApplication(
            customer_id=current_user.id,
            product_id=product.id,
            requested_amount=form.requested_amount.data,
            tenure_months=form.tenure_months.data,
            interest_rate=product.base_interest_rate,
            monthly_income_declared=form.monthly_income.data,
            existing_monthly_debt=form.existing_monthly_debt.data or 0.0,
            purpose=sanitize_input(form.purpose.data or ""),
            status=ApplicationStatus.SUBMITTED,
            submitted_at=datetime.now(timezone.utc),
        )
        db.session.add(application)
        db.session.commit()

        # Execute automated underwriting assessment
        assessment = evaluate_loan_application(application)

        # Log audit trail
        log_audit(
            action=AuditAction.APPLICATION_SUBMITTED,
            application_id=application.id,
            actor_id=current_user.id,
            previous_status=ApplicationStatus.DRAFT,
            new_status=ApplicationStatus.SUBMITTED,
            notes=f"Application submitted for ${application.requested_amount} under {product.name}. Auto-evaluation: {assessment.overall_result}",
        )

        create_notification(
            user_id=current_user.id,
            title="Application Submitted Successfully",
            message=f"Your application #{application.application_number} has been submitted and is in review.",
            notification_type=NotificationType.APPLICATION_STATUS,
            link=url_for("customer.application_detail", app_id=application.id),
        )

        flash(f"Application #{application.application_number} submitted! Please upload required KYC documents.", "success")
        return redirect(url_for("customer.application_detail", app_id=application.id))

    return render_template("customer/apply.html", form=form, products=products)


@customer_bp.route("/loans/<int:app_id>")
def application_detail(app_id: int):
    # Strict IDOR prevention: Customer can only access their own loan application
    application = LoanApplication.query.filter_by(id=app_id, customer_id=current_user.id).first_or_404()
    
    upload_form = DocumentUploadForm()
    documents = application.documents.all()
    audit_logs = application.audit_logs.limit(10).all()

    return render_template(
        "customer/application_detail.html",
        application=application,
        documents=documents,
        upload_form=upload_form,
        audit_logs=audit_logs,
    )


@customer_bp.route("/loans/<int:app_id>/documents/upload", methods=["POST"])
@limiter.limit("20 per hour")
def upload_document(app_id: int):
    # Strict IDOR check
    application = LoanApplication.query.filter_by(id=app_id, customer_id=current_user.id).first_or_404()

    form = DocumentUploadForm()
    if form.validate_on_submit():
        file = form.document_file.data
        doc_type = form.document_type.data

        try:
            doc = save_uploaded_document(
                file_storage=file,
                application_id=application.id,
                user_id=current_user.id,
                document_type=doc_type,
            )

            log_audit(
                action=AuditAction.DOCUMENT_UPLOADED,
                application_id=application.id,
                actor_id=current_user.id,
                notes=f"Uploaded document {doc.document_type} ({doc.original_filename})",
            )

            flash("Document uploaded securely and queued for verification.", "success")
        except ValueError as e:
            flash(str(e), "danger")
        except Exception as e:
            flash("An unexpected error occurred while processing your upload.", "danger")

    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"Upload error: {error}", "danger")

    return redirect(url_for("customer.application_detail", app_id=application.id))


@customer_bp.route("/documents/<file_uuid>/download")
def download_document(file_uuid: str):
    # Ownership verification (Security Rule #5)
    doc = ApplicationDocument.query.filter_by(file_uuid=file_uuid).first_or_404()

    if doc.user_id != current_user.id and current_user.role not in (UserRole.LOAN_OFFICER, UserRole.LOAN_MANAGER, UserRole.ADMIN):
        abort(403)

    try:
        path = get_document_file_path(doc)
        return send_file(
            path,
            mimetype=doc.mime_type,
            as_attachment=True,
            download_name=doc.original_filename,
        )
    except FileNotFoundError:
        abort(404)


@customer_bp.route("/loans/<int:app_id>/repayments")
def repayment_schedule(app_id: int):
    # IDOR check
    application = LoanApplication.query.filter_by(id=app_id, customer_id=current_user.id).first_or_404()
    schedules = application.repayment_schedules.order_by(RepaymentSchedule.installment_number.asc()).all()

    return render_template(
        "customer/repayments.html",
        application=application,
        schedules=schedules,
    )


@customer_bp.route("/repayments/<int:schedule_id>/pay", methods=["GET", "POST"])
def pay_installment(schedule_id: int):
    # IDOR check via join with LoanApplication
    schedule = (
        RepaymentSchedule.query.join(LoanApplication)
        .filter(
            RepaymentSchedule.id == schedule_id,
            LoanApplication.customer_id == current_user.id,
        )
        .first_or_404()
    )

    if schedule.status == RepaymentStatus.PAID:
        flash("This installment has already been settled in full.", "info")
        return redirect(url_for("customer.repayment_schedule", app_id=schedule.application_id))

    form = RepaymentPaymentForm()
    if request.method == "GET":
        form.amount.data = schedule.outstanding_balance

    if form.validate_on_submit():
        amount_to_pay = float(form.amount.data)
        if amount_to_pay <= 0:
            flash("Payment amount must be greater than zero.", "danger")
            return render_template("customer/pay_installment.html", schedule=schedule, form=form)

        try:
            txn = record_repayment(
                schedule=schedule,
                amount=amount_to_pay,
                payment_method=form.payment_method.data,
                customer_id=current_user.id,
            )

            log_audit(
                action=AuditAction.REPAYMENT_RECORDED,
                application_id=schedule.application_id,
                actor_id=current_user.id,
                notes=f"Customer paid ${amount_to_pay:.2f} for Installment #{schedule.installment_number} via {form.payment_method.data}. TXN: {txn.transaction_ref}",
            )

            create_notification(
                user_id=current_user.id,
                title="Repayment Received",
                message=f"Your payment of ${amount_to_pay:.2f} (Ref: {txn.transaction_ref}) was received successfully.",
                notification_type=NotificationType.EMI_DUE,
                link=url_for("customer.repayment_schedule", app_id=schedule.application_id),
            )

            flash(f"Payment of ${amount_to_pay:.2f} processed successfully! Reference: {txn.transaction_ref}", "success")
            return redirect(url_for("customer.repayment_schedule", app_id=schedule.application_id))
        except Exception as e:
            flash(f"Payment failed: {str(e)}", "danger")

    return render_template("customer/pay_installment.html", schedule=schedule, form=form)


@customer_bp.route("/notifications/read-all", methods=["POST"])
def read_all_notifications():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({"is_read": True})
    db.session.commit()
    flash("All notifications marked as read.", "info")
    return redirect(url_for("customer.dashboard"))
