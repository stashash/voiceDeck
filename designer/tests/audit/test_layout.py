"""Тесты вёрстки: границы, наложения, переполнение, поля, направляющие, пропорции.

Владелец: задача T-03.
"""
from designer.audit import checks_layout
from designer.contracts import Asset, DesignSystem, Element, Margins, Scene, TextStyle, Tokens

_SLIDE_EMU = (1270000, 1270000)  # квадратный слайд 100x100 pt — удобные числа для расчёта вручную


def _ds(*, margins=None, guides_x=(), assets=()):
    return DesignSystem(
        id="ds1", source_file="tpl.pptx", slide_size_emu=_SLIDE_EMU,
        tokens=Tokens(
            colors=[], fonts=[], type_scale=[],
            margins=margins or Margins(left=0.05, top=0.05, right=0.05, bottom=0.05),
            guides_x=list(guides_x), guides_y=[],
        ),
        assets=list(assets),
    )


def _scene(slide_id: str, elements: list[Element]) -> Scene:
    return Scene(slide_id=slide_id, pattern_id="p1", elements=elements)


def test_out_of_bounds_found():
    el = Element(id="e1", type="text", box=(0.9, 0.9, 0.2, 0.2), text="x")
    findings = checks_layout.check_out_of_bounds([_scene("s1", [el])], _ds())
    assert len(findings) == 1
    assert findings[0].check_id == "layout.out_of_bounds"
    assert findings[0].element_ids == ["e1"]


def test_out_of_bounds_clean():
    el = Element(id="e1", type="text", box=(0.1, 0.1, 0.2, 0.2), text="x")
    findings = checks_layout.check_out_of_bounds([_scene("s1", [el])], _ds())
    assert findings == []


def test_overlap_found():
    a = Element(id="a", type="text", box=(0.1, 0.1, 0.3, 0.3), text="a")
    b = Element(id="b", type="text", box=(0.2, 0.2, 0.3, 0.3), text="b")
    findings = checks_layout.check_overlap([_scene("s1", [a, b])], _ds())
    assert len(findings) == 1
    assert set(findings[0].element_ids) == {"a", "b"}


def test_overlap_clean_backdrop_excluded():
    """Подложка (shape) под текстом наложением не считается — исключена из сравнения."""
    text = Element(id="t", type="text", box=(0.2, 0.2, 0.2, 0.1), text="t")
    backdrop = Element(id="bg", type="shape", box=(0.1, 0.1, 0.5, 0.4), fill="0077FF")
    other = Element(id="c", type="text", box=(0.7, 0.7, 0.2, 0.2), text="c")
    findings = checks_layout.check_overlap([_scene("s1", [text, backdrop, other])], _ds())
    assert findings == []


def test_text_overflow_found():
    style = TextStyle(size_pt=10)
    el = Element(id="e1", type="text", box=(0.3, 0.3, 0.3, 0.2), text="a" * 6, style=style)
    findings = checks_layout.check_text_overflow([_scene("s1", [el])], _ds())
    assert len(findings) == 1
    assert findings[0].fixable is True


def test_text_overflow_clean():
    style = TextStyle(size_pt=10)
    el = Element(id="e1", type="text", box=(0.3, 0.3, 0.3, 0.2), text="a" * 5, style=style)
    findings = checks_layout.check_text_overflow([_scene("s1", [el])], _ds())
    assert findings == []


def test_in_margins_found():
    el = Element(id="e1", type="text", box=(0.0, 0.1, 0.1, 0.1), text="x")
    findings = checks_layout.check_in_margins([_scene("s1", [el])], _ds())
    assert len(findings) == 1


def test_in_margins_clean():
    el = Element(id="e1", type="text", box=(0.1, 0.1, 0.1, 0.1), text="x")
    findings = checks_layout.check_in_margins([_scene("s1", [el])], _ds())
    assert findings == []


def test_off_guides_found():
    el = Element(id="e1", type="text", box=(0.3, 0.1, 0.1, 0.1), text="x")
    findings = checks_layout.check_off_guides([_scene("s1", [el])], _ds(guides_x=[0.1, 0.5]))
    assert len(findings) == 1


def test_off_guides_clean():
    el = Element(id="e1", type="text", box=(0.1, 0.1, 0.1, 0.1), text="x")
    findings = checks_layout.check_off_guides([_scene("s1", [el])], _ds(guides_x=[0.1, 0.5]))
    assert findings == []


def test_image_aspect_found():
    asset = Asset(id="img1", path="img1.png", kind="photo", width_px=200, height_px=100, sha1="a" * 40)
    el = Element(id="e1", type="image", box=(0.1, 0.1, 0.4, 0.1), asset="img1")
    findings = checks_layout.check_image_aspect([_scene("s1", [el])], _ds(assets=[asset]))
    assert len(findings) == 1


def test_image_aspect_clean():
    asset = Asset(id="img1", path="img1.png", kind="photo", width_px=200, height_px=100, sha1="a" * 40)
    el = Element(id="e1", type="image", box=(0.1, 0.1, 0.4, 0.2), asset="img1")
    findings = checks_layout.check_image_aspect([_scene("s1", [el])], _ds(assets=[asset]))
    assert findings == []
