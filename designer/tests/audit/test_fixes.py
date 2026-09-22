"""Тесты починки находок аудита. Владелец: задача T-21."""
from designer.audit.deterministic import run_checks
from designer.audit.fixes import apply_fixes
from designer.contracts import (
    ColorToken, DesignSystem, Element, Finding, Margins, Pattern, Scene, SlideKind, SlideSpec,
    Slot, TextStyle, Tokens, TypeStep,
)

_SLIDE_EMU = (1270000, 1270000)


def _ds(*, type_scale=(), colors=(), margins=None, guides_x=(), patterns=()) -> DesignSystem:
    return DesignSystem(
        id="ds1", source_file="tpl.pptx", slide_size_emu=_SLIDE_EMU,
        tokens=Tokens(
            colors=list(colors), fonts=[], type_scale=list(type_scale),
            margins=margins or Margins(left=0.0, top=0.0, right=0.0, bottom=0.0),
            guides_x=list(guides_x),
        ),
        patterns=list(patterns),
    )


def _pattern(slot: Slot | None = None) -> Pattern:
    return Pattern(
        id="p1", source_slide=1, layout_name="L1", kind=SlideKind.bullets,
        kind_confidence=0.9, theme="light", slots=[slot] if slot else [],
    )


def _scene(slide_id: str, elements: list[Element], *, pattern_id="p1", background_color=None) -> Scene:
    return Scene(slide_id=slide_id, pattern_id=pattern_id, elements=elements, background_color=background_color)


def _spec(slide_id: str, *, pattern_id="p1", slot_text=None, fitted_size_pt=None) -> SlideSpec:
    return SlideSpec(
        slide_id=slide_id, pattern_id=pattern_id,
        slot_text=dict(slot_text or {}), fitted_size_pt=dict(fitted_size_pt or {}),
    )


def test_type_scale_fixed():
    ds = _ds(
        type_scale=[TypeStep(size_pt=12, role="body", share=0.5), TypeStep(size_pt=24, role="body", share=0.5)],
        patterns=[_pattern(Slot(id="body", role="body", shape_id=1, box=(0, 0, 0.5, 0.5), max_chars=100, max_lines=5))],
    )
    el = Element(id="body", type="text", box=(0, 0, 0.5, 0.5), text="текст слота",
                 style=TextStyle(size_pt=15), source_shape_id=1)
    scene = _scene("s1", [el])
    spec = _spec("s1", slot_text={"body": "текст слота"})

    findings = run_checks([scene], ds)
    target = next(f for f in findings if f.check_id == "template.type_scale")

    new_specs, new_scenes, report = apply_fixes([spec], [scene], findings, [target.id], ds)

    assert scene.elements[0].style.size_pt == 15
    assert spec.fitted_size_pt == {}
    entry = next(r for r in report if r["finding_id"] == target.id)
    assert entry["status"] == "fixed"
    assert "12" in entry["what"]

    fixed_el = new_scenes[0].elements[0]
    assert fixed_el.style.size_pt == 12
    assert new_specs[0].fitted_size_pt["body"] == 12
    assert not any(f.check_id == "template.type_scale" for f in run_checks(new_scenes, ds))


def test_color_text_fixed():
    ds = _ds(colors=[ColorToken(hex="0077FF", role="accent", share=1.0, source="theme")])
    el = Element(id="e1", type="text", box=(0, 0, 0.3, 0.1), text="a", style=TextStyle(color="FF0000"))
    scene = _scene("s1", [el])
    spec = _spec("s1")

    findings = run_checks([scene], ds)
    target = next(f for f in findings if f.check_id == "template.color")

    new_specs, new_scenes, report = apply_fixes([spec], [scene], findings, [target.id], ds)

    assert scene.elements[0].style.color == "FF0000"
    entry = next(r for r in report if r["finding_id"] == target.id)
    assert entry["status"] == "fixed"

    assert new_scenes[0].elements[0].style.color == "0077FF"
    assert not any(f.check_id == "template.color" for f in run_checks(new_scenes, ds))


def test_color_fill_fixed():
    ds = _ds(colors=[ColorToken(hex="0077FF", role="accent", share=1.0, source="theme")])
    el = Element(id="e1", type="shape", box=(0, 0, 0.3, 0.1), fill="FF0000")
    scene = _scene("s1", [el])
    spec = _spec("s1")

    findings = run_checks([scene], ds)
    target = next(f for f in findings if f.check_id == "template.color")

    new_specs, new_scenes, report = apply_fixes([spec], [scene], findings, [target.id], ds)

    assert scene.elements[0].fill == "FF0000"
    entry = next(r for r in report if r["finding_id"] == target.id)
    assert entry["status"] == "fixed"

    assert new_scenes[0].elements[0].fill == "0077FF"
    assert not any(f.check_id == "template.color" for f in run_checks(new_scenes, ds))


