from datetime import datetime, timezone
from sqlalchemy import func
from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    request,
    Response,
    abort,
)
from flask_login import login_required, current_user
from app.extensions import db
from app.models.user import UserRole, User
from app.models.loan_product import LoanProduct
from app.models.loan_application import LoanApplication, ApplicationStatus
from app.models.disbursement import Disbursement, DisbursementStatus
from app.models.repayment import RepaymentSchedule, RepaymentStatus
from app.models.audit import DecisionAuditLog, AuditAction
from app.models.notification import NotificationType
from app.forms.management_forms import (
    ManagerDecisionForm,
    DisbursementForm,
    LoanProductForm,
)
from app.utils.decorators import role_required, mfa_enforced_for_staff
from app.utils.security import mask_identifier, sanitize_input
from app.utils.formatters import inr_currency
from app.services.audit_service import log_audit
from app.services.notification_service import create_notification
from app.services.repayment_engine import generate_amortization_schedule, refresh_overdue_schedules
from app.services.export_service import stream_applications_csv, stream_repayments_csv

manager_bp = Blueprint("manager", __name__, url_prefix="/manager")


@manager_bp.before_request
@login_required
@role_required(UserRole.LOAN_MANAGER, UserRole.ADMIN)
@mfa_enforced_for_staff
def manager_guard():
    """Restricts blueprint to authorized Loan Managers and Admins with 2FA verified."""
    pass


@manager_bp.route("/dashboard")
def dashboard():
    refresh_overdue_schedules()

    # Portfolio KPI Metrics generated via optimized SQL aggregation queries
    # Render Free-Tier Optimization: zero in-memory entity loops
    total_applications = LoanApplication.query.count()

    approved_count = LoanApplication.query.filter(
        LoanApplication.status.in_([ApplicationStatus.APPROVED, ApplicationStatus.DISBURSED, ApplicationStatus.COMPLETED])
    ).count()
    rejected_count = LoanApplication.query.filter_by(status=ApplicationStatus.REJECTED).count()

    decided_count = approved_count + rejected_count
    approval_rate = round((approved_count / decided_count * 100.0), 1) if decided_count > 0 else 0.0

    # 1. Total Active Loans count (Optimized SQL COUNT)
    total_active_loans = LoanApplication.query.filter_by(status=ApplicationStatus.DISBURSED).count()

    # 2. Total Disbursed capital released (Optimized SQL SUM)
    total_disbursed_volume = float(
        db.session.query(func.coalesce(func.sum(Disbursement.amount), 0.0))
        .filter(Disbursement.status == DisbursementStatus.PROCESSED)
        .scalar()
    )
    if total_disbursed_volume == 0.0:
        total_disbursed_volume = float(
            db.session.query(
                func.coalesce(func.sum(func.coalesce(LoanApplication.approved_amount, LoanApplication.requested_amount)), 0.0)
            )
            .filter(LoanApplication.status.in_([ApplicationStatus.DISBURSED, ApplicationStatus.COMPLETED]))
            .scalar()
        )

    # Active portfolio outstanding volume (SQL SUM)
    active_portfolio_volume = float(
        db.session.query(
            func.coalesce(func.sum(func.coalesce(LoanApplication.approved_amount, LoanApplication.requested_amount)), 0.0)
        )
        .filter(LoanApplication.status == ApplicationStatus.DISBURSED)
        .scalar()
    )

    # 3. Pending Approvals queue count (Optimized SQL IN)
    pending_approvals_count = LoanApplication.query.filter(
        LoanApplication.status.in_([
            ApplicationStatus.RECOMMENDED_APPROVAL,
            ApplicationStatus.RECOMMENDED_REJECTION,
            ApplicationStatus.UNDER_REVIEW,
        ])
    ).count()

    ready_for_disbursement_count = LoanApplication.query.filter_by(status=ApplicationStatus.APPROVED).count()

    # Delinquency rate via SQL aggregates
    total_schedules_due = RepaymentSchedule.query.count()
    overdue_schedules = RepaymentSchedule.query.filter_by(status=RepaymentStatus.OVERDUE).count()
    delinquency_rate = round((overdue_schedules / total_schedules_due * 100.0), 1) if total_schedules_due > 0 else 0.0

    # Recent Audit activity
    recent_logs = DecisionAuditLog.query.order_by(DecisionAuditLog.created_at.desc()).limit(8).all()

    return render_template(
        "manager/dashboard.html",
        total_applications=total_applications,
        approval_rate=approval_rate,
        total_active_loans=total_active_loans,
        active_loans_count=total_active_loans,
        active_portfolio_volume=active_portfolio_volume,
        total_disbursed=total_disbursed_volume,
        total_disbursed_volume=total_disbursed_volume,
        delinquency_rate=delinquency_rate,
        pending_approvals_count=pending_approvals_count,
        ready_for_disbursement_count=ready_for_disbursement_count,
        recent_logs=recent_logs,
    )


