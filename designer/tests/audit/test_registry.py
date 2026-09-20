"""Тесты реестра проверок: уникальность id, детерминизм, чистая колода без находок.

Владелец: задача T-03.
"""
from designer.audit.deterministic import CHECKS, run_checks
from designer.contracts import DesignSystem, Element, Margins, Pattern, Scene, SlideKind, Tokens

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
