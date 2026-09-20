"""Тесты плотности содержимого: пункты, таблицы, диаграммы, заполнение слайда.

Владелец: задача T-03.
"""
from designer.audit import checks_density
from designer.contracts import (
    ChartSpec, DesignSystem, Element, Margins, Scene, Series, TableSpec, Tokens,
)

_SLIDE_EMU = (1270000, 1270000)


def _ds() -> DesignSystem:
    return DesignSystem(
        id="ds1", source_file="tpl.pptx", slide_size_emu=_SLIDE_EMU,
        tokens=Tokens(colors=[], fonts=[], type_scale=[], margins=Margins(left=0, top=0, right=0, bottom=0)),
    )


def _scene(slide_id: str, elements: list[Element]) -> Scene:
    return Scene(slide_id=slide_id, pattern_id="p1", elements=elements)


def test_bullets_found():
    text = "\n".join(f"пункт {i}" for i in range(7))
    el = Element(id="e1", type="text", box=(0, 0, 0.5, 0.5), text=text)
    findings = checks_density.check_bullets([_scene("s1", [el])], _ds())
    assert len(findings) == 1


def test_bullets_clean():
    text = "\n".join(f"пункт {i}" for i in range(6))
    el = Element(id="e1", type="text", box=(0, 0, 0.5, 0.5), text=text)
    findings = checks_density.check_bullets([_scene("s1", [el])], _ds())
    assert findings == []


def test_bullet_words_found():
    line = " ".join(f"слово{i}" for i in range(16))
    el = Element(id="e1", type="text", box=(0, 0, 0.5, 0.5), text=line)
    findings = checks_density.check_bullet_words([_scene("s1", [el])], _ds())
    assert len(findings) == 1


def test_bullet_words_clean():
    line = " ".join(f"слово{i}" for i in range(15))
    el = Element(id="e1", type="text", box=(0, 0, 0.5, 0.5), text=line)
    findings = checks_density.check_bullet_words([_scene("s1", [el])], _ds())
    assert findings == []


def test_table_found():
    spec = TableSpec(columns=["c1", "c2", "c3", "c4", "c5", "c6"], rows=[["a"] * 6 for _ in range(3)])
    el = Element(id="e1", type="table", box=(0, 0, 0.6, 0.4), table=spec)
    findings = checks_density.check_table([_scene("s1", [el])], _ds())
    assert len(findings) == 1


def test_table_clean():
    spec = TableSpec(columns=["c1", "c2", "c3", "c4"], rows=[["a"] * 4 for _ in range(5)])
    el = Element(id="e1", type="table", box=(0, 0, 0.6, 0.4), table=spec)
    findings = checks_density.check_table([_scene("s1", [el])], _ds())
    assert findings == []


def test_series_found():
    spec = ChartSpec(type="line", categories=["q1"], series=[Series(name=f"s{i}", values=[1]) for i in range(6)])
    el = Element(id="e1", type="chart", box=(0, 0, 0.6, 0.4), chart=spec)
    findings = checks_density.check_series([_scene("s1", [el])], _ds())
    assert len(findings) == 1


def test_series_clean():
    spec = ChartSpec(type="line", categories=["q1"], series=[Series(name=f"s{i}", values=[1]) for i in range(5)])
    el = Element(id="e1", type="chart", box=(0, 0, 0.6, 0.4), chart=spec)
    findings = checks_density.check_series([_scene("s1", [el])], _ds())
    assert findings == []


def test_fill_found_too_little():
    el = Element(id="e1", type="text", box=(0.4, 0.4, 0.05, 0.05), text="x")
    findings = checks_density.check_fill([_scene("s1", [el])], _ds())
    assert len(findings) == 1


def test_fill_clean():
    el = Element(id="e1", type="text", box=(0.2, 0.2, 0.6, 0.5), text="x")
    findings = checks_density.check_fill([_scene("s1", [el])], _ds())
    assert findings == []