def test_text_overflow_fixed():
    ds = _ds(
        type_scale=[TypeStep(size_pt=12, role="body", share=0.5), TypeStep(size_pt=24, role="body", share=0.5)],
        patterns=[_pattern(Slot(id="body", role="body", shape_id=1, box=(0, 0, 0.5, 0.2), max_chars=100, max_lines=5))],
    )
    el = Element(id="body", type="text", box=(0, 0, 0.5, 0.2), text="abcde",
                 style=TextStyle(size_pt=24), source_shape_id=1)
    scene = _scene("s1", [el])
    spec = _spec("s1", slot_text={"body": "abcde"})

    findings = run_checks([scene], ds)
    target = next(f for f in findings if f.check_id == "layout.text_overflow")

    new_specs, new_scenes, report = apply_fixes([spec], [scene], findings, [target.id], ds)

    assert scene.elements[0].style.size_pt == 24
    assert spec.fitted_size_pt == {}
    entry = next(r for r in report if r["finding_id"] == target.id)
    assert entry["status"] == "fixed"

    fixed_el = new_scenes[0].elements[0]
    assert fixed_el.style.size_pt == 12
    assert new_specs[0].fitted_size_pt["body"] == 12
    assert not any(f.check_id == "layout.text_overflow" for f in run_checks(new_scenes, ds))


def test_off_guides_fixed():
    ds = _ds(guides_x=[0.1])
    el = Element(id="e1", type="text", box=(0.115, 0.0, 0.2, 0.1), text="a", style=TextStyle(size_pt=12))
    scene = _scene("s1", [el])
    spec = _spec("s1")

    findings = run_checks([scene], ds)
    target = next(f for f in findings if f.check_id == "layout.off_guides")

    new_specs, new_scenes, report = apply_fixes([spec], [scene], findings, [target.id], ds)

    assert scene.elements[0].box[0] == 0.115
    entry = next(r for r in report if r["finding_id"] == target.id)
    assert entry["status"] == "fixed"

    fixed_el = new_scenes[0].elements[0]
    assert abs(fixed_el.box[0] - 0.1) < 1e-9
    assert not any(f.check_id == "layout.off_guides" for f in run_checks(new_scenes, ds))


def test_in_margins_fixed():
    ds = _ds(margins=Margins(left=0.05, top=0.05, right=0.05, bottom=0.05))
    el = Element(id="e1", type="text", box=(0.03, 0.2, 0.3, 0.1), text="a", style=TextStyle(size_pt=12))
    scene = _scene("s1", [el])
    spec = _spec("s1")

    findings = run_checks([scene], ds)
    target = next(f for f in findings if f.check_id == "layout.in_margins")

    new_specs, new_scenes, report = apply_fixes([spec], [scene], findings, [target.id], ds)

    assert scene.elements[0].box[0] == 0.03
    entry = next(r for r in report if r["finding_id"] == target.id)
    assert entry["status"] == "fixed"

    fixed_el = new_scenes[0].elements[0]
    assert abs(fixed_el.box[0] - 0.05) < 1e-9
    assert not any(f.check_id == "layout.in_margins" for f in run_checks(new_scenes, ds))


def test_contrast_fixed():
    ds = _ds(colors=[
        ColorToken(hex="FFFFFF", role="text", share=0.5, source="theme"),
        ColorToken(hex="000000", role="text", share=0.5, source="theme"),
    ])
    el = Element(id="e1", type="text", box=(0, 0, 0.3, 0.1), text="a", style=TextStyle(color="FFFFFF"))
    scene = _scene("s1", [el], background_color="FFFFFF")
    spec = _spec("s1")

    findings = run_checks([scene], ds)
    target = next(f for f in findings if f.check_id == "template.contrast")

    new_specs, new_scenes, report = apply_fixes([spec], [scene], findings, [target.id], ds)

    assert scene.elements[0].style.color == "FFFFFF"
    entry = next(r for r in report if r["finding_id"] == target.id)
    assert entry["status"] == "fixed"

    assert new_scenes[0].elements[0].style.color == "000000"
    assert not any(f.check_id == "template.contrast" for f in run_checks(new_scenes, ds))


