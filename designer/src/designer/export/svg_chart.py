"""Диаграммы SVG для HTML-экспорта. Владелец: задача T-06."""
from __future__ import annotations

import html
import math

from designer.contracts import ChartSpec, Tokens

_VIEW_W = 600.0
_VIEW_H = 360.0
_PAD_LEFT = 50.0
_PAD_RIGHT = 20.0
_PAD_TOP = 20.0
_PAD_BOTTOM = 50.0
_LEGEND_H = 24.0

_FALLBACK_COLORS = ["4C6EF5", "F76707", "2F9E44", "E8590C", "1098AD", "AE3EC9"]


def chart_colors(tokens: Tokens) -> list[str]:
    """Цвета рядов: accent, accent_alt, затем остальные токены по убыванию доли."""
    by_role: dict[str, str] = {}
    for color in tokens.colors:
        by_role.setdefault(color.role, color.hex)
    ordered: list[str] = []
    if "accent" in by_role:
        ordered.append(by_role["accent"])
    if "accent_alt" in by_role:
        ordered.append(by_role["accent_alt"])
    rest = sorted(
        (c for c in tokens.colors if c.role not in ("accent", "accent_alt")),
        key=lambda c: c.share,
        reverse=True,
    )
    for color in rest:
        if color.hex not in ordered:
            ordered.append(color.hex)
    return ordered or list(_FALLBACK_COLORS)


def _color(colors: list[str], i: int) -> str:
    return "#" + colors[i % len(colors)].lstrip("#")


def _max_value(spec: ChartSpec) -> float:
    values = [v for series in spec.series for v in series.values]
    return max(values) if values else 1.0


def _legend_items(names: list[str], colors: list[str], y: float) -> str:
    if len(names) < 2:
        return ""
    parts: list[str] = []
    x = _PAD_LEFT
    for i, name in enumerate(names):
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="12" height="12" fill="{_color(colors, i)}"/>'
            f'<text x="{x + 16:.1f}" y="{y + 10:.1f}" class="chart-legend">{html.escape(name)}</text>'
        )
        x += 32 + len(name) * 7
    return "".join(parts)


def _svg_wrap(body: str, kind: str, spec: ChartSpec, legend: str) -> str:
    title = (
        f'<text x="{_PAD_LEFT:.1f}" y="16" class="chart-title">{html.escape(spec.title)}</text>'
        if spec.title else ""
    )
    unit = (
        f'<text x="{_VIEW_W - _PAD_RIGHT:.1f}" y="16" class="chart-unit" text-anchor="end">'
        f"{html.escape(spec.unit)}</text>"
        if spec.unit else ""
    )
    return (
        f'<svg viewBox="0 0 {_VIEW_W:.0f} {_VIEW_H:.0f}" class="chart chart-{kind}" '
        f'preserveAspectRatio="xMidYMid meet" role="img">'
        f"{title}{unit}{body}{legend}</svg>"
    )


def _fraction(value: float, low: float, high: float) -> float:
    scale = max(abs(low), abs(high), 1e-300)
    return (value / scale - low / scale) / (high / scale - low / scale)


def _domain(values: list[float], zero: bool = False) -> tuple[float, float]:
    low, high = min(values), max(values)
    if zero or low == high:
        low, high = min(low, 0), max(high, 0)
    return (low, high) if low != high else (-1.0, 1.0)


def _y_ticks(low: float, high: float, plot_h: float) -> str:
    return "".join(
        f'<text x="{_PAD_LEFT - 6:.1f}" y="{_PAD_TOP + plot_h * (1 - i / 4):.1f}" '
        f'class="chart-label" text-anchor="end">{low * (1 - i / 4) + high * (i / 4):.4g}</text>'
        for i in range(5)
    )


