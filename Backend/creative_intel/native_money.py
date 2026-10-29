"""Compact native-money labels without an assumed denomination or conversion."""

import math


def compact_money(value, currency):
    """Format a finite amount with its explicit currency, or mark it unknown."""
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return "unavailable"
    if not math.isfinite(number):
        return "unavailable"
    amount = f"{number:.2f}"
    for unit, factor in (("M", 1_000_000.0), ("K", 1_000.0)):
        if abs(number) >= factor:
            text = f"{number / factor:.1f}".rstrip("0").rstrip(".")
            amount = f"{text}{unit}"
            break
    code = currency.strip().upper() if isinstance(currency, str) else ""
    return f"{code} {amount}" if code else f"{amount} (currency unknown)"
