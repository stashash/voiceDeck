"""Тесты соответствия шаблону: шрифты, кегли, цвета, ссылка на паттерн, контраст.

Владелец: задача T-03.
"""
from designer.audit import checks_template
from designer.contracts import (
    ColorToken, DesignSystem, Element, FontToken, Margins, Pattern, Scene, SlideKind,
    TextStyle, Tokens, TypeStep,
)

_SLIDE_EMU = (1270000, 1270000)


def _ds(*, fonts=(), type_scale=(), colors=(), patterns=()):
    return DesignSystem(
        id="ds1", source_file="tpl.pptx", slide_size_emu=_SLIDE_EMU,
        tokens=Tokens(
            colors=list(colors), fonts=list(fonts), type_scale=list(type_scale),
            margins=Margins(left=0.0, top=0.0, right=0.0, bottom=0.0),
        ),
        patterns=list(patterns),
    )


def _pattern(pattern_id: str) -> Pattern:
    return Pattern(id=pattern_id, source_slide=1, layout_name="L1", kind=SlideKind.bullets,
                    kind_confidence=0.9, theme="light")


def _scene(slide_id: str, elements: list[Element], *, pattern_id="p1", background_color=None) -> Scene:
    return Scene(slide_id=slide_id, pattern_id=pattern_id, elements=elements, background_color=background_color)


def test_font_found_wrong_and_too_many():
    ds = _ds(fonts=[FontToken(family="Inter", role="body", share=1.0)])
    e1 = Element(id="e1", type="text", box=(0, 0, 0.3, 0.1), text="a", style=TextStyle(family="Comic Sans"))
    e2 = Element(id="e2", type="text", box=(0, 0.2, 0.3, 0.1), text="b", style=TextStyle(family="Inter"))
    e3 = Element(id="e3", type="text", box=(0, 0.4, 0.3, 0.1), text="c", style=TextStyle(family="Arial"))
    findings = checks_template.check_font([_scene("s1", [e1, e2, e3])], ds)
    assert len(findings) == 3
    assert all(f.check_id == "template.font" for f in findings)


def test_font_clean():
    ds = _ds(fonts=[FontToken(family="Inter", role="body", share=1.0)])
    el = Element(id="e1", type="text", box=(0, 0, 0.3, 0.1), text="a", style=TextStyle(family="Inter"))
    findings = checks_template.check_font([_scene("s1", [el])], ds)
    assert findings == []


def test_type_scale_found():
    ds = _ds(type_scale=[TypeStep(size_pt=12, role="body", share=0.5), TypeStep(size_pt=24, role="title", share=0.5)])
    el = Element(id="e1", type="text", box=(0, 0, 0.3, 0.1), text="a", style=TextStyle(size_pt=15))
    findings = checks_template.check_type_scale([_scene("s1", [el])], ds)
    assert len(findings) == 1
    assert findings[0].fixable is True


def test_type_scale_clean():
    ds = _ds(type_scale=[TypeStep(size_pt=12, role="body", share=0.5), TypeStep(size_pt=24, role="title", share=0.5)])
    el = Element(id="e1", type="text", box=(0, 0, 0.3, 0.1), text="a", style=TextStyle(size_pt=12.3))
    findings = checks_template.check_type_scale([_scene("s1", [el])], ds)
    assert findings == []


def test_color_found():
    ds = _ds(colors=[ColorToken(hex="0077FF", role="accent", share=1.0, source="theme")])
    el = Element(id="e1", type="text", box=(0, 0, 0.3, 0.1), text="a", style=TextStyle(color="FF0000"))
    findings = checks_template.check_color([_scene("s1", [el])], ds)
    assert len(findings) == 1
    assert findings[0].fixable is True


def test_color_clean_within_tolerance():
    ds = _ds(colors=[ColorToken(hex="0077FF", role="accent", share=1.0, source="theme")])
    el = Element(id="e1", type="text", box=(0, 0, 0.3, 0.1), text="a", style=TextStyle(color="0077FA"))
    findings = checks_template.check_color([_scene("s1", [el])], ds)
    assert findings == []


def test_pattern_found():
    ds = _ds(patterns=[_pattern("p1")])
    findings = checks_template.check_pattern([_scene("s1", [], pattern_id="missing")], ds)
    assert len(findings) == 1
    assert findings[0].check_id == "template.pattern"


def test_pattern_clean():
    ds = _ds(patterns=[_pattern("p1")])
    findings = checks_template.check_pattern([_scene("s1", [], pattern_id="p1")], ds)
    assert findings == []


def test_contrast_found():
    ds = _ds()
    el = Element(id="e1", type="text", box=(0, 0, 0.3, 0.1), text="a", style=TextStyle(color="FFFFFF"))
    findings = checks_template.check_contrast([_scene("s1", [el], background_color="FFFFFF")], ds)
    assert len(findings) == 1
    assert findings[0].check_id == "template.contrast"


def test_contrast_clean():
    ds = _ds()
    el = Element(id="e1", type="text", box=(0, 0, 0.3, 0.1), text="a", style=TextStyle(color="000000"))
    findings = checks_template.check_contrast([_scene("s1", [el], background_color="FFFFFF")], ds)
    assert findings == []
