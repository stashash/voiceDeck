"""Тесты вида слайда в браузере: картинка и текстовый слой поверх неё. Задача T-26."""
from __future__ import annotations

import base64

from lxml import html as lxml_html

from designer.contracts import (
    ChartSpec, ColorToken, Deck, DeckPlan, DesignSystem, Element, FontToken, Margins, Scene,
    Series, SlideIntent, SlideKind, TextStyle, Tokens, TypeStep,
)
from designer.export.html_image import render_deck_images, slide_html

PNG_ONE = b"\x89PNG\r\n\x1a\n\x01"
PNG_TWO = b"\x89PNG\r\n\x1a\n\x02"


def _design_system() -> DesignSystem:
    tokens = Tokens(
        colors=[
            ColorToken(hex="0B0B12", role="background", share=0.6, source="theme"),
            ColorToken(hex="FFFFFF", role="text", share=0.4, source="theme"),
        ],
        fonts=[FontToken(family="Inter", role="body", share=1.0)],
        type_scale=[
            TypeStep(size_pt=44, role="display", share=0.2),
            TypeStep(size_pt=16, role="body", share=0.8),
        ],
        margins=Margins(left=0.05, top=0.05, right=0.05, bottom=0.05),
    )
    return DesignSystem(id="ds-test", source_file="test.pptx",
                         slide_size_emu=(12192000, 6858000), tokens=tokens)


def _scene(slide_id: str = "s1") -> Scene:
    chart = ChartSpec(type="column", categories=["янв"], series=[Series(name="план", values=[1])])
    return Scene(
        slide_id=slide_id, pattern_id="p1", theme="dark",
        elements=[
            Element(id="e1", type="text", role="title", box=(0.08, 0.1, 0.8, 0.2), z=2,
                    text="Конверсия выросла до 20 процентов",
                    style=TextStyle(size_pt=40, bold=True, align="left")),
            Element(id="e2", type="text", role="body", box=(0.08, 0.4, 0.6, 0.3), z=1,
                    text="<script>alert(1)</script> и подпись"),
            Element(id="e3", type="chart", role="other", box=(0.5, 0.4, 0.4, 0.4), z=1, chart=chart),
            Element(id="e4", type="text", role="caption", box=(0.08, 0.8, 0.4, 0.1), z=1, text=""),
        ],
    )


def _deck() -> Deck:
    plan = DeckPlan(
        title="Тестовая колода", purpose="показать вид слайда",
        slides=[SlideIntent(id="s1", kind=SlideKind.title, title="Заголовок"),
                SlideIntent(id="s2", kind=SlideKind.bullets, title="Пункты")],
    )
    return Deck(id="deck-test", design_system_id="ds-test", variant="a", plan=plan,
                scenes=[_scene("s1"), _scene("s2")])


# ---------- один слайд ----------

def test_slide_html_shows_picture_of_the_slide():
    out = slide_html(PNG_ONE, _scene(), _design_system())
    doc = lxml_html.fromstring(out)

    images = doc.xpath('//img[@class="slide-image"]')
    assert len(images) == 1
    assert images[0].get("src") == "data:image/png;base64," + base64.b64encode(PNG_ONE).decode("ascii")


def test_text_layer_has_every_text_element_of_the_scene():
    scene = _scene()
    out = slide_html(PNG_ONE, scene, _design_system())
    doc = lxml_html.fromstring(out)

    layer_texts = [el.text_content() for el in doc.xpath('//div[contains(@class, "el text")]')]
    expected = [el.text for el in sorted(scene.elements, key=lambda e: e.z)
                 if el.type == "text" and el.text]
    assert layer_texts == expected


def test_text_layer_is_transparent_and_selectable():
    out = slide_html(PNG_ONE, _scene(), _design_system())
    assert "color: transparent;" in out
    assert "::selection" in out


def test_non_text_elements_do_not_get_into_the_layer():
    out = slide_html(PNG_ONE, _scene(), _design_system())
    doc = lxml_html.fromstring(out)

    assert doc.xpath('//*[local-name()="svg"]') == []
    assert len(doc.xpath('//div[contains(@class, "el text")]')) == 2


def test_script_in_text_is_escaped():
    out = slide_html(PNG_ONE, _scene(), _design_system())
    doc = lxml_html.fromstring(out)

    assert "<script>alert(1)</script>" not in out
    assert len(doc.xpath("//script")) == 1  # только листание


def test_slide_html_has_no_external_links():
    out = slide_html(PNG_ONE, _scene(), _design_system())
    assert "http://" not in out
    assert "https://" not in out


# ---------- колода ----------

def test_deck_images_render_section_per_slide():
    out = render_deck_images(_deck(), _design_system(), [PNG_ONE, PNG_TWO])
    doc = lxml_html.fromstring(out)

    sections = doc.xpath("//section[contains(concat(' ', @class, ' '), ' slide ')]")
    assert len(sections) == 2
    sources = [img.get("src") for img in doc.xpath('//img[@class="slide-image"]')]
    assert sources[0] != sources[1]


def test_deck_images_keep_paging_fullscreen_and_print():
    out = render_deck_images(_deck(), _design_system(), [PNG_ONE, PNG_TWO])

    assert "ArrowRight" in out
    assert "requestFullscreen" in out
    assert "@media print" in out


def test_deck_title_goes_to_the_page_title():
    out = render_deck_images(_deck(), _design_system(), [PNG_ONE, PNG_TWO])
    doc = lxml_html.fromstring(out)

    assert doc.xpath("//title")[0].text == "Тестовая колода"


def test_first_slide_is_visible_without_script():
    # Сцена живого режима показывает слайд в рамке без скриптов: первый слайд виден разметкой.
    assert 'class="slide active"' in slide_html(PNG_ONE, _scene(), _design_system())
