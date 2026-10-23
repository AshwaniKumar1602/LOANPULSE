from flask import Blueprint, render_template, jsonify, request
from app.models.loan_product import LoanProduct
from app.models.loan_application import LoanApplication

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    products = LoanProduct.query.filter_by(is_active=True).all()
    return render_template("index.html", products=products)


@main_bp.route("/products")
def products():
    """
    Institutional Loan Products Catalogue (Read-Only).
    Publicly accessible to prospective borrowers, existing customers,
    and loan officers for transparent underwriting terms.
    """
    active_products = LoanProduct.query.filter_by(is_active=True).order_by(LoanProduct.id.asc()).all()
    return render_template("products/catalog.html", products=active_products)


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
