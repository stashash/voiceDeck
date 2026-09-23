"""Тесты экспорта колоды в самодостаточный HTML. Задача T-06."""
import pytest
from lxml import html as lxml_html
from PIL import Image

from designer.contracts import (
    Asset, ChartSpec, ColorToken, Deck, DeckPlan, DesignSystem, Element, FontToken,
    Margins, Scene, Series, SlideIntent, SlideKind, TableSpec, TextStyle, Tokens, TypeStep,
)
from designer.export.html import render_deck


@pytest.fixture
def package_dir(tmp_path):
    """Временный пакет дизайн-системы: картинка 2x2 пикселя, без шрифта."""
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    Image.new("RGB", (2, 2), color=(10, 20, 30)).save(assets_dir / "bg.png")
    return tmp_path


def _design_system() -> DesignSystem:
    tokens = Tokens(
        colors=[
            ColorToken(hex="0B0B12", role="background", share=0.5, source="theme"),
            ColorToken(hex="FFFFFF", role="text", share=0.3, source="theme"),
            ColorToken(hex="4C6EF5", role="accent", share=0.1, source="usage"),
            ColorToken(hex="F76707", role="accent_alt", share=0.1, source="usage"),
        ],
        fonts=[FontToken(family="Inter", role="body", share=1.0)],
        type_scale=[
            TypeStep(size_pt=44, role="display", share=0.1),
            TypeStep(size_pt=16, role="body", share=0.6),
        ],
        margins=Margins(left=0.05, top=0.05, right=0.05, bottom=0.05),
    )
    return DesignSystem(
        id="ds-test",
        source_file="test.pptx",
        slide_size_emu=(12192000, 6858000),
        tokens=tokens,
        assets=[
            Asset(id="bg", path="assets/bg.png", kind="background", width_px=2, height_px=2,
                  sha1="0" * 40, used_on=[1]),
        ],
    )


def _deck() -> Deck:
    plan = DeckPlan(
        title="Тестовая колода", purpose="демонстрация экспорта",
        slides=[
            SlideIntent(id="s1", kind=SlideKind.title, title="Заголовок"),
            SlideIntent(id="s2", kind=SlideKind.chart, title="График"),
            SlideIntent(id="s3", kind=SlideKind.table, title="Таблица"),
        ],
    )
    scene1 = Scene(
        slide_id="s1", pattern_id="p1", theme="dark", background_asset="bg",
        elements=[
            Element(id="e1", type="text", role="title", box=(0.1, 0.1, 0.8, 0.2), z=1,
                    text="<script>alert(1)</script>", style=TextStyle(size_pt=44, bold=True, color="FFFFFF")),
            Element(id="e2", type="text", role="body", box=(0.1, 0.35, 0.8, 0.1), z=1,
                    text="Подзаголовок слайда"),
        ],
    )
    chart_spec = ChartSpec(
        type="column", title="Динамика", unit="шт.",
        categories=["янв", "фев", "мар"],
        series=[Series(name="план", values=[1, 2, 3]), Series(name="факт", values=[1.2, 1.9, 2.8])],
    )
    scene2 = Scene(
        slide_id="s2", pattern_id="p2", theme="light", background_color="FFFFFF",
        elements=[Element(id="e3", type="chart", role="other", box=(0.1, 0.2, 0.8, 0.6), z=1, chart=chart_spec)],
    )
    table_spec = TableSpec(
        columns=["Метрика", "Значение"],
        rows=[["Охват", "120"], ["Конверсия", "4%"], ["Возврат", "12%"]],
    )
    scene3 = Scene(
        slide_id="s3", pattern_id="p3", theme="light", background_color="FFFFFF",
        elements=[Element(id="e4", type="table", role="other", box=(0.1, 0.2, 0.8, 0.5), z=1, table=table_spec)],
    )
    return Deck(id="deck-test", design_system_id="ds-test", variant="a", plan=plan, scenes=[scene1, scene2, scene3])


def test_render_deck_has_three_slide_sections(package_dir):
    out = render_deck(_deck(), _design_system(), package_dir)
    doc = lxml_html.fromstring(out)
    assert len(doc.xpath("//section[contains(concat(' ', @class, ' '), ' slide ')]")) == 3


def test_slide_text_present_and_script_escaped(package_dir):
    out = render_deck(_deck(), _design_system(), package_dir)
    assert "<script>alert(1)</script>" not in out
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in out
    assert "Подзаголовок слайда" in out
    doc = lxml_html.fromstring(out)
    # экранированный текст остался текстом, не превратился в собственный тег script
    assert len(doc.xpath('//script')) == 1


def test_chart_svg_has_columns_matching_data(package_dir):
    deck = _deck()
    out = render_deck(deck, _design_system(), package_dir)
    doc = lxml_html.fromstring(out)
    chart_scene = doc.xpath('//section[@id="slide-2"]')[0]
    svgs = chart_scene.xpath('.//*[local-name()="svg"]')
    assert len(svgs) == 1
    bars = chart_scene.xpath('.//*[local-name()="rect" and contains(@class, "chart-bar")]')
    chart_spec = deck.scenes[1].elements[0].chart
    assert len(bars) == len(chart_spec.categories) * len(chart_spec.series)


def test_table_has_expected_row_count(package_dir):
    deck = _deck()
    out = render_deck(deck, _design_system(), package_dir)
    doc = lxml_html.fromstring(out)
    rows = doc.xpath('//section[@id="slide-3"]//table/tbody/tr')
    table_spec = deck.scenes[2].elements[0].table
    assert len(rows) == len(table_spec.rows)


def test_no_network_references(package_dir):
    out = render_deck(_deck(), _design_system(), package_dir)
    assert "http://" not in out
    assert "https://" not in out


def test_print_media_present(package_dir):
    out = render_deck(_deck(), _design_system(), package_dir)
    assert "@media print" in out


def test_background_image_embedded_as_data_uri(package_dir):
    out = render_deck(_deck(), _design_system(), package_dir)
    assert "data:image/png;base64," in out
