"""French number formatting for templates (1 234,56 €)."""
from __future__ import annotations

from jinja2 import Undefined

NNBSP = " "  # narrow no-break space, the French thousands separator


def _blank(value) -> bool:
    return value is None or value == "" or isinstance(value, Undefined)


def fr_num(value, decimals: int = 0, empty: str = "—") -> str:
    if _blank(value):
        return empty
    try:
        v = float(value)
    except (TypeError, ValueError):
        return empty
    s = f"{v:,.{decimals}f}"
    return s.replace(",", NNBSP).replace(".", ",")


def fr_money(value, decimals: int = 2, empty: str = "—") -> str:
    out = fr_num(value, decimals, empty)
    return out if out == empty else f"{out}{NNBSP}€"


def input_num(value) -> str:
    """Value for an <input type=number>: '12' not '12.0', '' for None."""
    if _blank(value):
        return ""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return ""
    if v.is_integer():
        return str(int(v))
    return f"{v:.4f}".rstrip("0").rstrip(".")
