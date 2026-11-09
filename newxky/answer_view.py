"""Render a bank answer in bank order: stem first, then every option.

This build never prints the letters of the exam page. The exam may reorder its
options, so the only honest output is the question bank's own text with its own
letters, plus a standing warning that the page order may differ.
"""
from __future__ import annotations

from html import escape

from .models import Question

NOTICE = "题库答案请注意实际考题顺序"
SIMILAR_STATUSES = frozenset({"candidate", "unverified"})


def banner(status: str) -> str:
    """Standing warning shown above the answer block."""
    suffix = "（相似题，请核对题干）" if status in SIMILAR_STATUSES else ""
    return (
        "<span style=\"color:#b42318;font-weight:700;font-size:15px;\">"
        f"{NOTICE}{suffix}</span>"
    )


def render(question: Question) -> str:
    """Rich text: the bank stem, then A/B/C/D with the correct ones highlighted."""
    correct = set(question.answers)
    rows = []
    for letter, value in question.options.items():
        if letter in correct:
            rows.append(
                "<div style=\"background:#eaf7f1;border-left:6px solid #0b8c78;"
                "border-radius:6px;padding:9px 12px;margin:7px 0;\">"
                "<span style=\"color:#075e50;font-weight:700;font-size:17px;\">"
                f"{escape(letter)}.</span> "
                "<span style=\"color:#04564a;font-weight:700;font-size:17px;\">"
                f"{escape(value)}</span></div>"
            )
        else:
            rows.append(
                "<div style=\"color:#40566b;padding:6px 12px;margin:5px 0;\">"
                f"<b>{escape(letter)}.</b> {escape(value)}</div>"
            )
    stem = escape(question.stem).replace("\n", "<br>")
    return (
        "<div style=\"line-height:1.6;\">"
        "<div style=\"color:#182c43;font-size:15px;margin-bottom:10px;\">"
        f"{stem}</div>"
        + "".join(rows)
        + "</div>"
    )
