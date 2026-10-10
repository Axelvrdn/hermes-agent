"""Safe opt-in Discord Components V2 static text payloads.

Only a returned HTTP client rejection proves that Discord did not create a message.
A timeout, transport error or server response does not justify replaying legacy.
"""

from __future__ import annotations

from typing import Any


def static_text_view(discord_module: Any, text: str) -> Any | None:
    """Construct a static layout without silently clipping the visible text."""
    if not text or len(text) > 4000:
        return None
    ui = getattr(discord_module, "ui", None)
    layout = getattr(ui, "LayoutView", None)
    display = getattr(ui, "TextDisplay", None)
    if not isinstance(layout, type) or not isinstance(display, type):
        return None
    try:
        view = layout(timeout=None)
        view.add_item(display(text))
        return view
    except (TypeError, ValueError, AttributeError):
        return None


def definitely_rejected(exc: Exception) -> bool:
    """Retry only explicit Discord client-side 4xx errors (excluding 429)."""
    status = getattr(exc, "status", None)
    return isinstance(status, int) and 400 <= status < 500 and status != 429
