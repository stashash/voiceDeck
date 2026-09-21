"""Намерение -> инструкция сборки слайда. Задачи T-07 и T-19."""
from designer.contracts import (
    Area, ChartSpec, DesignSystem, Item, Margins, Pattern, RepeatGroup, RepeatUnit,
    Series, SlideIntent, SlideKind, Slot, TableSpec, TextStyle, Tokens, TypeStep,
)
from designer.layout.capacity import box_capacity, slide_pt
from designer.layout.compose import compose

SLIDE = (9144000, 5143500)
SLIDE_PT = slide_pt(SLIDE)


def _slot(shape_id, role, box, size=18.0):
    chars, lines = box_capacity(box, size, SLIDE_PT)
    return Slot(id=f"s{shape_id}", role=role, shape_id=shape_id, box=box,
                style=TextStyle(size_pt=size), max_chars=chars, max_lines=lines,
                sample_text="образцовый текст шаблона")


def _ds():
    tokens = Tokens(colors=[], fonts=[],
                    type_scale=[TypeStep(size_pt=36, role="title", share=0.3),
                                TypeStep(size_pt=18, role="body", share=0.7)],
                    margins=Margins(left=0.05, top=0.05, right=0.05, bottom=0.05))
    return DesignSystem(id="ds", source_file="shablon.pptx", slide_size_emu=SLIDE, tokens=tokens)


def _cards(max_units=4, areas=None, extra_slots=()):
    units = [RepeatUnit(index=i, box=(0.05 + i * 0.30, 0.35, 0.28, 0.30), shape_ids=[100 + i])
             for i in range(3)]
    group = RepeatGroup(id="g1", direction="row", cols=3, rows=1, step=(0.30, 0.0),
                        unit_size=(0.28, 0.30), units=units, max_units=max_units,
                        unit_slots=[_slot(101, "number", (0.0, 0.0, 0.08, 0.05), 24),
                                    _slot(102, "heading", (0.0, 0.07, 0.26, 0.06), 20),
                                    _slot(103, "body", (0.0, 0.15, 0.26, 0.14), 12)])
    slots = [_slot(1, "title", (0.05, 0.08, 0.6, 0.12), 36),
             _slot(2, "subtitle", (0.05, 0.22, 0.6, 0.07), 20), *extra_slots]
    return Pattern(id="p001", source_slide=1, layout_name="макет", kind=SlideKind.cards,
                   kind_confidence=0.8, theme="light", slots=slots, groups=[group],
                   areas=list(areas or []))


def _intent(**kwargs):
    base = dict(id="s1", kind=SlideKind.cards, title="Три причины",
                key_message="Почему это работает")
    base.update(kwargs)
    return SlideIntent(**base)


def _items(n):
    return [Item(heading=f"Причина {i + 1}", body="Короткое пояснение") for i in range(n)]


def test_title_and_key_message_go_to_their_slots():
    spec = compose(_intent(items=_items(3)), _cards(), _ds())
    assert spec.slot_text["s1"] == "Три причины"
    assert spec.slot_text["s2"] == "Почему это работает"
    assert spec.pattern_id == "p001" and spec.slide_id == "s1"


def test_items_fill_unit_slots_by_role():
    spec = compose(_intent(items=_items(3)), _cards(), _ds())
    assert spec.group_id == "g1"
    assert len(spec.unit_text) == 3
    assert spec.unit_text[0]["s102"] == "Причина 1"
    assert spec.unit_text[2]["s103"] == "Короткое пояснение"
    assert spec.unit_text[1]["s101"] == "2"


def test_own_numbers_win_over_order():
    items = [Item(number="01", heading="Разбор"), Item(number="02", heading="Сборка")]
    spec = compose(_intent(kind=SlideKind.steps, items=items), _cards(), _ds())
    assert [unit["s101"] for unit in spec.unit_text] == ["01", "02"]


def test_number_is_kept_when_the_block_has_no_number_slot():
    pattern = _cards()
    pattern.groups[0].unit_slots = [_slot(102, "heading", (0.0, 0.07, 0.26, 0.06), 20)]
    spec = compose(_intent(items=[Item(number="5", heading="минут на колоду")]), pattern, _ds())
    assert spec.unit_text[0]["s102"] == "5 минут на колоду"


def test_slots_without_content_get_an_empty_string():
    pattern = _cards(extra_slots=[_slot(3, "caption", (0.05, 0.9, 0.3, 0.05), 12)])
    spec = compose(_intent(items=_items(3)), pattern, _ds())
    assert set(spec.slot_text) == {"s1", "s2", "s3"}
    assert spec.slot_text["s3"] == ""


