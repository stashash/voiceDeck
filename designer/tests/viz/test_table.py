"""Тесты add_table: текст ячеек, заливка шапки, рамка, лимиты строк и колонок. Владелец: задача T-05."""
from pathlib import Path

import pytest
from pptx import Presentation

from designer.contracts import ColorToken, FontToken, Margins, TableSpec, Tokens, TypeStep
from designer.viz.pptx_native import add_table

SLIDE_SIZE = (9144000, 5143500)


def _tokens() -> Tokens:
    return Tokens(
        colors=[
            ColorToken(hex="0077FF", role="accent", share=0.3, source="theme"),
            ColorToken(hex="EEEEEE", role="surface", share=0.4, source="usage"),
        ],
        fonts=[FontToken(family="PT Sans", role="body", share=0.8)],
        type_scale=[TypeStep(size_pt=12, role="body", share=0.5)],
        margins=Margins(left=0.03, top=0.06, right=0.03, bottom=0.06),
    )


def _blank_slide():
    prs = Presentation()
    prs.slide_width, prs.slide_height = SLIDE_SIZE
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    return prs, slide


def _roundtrip(prs: Presentation, tmp_path: Path) -> Presentation:
    path = tmp_path / "out.pptx"
    prs.save(str(path))
    return Presentation(str(path))


def _spec(rows: int = 2, cols: int = 3) -> TableSpec:
    columns = [f"стлб{i}" for i in range(cols)]
    body = [[f"{r}-{c}" for c in range(cols)] for r in range(rows)]
    return TableSpec(columns=columns, rows=body)


def test_add_table_cell_text_and_header_fill(tmp_path):
    tokens = _tokens()
    prs, slide = _blank_slide()
    spec = _spec(rows=2, cols=3)

    add_table(slide, spec, (0.1, 0.1, 0.6, 0.3), SLIDE_SIZE, tokens)

    reopened = _roundtrip(prs, tmp_path)
    table = reopened.slides[0].shapes[0].table
    assert table.cell(0, 0).text == "стлб0"
    assert table.cell(1, 1).text == "0-1"
    assert str(table.cell(0, 0).fill.fore_color.rgb) == "0077FF"


def test_add_table_box_matches_within_one_percent(tmp_path):
    tokens = _tokens()
    prs, slide = _blank_slide()
    spec = _spec(rows=2, cols=2)
    box = (0.1, 0.2, 0.5, 0.3)

    add_table(slide, spec, box, SLIDE_SIZE, tokens)

    reopened = _roundtrip(prs, tmp_path)
    shape = reopened.slides[0].shapes[0]
    slide_w, slide_h = SLIDE_SIZE
    assert shape.left == pytest.approx(box[0] * slide_w, rel=0.01)
    assert shape.top == pytest.approx(box[1] * slide_h, rel=0.01)
    assert shape.width == pytest.approx(box[2] * slide_w, rel=0.01)
    assert shape.height == pytest.approx(box[3] * slide_h, rel=0.01)


def test_add_table_more_than_seven_rows_raises():
    tokens = _tokens()
    _, slide = _blank_slide()
    spec = _spec(rows=8, cols=2)

    with pytest.raises(ValueError):
        add_table(slide, spec, (0.1, 0.1, 0.5, 0.3), SLIDE_SIZE, tokens)


def test_add_table_more_than_five_columns_raises():
    tokens = _tokens()
    _, slide = _blank_slide()
    spec = _spec(rows=2, cols=6)

    with pytest.raises(ValueError):
        add_table(slide, spec, (0.1, 0.1, 0.5, 0.3), SLIDE_SIZE, tokens)
