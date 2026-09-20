from designer.contracts import (
    DesignSystem, Margins, Pattern, RepeatGroup, RepeatUnit, Scene, SlideKind, Slot, Tokens,
)


def test_design_system_roundtrip():
    slot = Slot(id="title", role="title", shape_id=808, box=(0.02, 0.06, 0.74, 0.14), max_chars=60, max_lines=2)
    group = RepeatGroup(
        id="g1", direction="grid", cols=3, rows=2, step=(0.32, 0.32), unit_size=(0.31, 0.31),
        units=[RepeatUnit(index=0, box=(0.03, 0.24, 0.31, 0.31), shape_ids=[777, 778, 779, 780, 781])],
        max_units=6,
    )
    pattern = Pattern(id="p17", source_slide=17, layout_name="1_Свободный дизайн", kind=SlideKind.cards,
                      kind_confidence=0.9, theme="light", slots=[slot], groups=[group])
    ds = DesignSystem(
        id="vk-tech", source_file="VK Tech шаблон.pptx", slide_size_emu=(9144000, 5143500),
        tokens=Tokens(colors=[], fonts=[], type_scale=[], margins=Margins(left=0.03, top=0.06, right=0.03, bottom=0.06)),
        patterns=[pattern],
    )
    again = DesignSystem.model_validate_json(ds.model_dump_json())
    assert again.patterns[0].groups[0].units[0].shape_ids[0] == 777


def test_scene_defaults():
    assert Scene(slide_id="s1", pattern_id="p17").elements == []
