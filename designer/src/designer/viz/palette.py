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


def _channel(hex_color: str, index: int) -> int:
    return int(hex_color[index * 2:index * 2 + 2], 16)


def _relative_luminance(hex_color: str) -> float:
    """Относительная яркость WCAG: линеаризованные каналы, вес по BT.709."""
    def linear(channel: int) -> float:
        c = channel / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (_channel(hex_color, i) for i in range(3))
    return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b)


def contrast_ratio(hex_a: str, hex_b: str) -> float:
    """Контраст WCAG между двумя цветами: от 1 (одинаковые) до 21 (чёрный на белом)."""
    la, lb = _relative_luminance(hex_a), _relative_luminance(hex_b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def is_dark(hex_color: str) -> bool:
    """Цвет тёмный, если его яркость ниже середины шкалы."""
    return _relative_luminance(hex_color) < 0.5


def _theme_background(tokens: Tokens, theme: str) -> str | None:
    """Фон темы: самый тёмный фоновый токен для dark, самый светлый для light."""
    backgrounds = [c.hex for c in tokens.colors if c.role == "background"]
    if not backgrounds:
        return None
    pick = min if theme == "dark" else max
    return pick(backgrounds, key=_relative_luminance)


def theme_text_color(tokens: Tokens, theme: str) -> str | None:
    """Цвет текста из токенов с наибольшим контрастом к фону темы. Имя роли не участвует в выборе."""
    bg = _theme_background(tokens, theme)
    if bg is None or not tokens.colors:
        return None
    return max((c.hex for c in tokens.colors), key=lambda hex_value: contrast_ratio(hex_value, bg))


def muted_gridline_color(tokens: Tokens, theme: str) -> str | None:
    """Приглушённый светлый цвет линий сетки для тёмной темы: текстовый цвет, сдвинутый к фону."""
    text_hex = theme_text_color(tokens, theme)
    bg = _theme_background(tokens, theme)
    if text_hex is None or bg is None:
        return None
    weight = 0.4
    parts = (round(_channel(text_hex, i) + (_channel(bg, i) - _channel(text_hex, i)) * weight) for i in range(3))
    return "".join(f"{value:02X}" for value in parts)