def test_every_unit_slot_is_named_even_when_item_has_no_body():
    items = [Item(heading="Только заголовок"), Item(heading="И второй")]
    spec = compose(_intent(items=items), _cards(), _ds())
    assert set(spec.unit_text[0]) == {"s101", "s102", "s103"}
    assert spec.unit_text[0]["s103"] == ""


def test_extra_items_do_not_exceed_the_grid():
    spec = compose(_intent(items=_items(9)), _cards(max_units=4), _ds())
    assert len(spec.unit_text) == 4


def test_table_goes_to_the_table_area():
    area = Area(id="a9", kind="table", box=(0.05, 0.3, 0.9, 0.5), shape_id=9)
    table = TableSpec(columns=["Проверка", "Что ловит"], rows=[["Наезд", "пересечение блоков"]])
    spec = compose(_intent(kind=SlideKind.table, items=[], table=table), _cards(areas=[area]), _ds())
    assert spec.viz_area_id == "a9"
    assert spec.table is table
    assert spec.unit_text == []


def test_without_an_area_visualisation_gets_the_free_frame():
    chart = ChartSpec(type="column", categories=["I", "II"], series=[Series(name="план", values=[1, 2])])
    pattern = _cards()
    spec = compose(_intent(kind=SlideKind.chart, items=_items(3), chart=chart), pattern, _ds())
    assert spec.viz_area_id is None
    assert spec.unit_text == []
    assert spec.viz_box is not None and spec.viz_box[2] * spec.viz_box[3] >= 0.35
    blocks = {sid for unit in pattern.groups[0].units for sid in unit.shape_ids}
    assert blocks <= set(spec.remove_shape_ids)


def test_items_land_in_free_slots_when_there_is_no_group():
    pattern = _cards(extra_slots=[_slot(4, "body", (0.05, 0.4, 0.4, 0.2), 16),
                                  _slot(5, "body", (0.05, 0.65, 0.4, 0.2), 16)])
    pattern.groups = []
    spec = compose(_intent(items=_items(2)), pattern, _ds())
    assert spec.unit_text == []
    filled = [text for text in spec.slot_text.values() if "Причина" in text]
    assert len(filled) == 2


def test_lead_number_goes_to_the_number_slot():
    pattern = _cards(extra_slots=[_slot(6, "number", (0.05, 0.4, 0.3, 0.25), 72)])
    pattern.groups = []
    intent = _intent(kind=SlideKind.big_number, items=[Item(number="5", heading="минут на колоду")])
    spec = compose(intent, pattern, _ds())
    assert spec.slot_text["s6"] == "5"


# ---------- решения вёрстки: что убрать, где визуализация, каким кеглем набрать ----------

def _second_group():
    """Вторая группа паттерна со своими фигурами: содержания ей не достанется."""
    units = [RepeatUnit(index=i, box=(0.05 + i * 0.30, 0.72, 0.28, 0.12), shape_ids=[300 + i])
             for i in range(3)]
    return RepeatGroup(id="g2", direction="row", cols=3, rows=1, step=(0.30, 0.0),
                       unit_size=(0.28, 0.12), units=units, max_units=3,
                       unit_slots=[_slot(301, "caption", (0.0, 0.0, 0.26, 0.10), 12)])


def _linked_steps():
    """Ряд номеров и ряд подписей под ними: подписи главные, номера идут за ними."""
    numbers = RepeatGroup(
        id="g1", direction="row", cols=3, rows=1, step=(0.30, 0.0), unit_size=(0.10, 0.10),
        units=[RepeatUnit(index=i, box=(0.14 + i * 0.30, 0.35, 0.10, 0.10), shape_ids=[400 + i])
               for i in range(3)],
        max_units=3, unit_slots=[_slot(401, "number", (0.0, 0.0, 0.10, 0.10), 40)])
    heads = RepeatGroup(
        id="g2", direction="row", cols=3, rows=1, step=(0.30, 0.0), unit_size=(0.28, 0.14),
        units=[RepeatUnit(index=i, box=(0.05 + i * 0.30, 0.50, 0.28, 0.14), shape_ids=[410 + i])
               for i in range(3)],
        max_units=3, unit_slots=[_slot(411, "heading", (0.0, 0.0, 0.28, 0.06), 20),
                                 _slot(412, "body", (0.0, 0.08, 0.28, 0.06), 12)],
        linked_group_ids=["g1"])
    pattern = _cards()
    pattern.groups = [numbers, heads]
    pattern.primary_group_id = "g2"
    return pattern


