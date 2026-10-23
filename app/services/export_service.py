import csv
import io
from app.models.loan_application import LoanApplication
from app.models.repayment import RepaymentSchedule


def stream_applications_csv(query_cursor):
    """
    Render Free-Tier Optimization (Rule #2):
    Yields CSV chunks one-by-one via Python generator streaming to minimize RAM footprint.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    # Header row
    writer.writerow([
        "Application Number",
        "Customer Name",
        "Customer Email",
        "Loan Product",
        "Requested Amount (INR)",
        "Approved Amount (INR)",
        "Tenure (Months)",
        "Interest Rate (%)",
        "Status",
        "Risk Score",
        "Automated Decision",
        "Submitted At",
    ])
    yield buffer.getvalue()
    buffer.seek(0)
    buffer.truncate(0)

    # Chunk processing: yield line by line
    for app in query_cursor:
        customer_name = app.customer.full_name if app.customer else "N/A"
        customer_email = app.customer.email if app.customer else "N/A"
        product_name = app.product.name if app.product else "N/A"
        submitted = app.submitted_at.strftime("%Y-%m-%d %H:%M:%S") if app.submitted_at else "Draft"

        writer.writerow([
            app.application_number,
            customer_name,
            customer_email,
            product_name,
            f"{float(app.requested_amount):.2f}",
            f"{float(app.approved_amount or 0):.2f}",
            app.tenure_months,
            f"{float(app.interest_rate):.2f}",
            app.status,
            f"{float(app.risk_score or 0):.1f}",
            app.automated_decision or "Pending",
            submitted,
        ])
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)


def stream_repayments_csv(query_cursor):
    """
    Generator streaming for repayment schedules CSV export.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    writer.writerow([
        "Application Number",
        "Customer Name",
        "Installment Number",
        "Due Date",
        "Principal Component (INR)",
        "Interest Component (INR)",
        "Total Installment EMI (INR)",
        "Remaining Principal (INR)",
        "Paid Amount (INR)",
        "Status",
        "Paid Date",
    ])
    yield buffer.getvalue()
    buffer.seek(0)
    buffer.truncate(0)

    for item in query_cursor:
        app_num = item.application.application_number if item.application else "N/A"
        customer_name = item.application.customer.full_name if item.application and item.application.customer else "N/A"
        paid_date = item.paid_date.strftime("%Y-%m-%d") if item.paid_date else "N/A"

        writer.writerow([
            app_num,
            customer_name,
            item.installment_number,
            item.due_date.strftime("%Y-%m-%d"),
            f"{float(item.principal_amount):.2f}",
            f"{float(item.interest_amount):.2f}",
            f"{float(item.total_installment):.2f}",
            f"{float(item.remaining_principal):.2f}",
            f"{float(item.paid_amount):.2f}",
            item.status,
            paid_date,
        ])
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
