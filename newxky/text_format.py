"""Safe emphasis for the fallback answer-order warning."""
from html import escape


def emphasize_bank_order(text: str, *, warning: bool = False) -> str:
    formatted = escape(text).replace(
        "题库顺序", '<span style="color:#c62828;font-weight:700;">题库顺序</span>'
    ).replace("\n", "<br>")
    return f'<span style="color:#c62828;font-weight:700;">{formatted}</span>' if warning else formatted