def test_group_without_content_is_removed_whole():
    pattern = _cards()
    pattern.groups.append(_second_group())
    spec = compose(_intent(items=_items(3)), pattern, _ds())
    assert spec.group_id == "g1"
    assert {300, 301, 302} <= set(spec.remove_shape_ids)


def test_blocks_beyond_the_content_are_removed():
    pattern = _cards()
    pattern.groups[0].units = [RepeatUnit(index=i, box=(0.05 + i * 0.30, 0.35, 0.28, 0.30),
                                          shape_ids=[500 + i]) for i in range(3)]
    spec = compose(_intent(items=_items(2)), pattern, _ds())
    assert len(spec.unit_text) == 2
    assert 502 in spec.remove_shape_ids
    assert 500 not in spec.remove_shape_ids


def test_photo_placeholder_is_removed():
    area = Area(id="a9", kind="image", box=(0.6, 0.3, 0.3, 0.4), shape_id=9, placeholder=True)
    spec = compose(_intent(items=_items(3)), _cards(areas=[area]), _ds())
    assert 9 in spec.remove_shape_ids


def test_sample_chart_of_the_pattern_is_removed():
    area = Area(id="a9", kind="chart", box=(0.6, 0.3, 0.3, 0.4), shape_id=9)
    spec = compose(_intent(items=_items(3)), _cards(areas=[area]), _ds())
    assert 9 in spec.remove_shape_ids


def test_linked_group_gets_the_same_number_of_blocks():
    items = [Item(number="01", heading="Разбор", body="Читаем шаблон"),
             Item(number="02", heading="План", body="Делим бриф на слайды")]
    spec = compose(_intent(kind=SlideKind.steps, items=items), _linked_steps(), _ds())
    assert spec.group_id == "g2"
    assert list(spec.linked_unit_text) == ["g1"]
    assert len(spec.linked_unit_text["g1"]) == len(spec.unit_text) == 2
    assert [unit["s401"] for unit in spec.linked_unit_text["g1"]] == ["01", "02"]
    assert spec.unit_text[1]["s411"] == "План"
    assert spec.unit_text[1]["s412"] == "Делим бриф на слайды"
    # Третий блок обеих групп лишний: он уходит, первые два остаются.
    assert not set(spec.remove_shape_ids) & {400, 401, 410, 411}
    assert {402, 412} <= set(spec.remove_shape_ids)


def test_single_slot_keeps_both_heading_and_body():
    pattern = _cards()
    pattern.groups[0].unit_slots = [_slot(102, "heading", (0.0, 0.07, 0.26, 0.06), 20)]
    spec = compose(_intent(items=_items(2)), pattern, _ds())
    assert "Короткое пояснение" in spec.unit_text[0]["s102"]
    assert "Причина 1" in spec.unit_text[0]["s102"]


def test_visualisation_frame_is_roomy_and_clears_what_is_under_it():
    stray = _slot(7, "caption", (0.1, 0.5, 0.3, 0.1), 12)
    table = TableSpec(columns=["Проверка", "Что ловит"], rows=[["Наезд", "пересечение блоков"]])
    spec = compose(_intent(kind=SlideKind.table, items=[], table=table),
                   _cards(extra_slots=[stray]), _ds())
    box = spec.viz_box
    assert box is not None and box[2] * box[3] >= 0.35
    assert box[0] >= 0.05 and box[1] + box[3] <= 0.95
    assert spec.slot_text["s7"] == "" and 7 in spec.remove_shape_ids
    assert spec.slot_text["s2"] == "Почему это работает"


def test_visualisation_frame_goes_around_the_filled_slot():
    message = _slot(8, "body", (0.05, 0.32, 0.9, 0.12), 16)
    chart = ChartSpec(type="column", categories=["I", "II"], series=[Series(name="план", values=[1, 2])])
    pattern = _cards(extra_slots=[message])
    pattern.slots = [slot for slot in pattern.slots if slot.id != "s2"]
    spec = compose(_intent(kind=SlideKind.chart, items=[], chart=chart), pattern, _ds())
    assert spec.slot_text["s8"] == "Почему это работает"
    assert spec.viz_box is not None and spec.viz_box[1] >= 0.44 - 1e-9


def test_fitted_size_steps_down_for_a_long_heading():
    items = [Item(heading="Причина, у которой очень длинное название", body="Коротко"), *_items(2)]
    spec = compose(_intent(items=items), _cards(), _ds())
    assert spec.fitted_size_pt["s102"] == 18.0  # один кегль на все блоки ряда
    assert spec.fitted_size_pt["s1"] == 36.0
