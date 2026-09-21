"""Тесты вёрстки: границы, наложения, переполнение, поля, направляющие, пропорции.

Владелец: задача T-03.
"""
from designer.audit import checks_layout
from designer.contracts import Asset, DesignSystem, Element, Margins, Pattern, Scene, TextStyle, Tokens
from designer.parse.package import build_package

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


# ---------- T-29: элемент на месте образца шаблона не считается огрехом ----------

def _slot_elements(pattern: Pattern) -> list[Element]:
    """Слоты паттерна как элементы сцены, без единого сдвига — как их поставил шаблон."""
    return [
        Element(
            id=slot.id, type="text", role=slot.role, box=slot.box,
            text=slot.sample_text or "Пример", style=slot.style, source_shape_id=slot.shape_id,
        )
        for slot in pattern.slots
        if slot.style.size_pt
    ]


def test_unmoved_template_slots_have_no_margin_or_guide_findings(templates, tmp_path):
    """Сцена, собранная из паттерна без сдвигов, чиста от layout.in_margins и layout.off_guides
    на всех выданных шаблонах: шаблон сам ставит элементы там, где считает нужным."""
    for path in templates:
        ds = build_package(path, tmp_path / path.stem)
        for pattern in ds.patterns:
            elements = _slot_elements(pattern)
            if not elements:
                continue
            scene = Scene(slide_id="s1", pattern_id=pattern.id, elements=elements,
                          background_color=pattern.background_color)
            findings = checks_layout.check_in_margins([scene], ds) + checks_layout.check_off_guides([scene], ds)
            assert findings == [], f"{path.name} {pattern.id}: {[f.message for f in findings]}"


def test_slot_shifted_5pct_past_margin_gets_finding(templates, tmp_path):
    """Тот же слот, сдвинутый на 5% кадра за поле, находку layout.in_margins получает."""
    path = templates[0]
    ds = build_package(path, tmp_path / path.stem)
    pattern = next(p for p in ds.patterns if any(s.style.size_pt for s in p.slots))
    slot = next(s for s in pattern.slots if s.style.size_pt)
    m = ds.tokens.margins
    x, y, w, h = slot.box
    shifted_box = (1 - m.right + 0.05, y, w, h)
    el = Element(id=slot.id, type="text", role=slot.role, box=shifted_box,
                 text=slot.sample_text or "Пример", style=slot.style, source_shape_id=slot.shape_id)
    scene = Scene(slide_id="s1", pattern_id=pattern.id, elements=[el], background_color=pattern.background_color)
    findings = checks_layout.check_in_margins([scene], ds)
    assert len(findings) == 1
    assert findings[0].check_id == "layout.in_margins"
