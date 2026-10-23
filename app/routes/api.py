from decimal import InvalidOperation
from flask import Blueprint, request, jsonify
from app.extensions import limiter, csrf, db
from app.models.loan_product import LoanProduct
from app.services.calculator_service import calculate_precise_emi, calculate_amortization_schedule_decimal
from app.services.underwriting_engine import validate_product_eligibility

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/calculator", methods=["GET", "POST"])
@api_bp.route("/calculator/compute", methods=["GET", "POST"])
@csrf.exempt
@limiter.limit("60 per minute")
def calculate_emi():
    """
    Computes precise Equated Monthly Installment (EMI) and amortization breakdown.
    Uses Python Decimal arithmetic and standard financial rounding (ROUND_HALF_UP).
    """
    if request.method == "POST":
        data = request.get_json(silent=True) or request.form
    else:
        data = request.args

    try:
        amount = data.get("amount") or data.get("principal", 0)
        tenure = data.get("tenure") or data.get("tenure_months", 0)
        annual_rate = data.get("interest_rate") or data.get("rate") or data.get("annual_rate")
        moratorium = data.get("moratorium_months") or data.get("moratorium", 0)

        product_id = data.get("product_id")
        if (annual_rate is None or annual_rate == "") and product_id:
            product = db.session.get(LoanProduct, int(product_id))
            if product:
                annual_rate = product.base_interest_rate

        if annual_rate is None or annual_rate == "":
            return jsonify({"error": "Missing interest rate parameter."}), 400

        amount_f = float(amount)
        tenure_i = int(tenure)
        rate_f = float(annual_rate)
        moratorium_i = int(moratorium)
    except (ValueError, TypeError, InvalidOperation):
        return jsonify({"error": "Invalid numerical parameters."}), 400

    if amount_f <= 0 or tenure_i <= 0 or rate_f < 0:
        return jsonify({"error": "Principal and tenure must be positive numbers; rate cannot be negative."}), 400

    result = calculate_amortization_schedule_decimal(
        principal=amount_f,
        annual_rate=rate_f,
        tenure_months=tenure_i,
        moratorium_months=moratorium_i,
    )

    return jsonify({
        "monthly_emi": float(result["monthly_emi"]),
        "total_interest": float(result["total_interest"]),
        "total_payment": float(result["total_payment"]),
        "principal": float(result["principal"]),
        "tenure_months": result["tenure_months"],
        "annual_interest_rate": float(result["annual_interest_rate"]),
        "moratorium_months": result["moratorium_months"],
        "schedule": result["schedule"],
    }), 200


@api_bp.route("/eligibility/check", methods=["POST"])
@csrf.exempt
@limiter.limit("60 per minute")
def check_eligibility():
    """
    Evaluates an applicant's financial parameters against configured loan product rules.
    Returns eligibility flag, rule breakdown, and estimated monthly EMI.
    """
    data = request.get_json(silent=True) or request.form

    product_id = data.get("product_id")
    product_code = data.get("product_code")

    product = None
    if product_id:
        try:
            product = db.session.get(LoanProduct, int(product_id))
        except (ValueError, TypeError):
            pass
    elif product_code:
        product = LoanProduct.query.filter_by(code=str(product_code).strip().upper()).first()

    if not product:
        return jsonify({"error": "Loan product not found."}), 404

    try:
        requested_amount = float(data.get("requested_amount") or data.get("amount", 0))
        tenure_months = int(data.get("tenure_months") or data.get("tenure", 0))
        monthly_income = float(data.get("monthly_income") or data.get("income", 0))
        existing_debt = float(data.get("existing_debt", 0.0) or 0.0)
        credit_score = int(data.get("credit_score", 650) or 650)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid numerical parameters."}), 400

    if requested_amount <= 0 or tenure_months <= 0 or monthly_income < 0:
        return jsonify({"error": "Requested amount, tenure, and income must be valid positive values."}), 400

    eligibility = validate_product_eligibility(
        product=product,
        requested_amount=requested_amount,
        tenure_months=tenure_months,
        monthly_income=monthly_income,
        existing_debt=existing_debt,
        credit_score=credit_score,
    )

    return jsonify(eligibility), 200
