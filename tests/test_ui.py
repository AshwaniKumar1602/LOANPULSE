from app.models.loan_product import LoanProduct
from app.models.user import User, UserRole


def test_index_page_responsive_render(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "LoanPulse" in html
    assert "Tailwind CSS CDN" in html or "tailwind.config" in html
    # Check theme tokens present in base config
    assert "#D97706" in html
    assert "#F59E0B" in html
    assert "#0F172A" in html


def test_calculator_page_render(client):
    response = client.get("/calculator")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "Equated Monthly Installment (EMI) Calculator" in html
    assert "calc-amount" in html


def test_ui_components_macro_import(app):
    with app.test_request_context():
        from flask import render_template_string
        template_str = """
        {% import 'components/ui_components.html' as ui %}
        {{ ui.button('Apply Now', variant='primary', size='md') }}
        {{ ui.stat_card('Active Volume', '$25,000', subtitle='1 active loan') }}
        """
        rendered = render_template_string(template_str)
        assert "Apply Now" in rendered
        assert "Active Volume" in rendered
        assert "$25,000" in rendered
        assert "bg-amber-500" in rendered
