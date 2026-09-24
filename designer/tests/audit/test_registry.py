"""Тесты реестра проверок: уникальность id, детерминизм, чистая колода без находок.

Владелец: задача T-03.
"""
from designer.audit.deterministic import CHECKS, run_checks
from designer.contracts import DesignSystem, Element, Margins, Pattern, Scene, SlideKind, TextStyle, Tokens

_SLIDE_EMU = (1270000, 1270000)


def _ds() -> DesignSystem:
    return DesignSystem(
        id="ds1", source_file="tpl.pptx", slide_size_emu=_SLIDE_EMU,
        tokens=Tokens(
            colors=[], fonts=[], type_scale=[],
            margins=Margins(left=0.05, top=0.05, right=0.05, bottom=0.05),
        ),
        patterns=[Pattern(id="clean", source_slide=1, layout_name="L1", kind=SlideKind.bullets,
                           kind_confidence=0.9, theme="light")],
    )


def _clean_scenes() -> list[Scene]:
    scenes = []
    for i in range(1, 6):
        title = Element(id=f"t{i}", type="text", role="title", box=(0.1, 0.1, 0.5, 0.1),
                         text=f"Тема доклада {i}")
        body = Element(id=f"b{i}", type="text", role="body", box=(0.1, 0.25, 0.7, 0.4),
                        text=f"Краткое описание пункта номер {i} для примера содержания")
        scenes.append(Scene(slide_id=f"s{i}", pattern_id="clean", elements=[title, body]))
    return scenes


def test_check_ids_are_unique():
    ids = [c.id for c in CHECKS]
    assert len(ids) == len(set(ids))


def test_run_checks_deterministic_across_runs():
    ds = _ds()
    el = Element(id="e1", type="text", box=(0.9, 0.9, 0.2, 0.2), text="TODO")
    scenes = [Scene(slide_id="s1", pattern_id="clean", elements=[el])]
    first = run_checks(scenes, ds)
    second = run_checks(scenes, ds)
    assert len(first) >= 1
    assert first == second


def test_clean_five_slide_deck_has_no_findings():
    ds = _ds()
    scenes = _clean_scenes()
    assert run_checks(scenes, ds) == []


def test_finding_messages_hide_internal_shape_ids():
    """Сообщения находок не показывают внутренние id вроде «s401», «d1056», «u1s123» (T-29)."""
    ds = _ds()
    internal_ids = ["s401", "d1056", "u1s99", "s1", "b1"]
    elements = [
        Element(id="s401", type="text", role="title", box=(0.9, 0.9, 0.5, 0.5), text="a" * 400,
                style=TextStyle(size_pt=99), source_shape_id=401),
        Element(id="d1056", type="shape", role="decor", box=(0.9, 0.9, 0.5, 0.5), fill="123456"),
        Element(id="u1s99", type="text", role="caption", box=(0.9, 0.9, 0.5, 0.5), text="b" * 400,
                style=TextStyle(size_pt=99, color="ABCDEF"), source_shape_id=99),
        Element(id="s1", type="table", role="viz", box=(0.5, 0.5, 0.3, 0.3)),
    ]
    scenes = [Scene(slide_id="b1", pattern_id="missing", elements=elements, background_color="000000")]
    findings = run_checks(scenes, ds)
    assert findings, "проверка должна была что-то найти на таком намеренно кривом слайде"
    for f in findings:
        for internal_id in internal_ids:
            assert internal_id not in f.message, f"{f.check_id}: «{internal_id}» в сообщении «{f.message}»"
