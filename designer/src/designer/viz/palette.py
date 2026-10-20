"""Палитра цветов рядов и контрастный текст для заливки. Владелец: задача T-05."""
from __future__ import annotations

import colorsys
import math
from functools import lru_cache

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


MIN_CHART_CONTRAST = 3.0
MIN_CHART_DISTANCE = 0.10
_FALLBACK_CHART_COLORS = ("4C6EF5", "F76707", "2F9E44", "E8590C", "1098AD", "AE3EC9")


def chart_background(tokens: Tokens, theme: str = "light", background: str | None = None) -> str:
    """The actual solid slide override wins over extracted theme tokens."""
    return (background or _theme_background(tokens, theme) or
            ("000000" if theme == "dark" else "FFFFFF")).lstrip("#").upper()


@lru_cache(maxsize=2048)
def _oklab(color: str) -> tuple[float, float, float]:
    channels = [int(color[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    r, g, b = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in channels]
    l = (.4122214708 * r + .5363325363 * g + .0514459929 * b) ** (1 / 3)
    m = (.2119034982 * r + .6806995451 * g + .1073969566 * b) ** (1 / 3)
    s = (.0883024619 * r + .2817188376 * g + .6299787005 * b) ** (1 / 3)
    return (.2104542553 * l + .7936177850 * m - .0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + .4505937099 * s,
            .0259040371 * l + .7827717662 * m - .8086757660 * s)


def chart_color_distance(first: str, second: str) -> float:
    """Euclidean OKLab distance: a bounded distinctness heuristic, not a CVD guarantee."""
    return math.dist(_oklab(first.lstrip("#").upper()), _oklab(second.lstrip("#").upper()))


@lru_cache(maxsize=256)
def _contrasting_colors(ordered: tuple[str, ...], background: str, count: int) -> tuple[str, ...]:
    ordered = ordered or _FALLBACK_CHART_COLORS
    # Reserve readable originals before generating replacements, so a replacement
    # cannot steal the color of a later, already readable brand accent.
    colors: list[str | None] = []
    kept: list[str] = []
    for color in ordered[:count]:
        good = contrast_ratio(color, background) >= MIN_CHART_CONTRAST and all(
            chart_color_distance(color, old) >= MIN_CHART_DISTANCE for old in kept)
        colors.append(color if good else None)
        if good:
            kept.append(color)
    colors.extend([None] * (count - len(colors)))
    # A monochrome/white accidental accent has no useful hue: find a chromatic
    # brand token before using the shared default. Derive lightness/saturation
    # variations first; rotate hue only when that gamut is exhausted.
    seed = next((color for color in ordered if max(_channel(color, i) for i in range(3)) -
                 min(_channel(color, i) for i in range(3)) > 24), "4C6EF5")
    hue, _, saturation = colorsys.rgb_to_hls(*(_channel(seed, i) / 255 for i in range(3)))
    groups = []
    for shifts in ((0,), (1/12, -1/12, 1/6, -1/6), (1/3, -1/3, 1/2, 1/4, -1/4, 5/12, -5/12)):
        candidates = []
        for shift in shifts:
            for lightness in (.18, .28, .38, .48, .58, .68, .78, .88):
                for sat in (max(.5, saturation), .65, .35):
                    color = "".join(f"{round(v * 255):02X}" for v in colorsys.hls_to_rgb(
                        (hue + shift) % 1, lightness, sat))
                    if contrast_ratio(color, background) >= MIN_CHART_CONTRAST:
                        candidates.append(color)
        groups.append(sorted(set(candidates)))
    for index, color in enumerate(colors):
        if color is not None:
            continue
        for group in groups:
            valid = [candidate for candidate in group if all(
                chart_color_distance(candidate, other) >= MIN_CHART_DISTANCE for other in kept)]
            if valid:
                # Maximum separation within the closest available brand hue family.
                replacement = max(valid, key=lambda c: min(
                    (chart_color_distance(c, old) for old in kept), default=1))
                colors[index] = replacement
                kept.append(replacement)
                break
        else:
            raise ValueError("Too many chart colors to distinguish against this background; split the chart")
    return tuple(colors)


def contrasting_chart_colors(colors: list[str], background: str = "FFFFFF", count: int | None = None) -> list[str]:
    """Shared by native PPTX and SVG; never repeat one fill for multiple series."""
    normalized = tuple(color.lstrip("#").upper() for color in colors)
    return list(_contrasting_colors(normalized, background.lstrip("#").upper(), max(1, count or len(colors) or 6)))


def chart_series_colors(tokens: Tokens, theme: str = "light", background: str | None = None,
                        count: int | None = None) -> list[str]:
    return contrasting_chart_colors(series_colors(tokens), chart_background(tokens, theme, background), count)


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