def test_placeholder_text_fixed():
    ds = _ds(
        patterns=[_pattern(Slot(id="body", role="body", shape_id=1, box=(0, 0, 0.5, 0.2), max_chars=50, max_lines=3))],
    )
    el = Element(id="body", type="text", box=(0, 0, 0.5, 0.2), text="TODO",
                 style=TextStyle(size_pt=12), source_shape_id=1)
    scene = _scene("s1", [el])
    spec = _spec("s1", slot_text={"body": "TODO"})

    findings = run_checks([scene], ds)
    target = next(f for f in findings if f.check_id == "integrity.placeholder_text")

    new_specs, new_scenes, report = apply_fixes([spec], [scene], findings, [target.id], ds)

    assert scene.elements[0].text == "TODO"
    assert spec.slot_text["body"] == "TODO"
    entry = next(r for r in report if r["finding_id"] == target.id)
    assert entry["status"] == "fixed"

    assert new_scenes[0].elements[0].text == ""
    assert new_specs[0].slot_text["body"] == ""
    assert not any(f.check_id == "integrity.placeholder_text" for f in run_checks(new_scenes, ds))


def test_bullets_fixed():
    ds = _ds(
        patterns=[_pattern(Slot(id="body", role="body", shape_id=1, box=(0, 0, 0.5, 0.5), max_chars=200, max_lines=10))],
    )
    lines = [f"пункт {i}" for i in range(1, 8)]
    text = "\n".join(lines)
    el = Element(id="body", type="text", box=(0, 0, 0.5, 0.5), text=text,
                 style=TextStyle(size_pt=12), source_shape_id=1)
    scene = _scene("s1", [el])
    spec = _spec("s1", slot_text={"body": text})

    findings = run_checks([scene], ds)
    target = next(f for f in findings if f.check_id == "density.bullets")

    new_specs, new_scenes, report = apply_fixes([spec], [scene], findings, [target.id], ds)

    assert scene.elements[0].text == text
    assert spec.slot_text["body"] == text
    entry = next(r for r in report if r["finding_id"] == target.id)
    assert entry["status"] == "fixed"
    assert "пункт 7" in entry["what"]

    expected = "\n".join(lines[:6])
    assert new_scenes[0].elements[0].text == expected
    assert new_specs[0].slot_text["body"] == expected
    assert not any(f.check_id == "density.bullets" for f in run_checks(new_scenes, ds))


def test_contextual_finding_skipped():
    ds = _ds()
    el = Element(id="e1", type="text", box=(0, 0, 0.3, 0.1), text="a", style=TextStyle(size_pt=12))
    scene = _scene("s1", [el])
    spec = _spec("s1")
    finding = Finding(
        id="f1", slide_id="s1", check_id="contextual.composition", kind="contextual",
        severity="warning", message="Композиция слайда выглядит неровно", element_ids=["e1"], fixable=False,
    )

    new_specs, new_scenes, report = apply_fixes([spec], [scene], [finding], ["f1"], ds)

    assert len(report) == 1
    assert report[0]["finding_id"] == "f1"
    assert report[0]["status"] == "skipped"
    assert report[0]["what"]
    assert new_scenes[0].elements[0].text == "a"
    assert new_specs[0].slot_text == {}


def test_number_and_unchangeable_sizes_are_skipped():
    """Крупное число не приводится к ступени шкалы, а починка без изменения не считается сделанной."""
    from designer.audit.fixes import _fix_text_overflow, _fix_type_scale
    from designer.contracts import Element, TextStyle, TypeStep, Finding

    ds = _ds(type_scale=[TypeStep(role="body", size_pt=24, share=0.7), TypeStep(role="title", size_pt=48, share=0.3)])
    number = Element(id="n1", type="text", role="number", box=(0.1, 0.3, 0.3, 0.2), z=1, text="12 %",
                     style=TextStyle(size_pt=85.5))
    long = Element(id="b1", type="text", role="body", box=(0.1, 0.1, 0.05, 0.02), z=1, text="очень длинная строка",
                   style=TextStyle(size_pt=24))
    scene = _scene("s1", [number, long])
    spec = _spec("s1")
    f_num = Finding(id="f1", slide_id="s1", check_id="template.type_scale", kind="deterministic", severity="warning",
                    message="", element_ids=["n1"], fixable=True)
    f_long = Finding(id="f2", slide_id="s1", check_id="layout.text_overflow", kind="deterministic", severity="warning",
                     message="", element_ids=["b1"], fixable=True)
    assert _fix_type_scale(f_num, scene, spec, None, ds) is None
    assert number.style.size_pt == 85.5
    assert _fix_text_overflow(f_long, scene, spec, None, ds) is None
    assert long.style.size_pt == 24