def _render_columns(spec: ChartSpec, colors: list[str]) -> str:
    n_cat = len(spec.categories)
    n_series = len(spec.series)
    stacked = spec.type == "stacked_column"
    values = ([sum(s.values[i] for s in spec.series) for i in range(n_cat)] if stacked
              else [v for s in spec.series for v in s.values])
    low, high = _domain(values or [0], zero=True)
    has_legend = n_series >= 2
    legend = _legend_items([s.name for s in spec.series], colors, _VIEW_H - _LEGEND_H + 8) if has_legend else ""
    plot_h = _VIEW_H - _PAD_TOP - _PAD_BOTTOM - (_LEGEND_H if has_legend else 0)
    plot_w = _VIEW_W - _PAD_LEFT - _PAD_RIGHT
    group_w = plot_w / max(n_cat, 1)
    bar_w = (group_w * 0.7) / (1 if stacked else max(n_series, 1))
    bars: list[str] = []
    labels: list[str] = []
    for ci, category in enumerate(spec.categories):
        group_x = _PAD_LEFT + ci * group_w + group_w * 0.15
        total = 0.0
        for si, series in enumerate(spec.series):
            value = series.values[ci] if ci < len(series.values) else 0.0
            start, end = (total, total + value) if stacked else (0.0, value)
            total = end
            y1 = _PAD_TOP + (1 - _fraction(start, low, high)) * plot_h
            y2 = _PAD_TOP + (1 - _fraction(end, low, high)) * plot_h
            bar_h = abs(y2 - y1)
            x = group_x if stacked else group_x + si * bar_w
            y = min(y1, y2)
            bars.append(
                f'<rect class="chart-bar" x="{x:.1f}" y="{y:.1f}" '
                f'width="{bar_w * 0.85:.1f}" height="{bar_h:.1f}" fill="{_color(colors, si)}">'
                f'<title>{html.escape(series.name)} · {html.escape(category)}: {value:g}</title></rect>'
            )
        labels.append(
            f'<text x="{group_x + group_w * 0.35:.1f}" y="{_PAD_TOP + plot_h + 16:.1f}" '
            f'class="chart-label" text-anchor="middle">{html.escape(category)}</text>'
        )
    baseline = _PAD_TOP + (1 - _fraction(0, low, high)) * plot_h
    axis = f'<line class="chart-axis" x1="{_PAD_LEFT}" x2="{_VIEW_W - _PAD_RIGHT}" y1="{baseline:.1f}" y2="{baseline:.1f}" stroke="currentColor"/>'
    return _svg_wrap(axis + _y_ticks(low, high, plot_h) + "".join(bars) + "".join(labels), spec.type, spec, legend)


def _render_scatter(spec: ChartSpec, colors: list[str]) -> str:
    has_legend = len(spec.series) >= 2
    plot_h = _VIEW_H - _PAD_TOP - _PAD_BOTTOM - (_LEGEND_H if has_legend else 0)
    plot_w = _VIEW_W - _PAD_LEFT - _PAD_RIGHT
    xmin, xmax = _domain([x for s in spec.series for x in s.x_values])
    ymin, ymax = _domain([y for s in spec.series for y in s.values])
    parts = [_y_ticks(ymin, ymax, plot_h)]
    parts.append(f'<path class="chart-axis" d="M {_PAD_LEFT} {_PAD_TOP} V {_PAD_TOP + plot_h} H {_PAD_LEFT + plot_w}" fill="none" stroke="currentColor"/>')
    for i in range(5):
        tick = xmin * (1 - i / 4) + xmax * (i / 4)
        parts.append(f'<text class="chart-label" x="{_PAD_LEFT + plot_w * i / 4:.1f}" y="{_PAD_TOP + plot_h + 16:.1f}" text-anchor="middle">{tick:.4g}</text>')
    for si, series in enumerate(spec.series):
        for x, y in zip(series.x_values, series.values):
            px = _PAD_LEFT + _fraction(x, xmin, xmax) * plot_w
            py = _PAD_TOP + (1 - _fraction(y, ymin, ymax)) * plot_h
            parts.append(f'<circle class="chart-point" cx="{px:.1f}" cy="{py:.1f}" r="4" fill="{_color(colors, si)}"><title>{html.escape(series.name)}: ({x:g}, {y:g})</title></circle>')
    parts.append(f'<text class="chart-label" x="{_PAD_LEFT + plot_w / 2:.1f}" y="{_PAD_TOP + plot_h + 34:.1f}" text-anchor="middle">{html.escape(spec.x_axis_title)}</text>')
    parts.append(f'<text class="chart-label" transform="translate(12 {_PAD_TOP + plot_h / 2:.1f}) rotate(-90)" text-anchor="middle">{html.escape(spec.y_axis_title or spec.unit)}</text>')
    legend = _legend_items([s.name for s in spec.series], colors, _VIEW_H - _LEGEND_H + 8)
    return _svg_wrap("".join(parts), "scatter", spec, legend)


def _render_bars(spec: ChartSpec, colors: list[str]) -> str:
    n_cat = len(spec.categories)
    n_series = len(spec.series)
    max_v = _max_value(spec)
    has_legend = n_series >= 2
    legend = _legend_items([s.name for s in spec.series], colors, _VIEW_H - _LEGEND_H + 8) if has_legend else ""
    plot_h = _VIEW_H - _PAD_TOP - _PAD_BOTTOM - (_LEGEND_H if has_legend else 0)
    plot_w = _VIEW_W - _PAD_LEFT - _PAD_RIGHT
    group_h = plot_h / max(n_cat, 1)
    bar_h = (group_h * 0.7) / max(n_series, 1)
    bars: list[str] = []
    labels: list[str] = []
    for ci, category in enumerate(spec.categories):
        group_y = _PAD_TOP + ci * group_h + group_h * 0.15
        for si, series in enumerate(spec.series):
            value = series.values[ci] if ci < len(series.values) else 0.0
            length = (value / max_v) * plot_w if max_v else 0.0
            y = group_y + si * bar_h
            bars.append(
                f'<rect class="chart-bar" x="{_PAD_LEFT:.1f}" y="{y:.1f}" '
                f'width="{length:.1f}" height="{bar_h * 0.85:.1f}" fill="{_color(colors, si)}"/>'
            )
        labels.append(
            f'<text x="{_PAD_LEFT - 6:.1f}" y="{group_y + group_h * 0.35:.1f}" '
            f'class="chart-label" text-anchor="end">{html.escape(category)}</text>'
        )
    return _svg_wrap("".join(bars) + "".join(labels), "bar", spec, legend)


