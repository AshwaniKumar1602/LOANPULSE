from flask import Blueprint, render_template, jsonify, request
from app.models.loan_product import LoanProduct
from app.models.loan_application import LoanApplication

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    products = LoanProduct.query.filter_by(is_active=True).all()
    return render_template("index.html", products=products)


@main_bp.route("/calculator")
def calculator():
    products = LoanProduct.query.filter_by(is_active=True).all()
    return render_template("customer/calculator.html", products=products)


@main_bp.route("/health")
def health_check():
    """Health check endpoint for Render and infrastructure monitoring."""
    return jsonify({
        "status": "healthy",
        "service": "LoanPulse LoanMaster",
        "version": "1.0.0",
    }), 200
