from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Union


def inr_currency(value: Union[Decimal, float, int, str, None], show_symbol: bool = True) -> str:
    """
    Formats a monetary value using the Indian Numbering System (e.g., ₹1,00,000.00).
    Uses Python Decimal arithmetic with exact 2-decimal precision.
    
    Examples:
        inr_currency(100) -> "₹100.00"
        inr_currency(1000) -> "₹1,000.00"
        inr_currency(25000) -> "₹25,000.00"
        inr_currency(100000) -> "₹1,00,000.00"
        inr_currency(1234567.89) -> "₹12,34,567.89"
        inr_currency(-50000) -> "-₹50,000.00"
    """
    if value is None or value == "":
        return "₹0.00" if show_symbol else "0.00"

    try:
        dec = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return "₹0.00" if show_symbol else "0.00"

    is_negative = dec < Decimal("0")
    abs_dec = abs(dec)

    str_val = f"{abs_dec:.2f}"
    int_part, dec_part = str_val.split(".")

    if len(int_part) <= 3:
        formatted_int = int_part
    else:
        last_three = int_part[-3:]
        remaining = int_part[:-3]
        pairs = []
        while remaining:
            pairs.append(remaining[-2:])
            remaining = remaining[:-2]
        pairs.reverse()
        formatted_int = ",".join(pairs) + "," + last_three

    result = f"{formatted_int}.{dec_part}"
    if is_negative:
        return f"-₹{result}" if show_symbol else f"-{result}"
    return f"₹{result}" if show_symbol else result


def parse_inr(value: Union[str, float, int, Decimal]) -> Decimal:
    """
    Safely parses an INR currency string (which may contain ₹ or commas) into a 2-decimal Decimal.
    """
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if value is None:
        return Decimal("0.00")

    clean_str = str(value).replace("₹", "").replace(",", "").strip()
    if not clean_str:
        return Decimal("0.00")

    try:
        return Decimal(clean_str).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return Decimal("0.00")
