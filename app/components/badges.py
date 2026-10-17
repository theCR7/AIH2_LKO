"""Risk/status badge helpers for the UI.

Thin wrappers over the colour tokens in :mod:`app.components.styles` so pages
and (later) the Investigate view share one badge look.
"""

from __future__ import annotations

from app.components.styles import TOKENS, band_color, risk_badge  # re-export

__all__ = ["TOKENS", "band_color", "risk_badge", "status_badge"]


def status_badge(status: str) -> str:
    """Return an HTML pill for a case status (New / In Review / Approved / Rejected)."""
    colors = {
        "New": TOKENS["accent"],
        "In Review": TOKENS["risk_medium"],
        "Approved": TOKENS["risk_low"],
        "Rejected": TOKENS["risk_high"],
    }
    color = colors.get(status, "#64748B")
    return f'<span class="rs-badge" style="background:{color}">{status}</span>'
