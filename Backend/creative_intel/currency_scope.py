"""Pure currency classification for pooled native monetary amounts."""


def currency_breakdown(rows):
    """Distinct non-blank currency codes, with whitespace/case normalized."""
    return sorted({str((row or {}).get("currency") or "").strip().upper()
                   for row in rows or []
                   if str((row or {}).get("currency") or "").strip()})


def money_scope(rows):
    """Classify a pool without assuming the denomination of an unknown amount.

    A nonzero spend or revenue contribution with no currency prevents a
    known-currency pool from being labeled or compared as one denomination.
    Unknown rows whose monetary values are both zero do not add an unknown
    amount. Check each row, so offsetting unknown amounts cannot hide this.

    Preserve the documented legacy calculation policy for wholly unspecified
    currency scopes. Such a scope is still currency_known=False; allowing its
    legacy arithmetic does not establish a known monetary denomination.
    """
    rows = list(rows or [])
    currencies = currency_breakdown(rows)
    unknown_contribution = any(
        not str((row or {}).get("currency") or "").strip()
        and any((row or {}).get(field) not in (None, 0)
                for field in ("spend", "revenue"))
        for row in rows
    )
    mixed = len(currencies) > 1 or bool(currencies and unknown_contribution)
    known = len(currencies) == 1 and not unknown_contribution
    return {
        "currency": currencies[0] if known else None,
        "currencies": currencies,
        "mixed_currency": mixed,
        "currency_known": known,
        "unknown_currency_contribution": unknown_contribution,
    }
