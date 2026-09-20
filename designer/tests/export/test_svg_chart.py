"""Тесты SVG-диаграмм экспорта в HTML. Задача T-06."""
from designer.contracts import ChartSpec, ColorToken, Margins, Series, Tokens
from designer.export.svg_chart import chart_colors, render_chart


def _tokens_with_colors() -> Tokens:
    return Tokens(
        colors=[
            ColorToken(hex="112233", role="background", share=0.4, source="theme"),
            ColorToken(hex="AABBCC", role="accent", share=0.1, source="usage"),
            ColorToken(hex="334455", role="accent_alt", share=0.05, source="usage"),
            ColorToken(hex="556677", role="text", share=0.3, source="theme"),
            ColorToken(hex="778899", role="other", share=0.15, source="usage"),
        ],
        fonts=[],
        type_scale=[],
        margins=Margins(left=0, top=0, right=0, bottom=0),
    )


def test_chart_colors_order_accent_first_then_share():
    colors = chart_colors(_tokens_with_colors())
    assert colors[0] == "AABBCC"
    assert colors[1] == "334455"
    # остальные токены по убыванию доли: background(0.4), text(0.3), other(0.15)
    assert colors[2:] == ["112233", "556677", "778899"]


def test_chart_colors_fallback_when_no_tokens():
    empty = Tokens(colors=[], fonts=[], type_scale=[], margins=Margins(left=0, top=0, right=0, bottom=0))
    colors = chart_colors(empty)
    assert colors


def test_column_chart_bar_count_matches_data():
    spec = ChartSpec(
        type="column",
        title="Выручка",
        unit="млн Р",
        categories=["янв", "фев", "мар"],
        series=[Series(name="план", values=[1, 2, 3]), Series(name="факт", values=[1.5, 1.8, 2.9])],
    )
    svg = render_chart(spec, ["AABBCC", "334455"])
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert svg.count('class="chart-bar"') == len(spec.categories) * len(spec.series)
    assert 'class="chart-legend"' in svg
    assert "Выручка" in svg
    assert "млн Р" in svg


def test_bar_chart_single_series_has_no_legend():
    spec = ChartSpec(type="bar", categories=["a", "b"], series=[Series(name="s", values=[1, 2])])
    svg = render_chart(spec, ["AABBCC"])
    assert svg.count('class="chart-bar"') == 2
    assert 'class="chart-legend"' not in svg


def test_line_chart_has_one_path_per_series():
    spec = ChartSpec(
        type="line", categories=["a", "b", "c"],
        series=[Series(name="s1", values=[1, 2, 3]), Series(name="s2", values=[3, 2, 1])],
    )
    svg = render_chart(spec, ["AABBCC", "334455"])
    assert svg.count('class="chart-line"') == 2


def test_pie_chart_one_slice_per_category():
    spec = ChartSpec(type="pie", categories=["a", "b", "c"], series=[Series(name="s", values=[1, 2, 3])])
    svg = render_chart(spec, ["AABBCC", "334455", "556677"])
    assert svg.count('class="chart-slice"') == 3


def test_donut_chart_marked_with_own_class():
    spec = ChartSpec(type="donut", categories=["a", "b"], series=[Series(name="s", values=[1, 1])])
    svg = render_chart(spec, ["AABBCC", "334455"])
    assert "chart-donut" in svg


def test_chart_escapes_html_in_category_labels():
    spec = ChartSpec(type="column", categories=["<script>alert(1)</script>"], series=[Series(name="s", values=[1])])
    svg = render_chart(spec, ["AABBCC"])
    assert "<script>alert(1)</script>" not in svg
    assert "&lt;script&gt;" in svg
