"""Тесты целостности содержимого: заглушки, пустые слайды, подписи диаграмм, дубли.

Владелец: задача T-03.
"""
from designer.audit import checks_integrity
from designer.contracts import ChartSpec, DesignSystem, Element, Margins, Scene, Series, Tokens

_SLIDE_EMU = (1270000, 1270000)


def _ds() -> DesignSystem:
    return DesignSystem(
        id="ds1", source_file="tpl.pptx", slide_size_emu=_SLIDE_EMU,
        tokens=Tokens(colors=[], fonts=[], type_scale=[], margins=Margins(left=0, top=0, right=0, bottom=0)),
    )


def _scene(slide_id: str, elements: list[Element]) -> Scene:
    return Scene(slide_id=slide_id, pattern_id="p1", elements=elements)


def test_placeholder_text_found():
    el = Element(id="e1", type="text", box=(0, 0, 0.5, 0.1), text="Lorem ipsum dolor sit amet")
    findings = checks_integrity.check_placeholder_text([_scene("s1", [el])], _ds())
    assert len(findings) == 1


def test_placeholder_text_clean():
    el = Element(id="e1", type="text", box=(0, 0, 0.5, 0.1), text="Реальный содержательный рассказ о продукте")
    findings = checks_integrity.check_placeholder_text([_scene("s1", [el])], _ds())
    assert findings == []


def test_empty_found_no_elements():
    findings = checks_integrity.check_empty([_scene("s1", [])], _ds())
    assert len(findings) == 1
    assert findings[0].check_id == "integrity.empty"


def test_empty_clean_title_and_body():
    title = Element(id="t1", type="text", role="title", box=(0, 0, 0.5, 0.1), text="Название")
    body = Element(id="b1", type="text", role="body", box=(0, 0.2, 0.5, 0.3), text="Раскрытие темы")
    findings = checks_integrity.check_empty([_scene("s1", [title, body])], _ds())
    assert findings == []


def test_chart_labels_found():
    spec = ChartSpec(type="line", categories=[], series=[Series(name="", values=[1])], unit="")
    el = Element(id="e1", type="chart", box=(0, 0, 0.5, 0.3), chart=spec)
    findings = checks_integrity.check_chart_labels([_scene("s1", [el])], _ds())
    assert len(findings) == 1


def test_chart_labels_clean():
    spec = ChartSpec(type="line", categories=["Q1", "Q2"], series=[Series(name="Выручка", values=[1, 2])], unit="млн")
    el = Element(id="e1", type="chart", box=(0, 0, 0.5, 0.3), chart=spec)
    findings = checks_integrity.check_chart_labels([_scene("s1", [el])], _ds())
    assert findings == []


def test_duplicate_found():
    el1 = Element(id="e1", type="text", box=(0, 0, 0.5, 0.1), text="Один и тот же текст")
    el2 = Element(id="e2", type="text", box=(0, 0, 0.5, 0.1), text="Один и тот же текст")
    scenes = [_scene("s1", [el1]), _scene("s2", [el2])]
    findings = checks_integrity.check_duplicate(scenes, _ds())
    assert len(findings) == 1
    assert findings[0].slide_id == "s2"


def test_duplicate_clean():
    el1 = Element(id="e1", type="text", box=(0, 0, 0.5, 0.1), text="Первый слайд")
    el2 = Element(id="e2", type="text", box=(0, 0, 0.5, 0.1), text="Второй слайд")
    scenes = [_scene("s1", [el1]), _scene("s2", [el2])]
    findings = checks_integrity.check_duplicate(scenes, _ds())
    assert findings == []