def _render_line(spec: ChartSpec, colors: list[str]) -> str:
    n_cat = len(spec.categories)
    n_series = len(spec.series)
    max_v = _max_value(spec)
    has_legend = n_series >= 2
    legend = _legend_items([s.name for s in spec.series], colors, _VIEW_H - _LEGEND_H + 8) if has_legend else ""
    plot_h = _VIEW_H - _PAD_TOP - _PAD_BOTTOM - (_LEGEND_H if has_legend else 0)
    plot_w = _VIEW_W - _PAD_LEFT - _PAD_RIGHT
    step_x = plot_w / max(n_cat - 1, 1)
    paths: list[str] = []
    dots: list[str] = []
    for si, series in enumerate(spec.series):
        points: list[tuple[float, float]] = []
        for ci in range(n_cat):
            value = series.values[ci] if ci < len(series.values) else 0.0
            x = _PAD_LEFT + ci * step_x
            y = _PAD_TOP + plot_h - (value / max_v) * plot_h if max_v else _PAD_TOP + plot_h
            points.append((x, y))
        d = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in points)
        color = _color(colors, si)
        paths.append(f'<path class="chart-line" d="{d}" fill="none" stroke="{color}" stroke-width="2"/>')
        for x, y in points:
            dots.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{color}"/>')
    labels = [
        f'<text x="{_PAD_LEFT + ci * step_x:.1f}" y="{_PAD_TOP + plot_h + 16:.1f}" '
        f'class="chart-label" text-anchor="middle">{html.escape(category)}</text>'
        for ci, category in enumerate(spec.categories)
    ]
    return _svg_wrap("".join(paths) + "".join(dots) + "".join(labels), "line", spec, legend)


def _render_pie(spec: ChartSpec, colors: list[str], donut: bool) -> str:
    values = spec.series[0].values if spec.series else []
    total = sum(values) or 1.0
    cx, cy = _VIEW_W / 2, (_VIEW_H - _LEGEND_H) / 2
    r = min(_VIEW_W, _VIEW_H - _LEGEND_H) / 2 - 30
    inner_r = r * 0.55 if donut else 0.0
    slices: list[str] = []
    angle = -math.pi / 2
    for i, value in enumerate(values):
        frac = value / total
        sweep = frac * 2 * math.pi
        x0, y0 = cx + r * math.cos(angle), cy + r * math.sin(angle)
        x1, y1 = cx + r * math.cos(angle + sweep), cy + r * math.sin(angle + sweep)
        large_arc = 1 if sweep > math.pi else 0
        color = _color(colors, i)
        if donut:
            ix0, iy0 = cx + inner_r * math.cos(angle), cy + inner_r * math.sin(angle)
            ix1, iy1 = cx + inner_r * math.cos(angle + sweep), cy + inner_r * math.sin(angle + sweep)
            path = (
                f"M {x0:.1f} {y0:.1f} A {r:.1f} {r:.1f} 0 {large_arc} 1 {x1:.1f} {y1:.1f} "
                f"L {ix1:.1f} {iy1:.1f} A {inner_r:.1f} {inner_r:.1f} 0 {large_arc} 0 {ix0:.1f} {iy0:.1f} Z"
            )
        else:
            path = (
                f"M {cx:.1f} {cy:.1f} L {x0:.1f} {y0:.1f} "
                f"A {r:.1f} {r:.1f} 0 {large_arc} 1 {x1:.1f} {y1:.1f} Z"
            )
        slices.append(f'<path class="chart-slice" d="{path}" fill="{color}"/>')
        angle += sweep
    legend = _legend_items(spec.categories, colors, _VIEW_H - _LEGEND_H + 8)
    return _svg_wrap("".join(slices), "donut" if donut else "pie", spec, legend)


def render_chart(spec: ChartSpec, colors: list[str]) -> str:
    """Возвращает встраиваемый <svg>...</svg> для диаграммы spec.type."""
    if not colors:
        colors = list(_FALLBACK_COLORS)
    if spec.type in {"column", "grouped_column", "stacked_column"}:
        return _render_columns(spec, colors)
    if spec.type == "bar":
        return _render_bars(spec, colors)
    if spec.type == "line":
        return _render_line(spec, colors)
    if spec.type == "scatter":
        return _render_scatter(spec, colors)
    if spec.type in {"pie", "donut"}:
        return _render_pie(spec, colors, donut=(spec.type == "donut"))
    raise ValueError(f"Unsupported chart type: {spec.type}")