@manager_bp.route("/approvals")
def approvals():
    status_filter = request.args.get("status", "").strip()
    query = LoanApplication.query

    if status_filter:
        query = query.filter_by(status=status_filter)
    else:
        # Default: show actionable items
        query = query.filter(LoanApplication.status.in_([
            ApplicationStatus.RECOMMENDED_APPROVAL,
            ApplicationStatus.RECOMMENDED_REJECTION,
            ApplicationStatus.APPROVED,
            ApplicationStatus.UNDER_REVIEW,
        ]))

    applications = query.order_by(LoanApplication.created_at.desc()).all()
    return render_template("manager/approvals.html", applications=applications, current_status=status_filter)


@manager_bp.route("/loans/<int:app_id>/decision", methods=["GET", "POST"])
def decision(app_id: int):
    application = db.get_or_404(LoanApplication, app_id)

    # State validation: Prevent modifying already disbursed/closed loans
    if application.status in [ApplicationStatus.DISBURSED, ApplicationStatus.COMPLETED]:
        flash(f"Application #{application.application_number} is already {application.status} and cannot be modified.", "warning")
        return redirect(url_for("manager.approvals"))

    form = ManagerDecisionForm()

    if request.method == "GET":
        form.approved_amount.data = application.approved_amount or application.requested_amount
        form.interest_rate.data = application.interest_rate

    if form.validate_on_submit():
        decision_choice = form.decision.data
        remarks = sanitize_input(form.remarks.data)
        old_status = application.status

        target_status = ApplicationStatus.APPROVED if decision_choice == "APPROVE" else ApplicationStatus.REJECTED
        try:
            application.transition_to(target_status)
        except ValueError as err:
            flash(str(err), "danger")
            return redirect(url_for("manager.approvals"))

        if decision_choice == "APPROVE":
            application.approved_amount = form.approved_amount.data
            application.interest_rate = form.interest_rate.data
            action = AuditAction.MANAGER_APPROVED
            notif_msg = f"Congratulations! Your loan #{application.application_number} has been APPROVED for {inr_currency(form.approved_amount.data)} at {form.interest_rate.data}% APR."
            flash_msg = f"Application #{application.application_number} officially APPROVED. Ready for disbursement."
        else:
            action = AuditAction.MANAGER_REJECTED
            notif_msg = f"Your loan application #{application.application_number} has been rejected. Remarks: {remarks}"
            flash_msg = f"Application #{application.application_number} REJECTED."

        log_audit(
            action=action,
            application_id=application.id,
            actor_id=current_user.id,
            previous_status=old_status,
            new_status=application.status,
            notes=f"Manager {current_user.full_name} issued decision '{decision_choice}'. Remarks: {remarks}",
        )

        create_notification(
            user_id=application.customer_id,
            title=f"Application {application.status.capitalize()}",
            message=notif_msg,
            notification_type=NotificationType.APPLICATION_STATUS,
            link=url_for("customer.application_detail", app_id=application.id),
        )

        db.session.commit()
        flash(flash_msg, "success")
        return redirect(url_for("manager.approvals"))

    documents = application.documents.all()
    audit_logs = application.audit_logs.limit(15).all()

    return render_template(
        "manager/decision.html",
        application=application,
        documents=documents,
        form=form,
        audit_logs=audit_logs,
    )


@manager_bp.route("/loans/<int:app_id>/disburse", methods=["GET", "POST"])
def disburse(app_id: int):
    application = db.get_or_404(LoanApplication, app_id)

    if application.status == ApplicationStatus.DISBURSED:
        flash(f"Application #{application.application_number} has already been disbursed.", "warning")
        return redirect(url_for("manager.approvals"))

    if application.status != ApplicationStatus.APPROVED:
        flash("Only approved loan applications can be disbursed.", "warning")
        return redirect(url_for("manager.approvals"))

    form = DisbursementForm()
    if form.validate_on_submit():
        amount = float(application.approved_amount or application.requested_amount)
        bank_name = sanitize_input(form.bank_name.data.strip())
        raw_account = form.bank_account.data.strip()
        bank_routing = sanitize_input(form.bank_routing.data.strip())
        disb_method = form.disbursement_method.data
        notes = sanitize_input(form.notes.data or "")

        # Create disbursement record with masked account (Security Rule #19)
        disbursement = Disbursement(
            application_id=application.id,
            authorized_by_id=current_user.id,
            amount=amount,
            disbursement_method=disb_method,
            bank_name=bank_name,
            bank_account_masked=mask_identifier(raw_account, visible_suffix=4),
            bank_routing_or_ifsc=bank_routing,
            status=DisbursementStatus.PROCESSED,
            notes=notes,
            disbursed_at=datetime.now(timezone.utc),
        )
        db.session.add(disbursement)

        # Update application status
        old_status = application.status
        try:
            application.transition_to(ApplicationStatus.DISBURSED)
        except ValueError as err:
            flash(str(err), "danger")
            return redirect(url_for("manager.approvals"))

        # Generate Amortization Schedule
        schedules = generate_amortization_schedule(application)

        log_audit(
            action=AuditAction.DISBURSEMENT_COMPLETED,
            application_id=application.id,
            actor_id=current_user.id,
            previous_status=old_status,
            new_status=ApplicationStatus.DISBURSED,
            notes=f"Disbursed {inr_currency(amount)} via {disb_method} to {bank_name} ({mask_identifier(raw_account)}). Ref: {disbursement.disbursement_reference}. Generated {len(schedules)} EMI installments.",
        )

        create_notification(
            user_id=application.customer_id,
            title="Loan Funds Disbursed!",
            message=f"Loan #{application.application_number} funds of {inr_currency(amount)} have been disbursed to your account. Your EMI repayment schedule is now active.",
            notification_type=NotificationType.DISBURSEMENT,
            link=url_for("customer.repayment_schedule", app_id=application.id),
        )

        db.session.commit()
        flash(f"Funds successfully disbursed! Reference: {disbursement.disbursement_reference}. {len(schedules)} EMI installments generated.", "success")
        return redirect(url_for("manager.approvals"))

    return render_template("manager/disburse.html", application=application, form=form)


