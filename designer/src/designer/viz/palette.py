"""Палитра цветов рядов и контрастный текст для заливки. Владелец: задача T-05."""
from __future__ import annotations

from designer.contracts import Tokens

_EXCLUDED_ROLES = {"background", "text", "text_muted"}


def series_colors(tokens: Tokens) -> list[str]:
    """Цвета рядов: accent, accent_alt, затем остальные по убыванию доли.

    Фон и цвет текста в ряды не идут, дубликаты убраны.
    """
    accent = [c.hex for c in tokens.colors if c.role == "accent"]
    accent_alt = [c.hex for c in tokens.colors if c.role == "accent_alt"]
    rest = sorted(
        (c for c in tokens.colors if c.role not in _EXCLUDED_ROLES and c.role not in ("accent", "accent_alt")),
        key=lambda c: c.share,
        reverse=True,
    )
    ordered = [*accent, *accent_alt, *(c.hex for c in rest)]

    seen: set[str] = set()
    colors: list[str] = []
    for hex_value in ordered:
        if hex_value not in seen:
            seen.add(hex_value)
            colors.append(hex_value)
    return colors


def contrast_text_color(hex_color: str) -> str:
    """Белый или чёрный текст, смотря что читается лучше на заливке hex_color."""
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "000000" if luminance > 0.5 else "FFFFFF"
