from flask import Blueprint, request, jsonify
from app.extensions import limiter

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/calculator", methods=["POST"])
@limiter.limit("60 per minute")
def calculate_emi():
    """
    Computes Equated Monthly Installment (EMI) and breakdown JSON.
    """
    data = request.get_json(silent=True) or request.form
    try:
        amount = float(data.get("amount", 0))
        tenure = int(data.get("tenure", 0))
        annual_rate = float(data.get("interest_rate", 0))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid numerical parameters."}), 400

    if amount <= 0 or tenure <= 0 or annual_rate < 0:
        return jsonify({"error": "Parameters must be positive numbers."}), 400

    monthly_rate = (annual_rate / 100.0) / 12.0
    if monthly_rate == 0:
        emi = round(amount / tenure, 2)
        total_payment = amount
        total_interest = 0.0
    else:
        factor = (1.0 + monthly_rate) ** tenure
        emi = round((amount * monthly_rate * factor) / (factor - 1.0), 2)
        total_payment = round(emi * tenure, 2)
        total_interest = round(total_payment - amount, 2)

    return jsonify({
        "monthly_emi": emi,
        "total_interest": total_interest,
        "total_payment": total_payment,
        "principal": amount,
        "tenure_months": tenure,
        "annual_interest_rate": annual_rate,
    })