@manager_bp.route("/products")
def products():
    all_products = LoanProduct.query.order_by(LoanProduct.name.asc()).all()
    return render_template("manager/products.html", products=all_products)


@manager_bp.route("/products/create", methods=["GET", "POST"])
def create_product():
    form = LoanProductForm()
    if form.validate_on_submit():
        code = sanitize_input(form.code.data.strip().upper())
        if LoanProduct.query.filter_by(code=code).first():
            flash(f"A product with code '{code}' already exists.", "danger")
            return render_template("manager/product_edit.html", form=form, title="Create New Loan Product")

        product = LoanProduct(
            code=code,
            name=sanitize_input(form.name.data.strip()),
            description=sanitize_input(form.description.data or ""),
            loan_category=form.loan_category.data,
            min_amount=form.min_amount.data,
            max_amount=form.max_amount.data,
            min_tenure_months=form.min_tenure_months.data,
            max_tenure_months=form.max_tenure_months.data,
            base_interest_rate=form.base_interest_rate.data,
            min_credit_score=form.min_credit_score.data,
            max_dti_ratio=form.max_dti_ratio.data,
            min_income_required=form.min_income_required.data,
            secured=form.secured.data,
            moratorium_months=form.moratorium_months.data or 0,
            processing_speed=form.processing_speed.data,
            is_active=form.is_active.data,
        )
        db.session.add(product)
        db.session.commit()
        flash(f"Loan Product '{product.name}' created successfully.", "success")
        return redirect(url_for("manager.products"))

    return render_template("manager/product_edit.html", form=form, title="Create New Loan Product")


@manager_bp.route("/products/<int:prod_id>/edit", methods=["GET", "POST"])
def edit_product(prod_id: int):
    product = db.get_or_404(LoanProduct, prod_id)
    form = LoanProductForm(obj=product)

    if form.validate_on_submit():
        product.name = sanitize_input(form.name.data.strip())
        product.description = sanitize_input(form.description.data or "")
        product.loan_category = form.loan_category.data
        product.min_amount = form.min_amount.data
        product.max_amount = form.max_amount.data
        product.min_tenure_months = form.min_tenure_months.data
        product.max_tenure_months = form.max_tenure_months.data
        product.base_interest_rate = form.base_interest_rate.data
        product.min_credit_score = form.min_credit_score.data
        product.max_dti_ratio = form.max_dti_ratio.data
        product.min_income_required = form.min_income_required.data
        product.secured = form.secured.data
        product.moratorium_months = form.moratorium_months.data or 0
        product.processing_speed = form.processing_speed.data
        product.is_active = form.is_active.data

        db.session.commit()
        flash(f"Product '{product.name}' updated successfully.", "success")
        return redirect(url_for("manager.products"))

    return render_template("manager/product_edit.html", form=form, title=f"Edit Product: {product.name}")


@manager_bp.route("/products/<int:prod_id>/toggle-status", methods=["POST"])
def toggle_product_status(prod_id: int):
    product = db.get_or_404(LoanProduct, prod_id)
    product.is_active = not product.is_active
    db.session.commit()
    status_label = "activated" if product.is_active else "deactivated"
    flash(f"Loan Product '{product.name}' has been {status_label}.", "info")
    return redirect(url_for("manager.products"))


@manager_bp.route("/audit-logs")
def audit_logs():
    page = request.args.get("page", 1, type=int)
    logs_pagination = DecisionAuditLog.query.order_by(DecisionAuditLog.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    return render_template("manager/audit_logs.html", pagination=logs_pagination)


@manager_bp.route("/reports/export/applications")
def export_applications():
    """
    Render Free-Tier Optimization (Rule #2):
    Streamed CSV download generator avoiding memory exhaustion.
    """
    cursor = LoanApplication.query.order_by(LoanApplication.created_at.desc())
    return Response(
        stream_applications_csv(cursor),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=loanpulse_applications_export.csv"},
    )


@manager_bp.route("/reports/export/repayments")
def export_repayments():
    """
    Streamed CSV download generator for repayments.
    """
    cursor = RepaymentSchedule.query.order_by(RepaymentSchedule.due_date.asc())
    return Response(
        stream_repayments_csv(cursor),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=loanpulse_repayment_schedules.csv"},
    )
