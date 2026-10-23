from decimal import Decimal, ROUND_HALF_UP, ROUND_HALF_EVEN
from typing import Dict, Any, List


def calculate_precise_emi(
    principal: Decimal | float | str,
    annual_rate: Decimal | float | str,
    tenure_months: int,
    rounding_mode=ROUND_HALF_UP,
) -> Decimal:
    """
    Computes precise reducing-balance Equated Monthly Installment (EMI)
    using Python Decimal arithmetic and standard financial rounding (ROUND_HALF_UP).

    Formula:
        EMI = [P * r * (1 + r)^n] / [(1 + r)^n - 1]
    where:
        P = Principal loan amount
        r = Monthly interest rate = (Annual Rate / 100) / 12
        n = Tenure in months
    """
    P = Decimal(str(principal))
    rate = Decimal(str(annual_rate))
    n = int(tenure_months)

    if P <= Decimal("0") or n <= 0:
        return Decimal("0.00")

    if rate <= Decimal("0"):
        return (P / Decimal(str(n))).quantize(Decimal("0.01"), rounding=rounding_mode)

    monthly_rate = rate / (Decimal("12") * Decimal("100"))

    # Precise factor computation using Decimal power
    factor = (Decimal("1") + monthly_rate) ** n
    numerator = P * monthly_rate * factor
    denominator = factor - Decimal("1")

    if denominator == Decimal("0"):
        return (P / Decimal(str(n))).quantize(Decimal("0.01"), rounding=rounding_mode)

    emi = numerator / denominator
    return emi.quantize(Decimal("0.01"), rounding=rounding_mode)


def calculate_amortization_schedule_decimal(
    principal: Decimal | float | str,
    annual_rate: Decimal | float | str,
    tenure_months: int,
    moratorium_months: int = 0,
    rounding_mode=ROUND_HALF_UP,
) -> Dict[str, Any]:
    """
    Generates a full amortized repayment schedule using Decimal arithmetic.
    Accurately reconciles the final installment so that the sum of principal
    payments equals the exact initial principal with a final balance of 0.00.
    """
    P = Decimal(str(principal)).quantize(Decimal("0.01"), rounding=rounding_mode)
    rate = Decimal(str(annual_rate))
    n = int(tenure_months)
    m = max(0, int(moratorium_months))

    if P <= Decimal("0") or n <= 0:
        return {
            "principal": "0.00",
            "monthly_emi": "0.00",
            "total_interest": "0.00",
            "total_payment": "0.00",
            "schedule": [],
        }

    # Effective repayment tenure after moratorium (if applicable)
    active_tenure = max(1, n - m) if m < n else n
    monthly_rate = (rate / (Decimal("12") * Decimal("100"))) if rate > Decimal("0") else Decimal("0")

    # Regular monthly EMI for the active tenure
    regular_emi = calculate_precise_emi(P, rate, active_tenure, rounding_mode=rounding_mode)

    current_balance = P
    total_interest = Decimal("0.00")
    total_principal_paid = Decimal("0.00")
    schedule: List[Dict[str, Any]] = []

    for month in range(1, n + 1):
        is_moratorium = month <= m

        if is_moratorium:
            # During moratorium: interest accrual/payment only, principal payment is zero
            interest_component = (current_balance * monthly_rate).quantize(Decimal("0.01"), rounding=rounding_mode)
            principal_component = Decimal("0.00")
            installment = interest_component
            closing_balance = current_balance
        else:
            interest_component = (current_balance * monthly_rate).quantize(Decimal("0.01"), rounding=rounding_mode)
            installment = regular_emi
            principal_component = installment - interest_component

            # Balancing final installment or when principal component exceeds balance
            if month == n or principal_component >= current_balance:
                principal_component = current_balance
                installment = principal_component + interest_component
                closing_balance = Decimal("0.00")
            else:
                closing_balance = current_balance - principal_component

        total_interest += interest_component
        total_principal_paid += principal_component
        current_balance = closing_balance

        schedule.append({
            "month": month,
            "is_moratorium": is_moratorium,
            "installment": str(installment.quantize(Decimal("0.01"), rounding=rounding_mode)),
            "principal_component": str(principal_component.quantize(Decimal("0.01"), rounding=rounding_mode)),
            "interest_component": str(interest_component.quantize(Decimal("0.01"), rounding=rounding_mode)),
            "remaining_balance": str(closing_balance.quantize(Decimal("0.01"), rounding=rounding_mode)),
        })

    total_payment = P + total_interest

    return {
        "principal": str(P),
        "annual_interest_rate": str(rate),
        "tenure_months": n,
        "moratorium_months": m,
        "monthly_emi": str(regular_emi),
        "total_interest": str(total_interest.quantize(Decimal("0.01"), rounding=rounding_mode)),
        "total_payment": str(total_payment.quantize(Decimal("0.01"), rounding=rounding_mode)),
        "schedule": schedule,
    }
