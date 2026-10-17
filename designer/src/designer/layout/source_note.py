"""A visible, exportable source band for analytical slides."""
from designer.contracts import DesignSystem, Element, ElementPosition, Pattern, SlideSpec, TextStyle
from designer.layout.units import text_frame


def add_source_note(spec: SlideSpec, text: str, pattern: Pattern, ds: DesignSystem) -> None:
    if not text:
        return
    # The chart/table must end above the attribution. Its data remain unchanged.
    if spec.viz_box is None and (spec.chart is not None or spec.table is not None):
        margins = ds.tokens.margins
        spec.viz_box = (margins.left, 0.35, max(0.1, 1 - margins.left - margins.right), 0.54)
    if spec.viz_box is not None:
        x, y, w, h = spec.viz_box
        spec.viz_box = (x, y, w, min(h, max(0.05, 0.89 - y)))
    for slot in pattern.slots:
        if not spec.slot_text.get(slot.id) or slot.shape_id in spec.remove_shape_ids:
            continue
        original = text_frame(slot.box, ds.tokens.margins, slot.style.align)
        x, y, w, h = original
        if y + h > 0.90:
            spec.element_positions[slot.id] = ElementPosition(
                original_box=original, box=(x, max(0, 0.89 - h), w, h), source_shape_id=slot.shape_id,
            )
    dark = pattern.theme == "dark"
    background, color = ("161616", "FFFFFF") if dark else ("FFFFFF", "333333")
    font = next((item.family for item in ds.tokens.fonts if item.role == "body"), "Arial")
    # Keep the full source in notes/provenance. A very long filename is visibly abbreviated.
    lines = [line if len(line) <= 145 else line[:142] + "…" for line in text.splitlines()[:2]]
    spec.added_elements.extend([
        Element(id="data-source-background", type="shape", role="source_background",
                box=(0, 0.91, 1, 0.09), fill=background, z=10000),
        Element(id="data-source", type="text", role="source", box=(0.04, 0.925, 0.92, 0.065),
                text="\n".join(lines), z=10001,
                style=TextStyle(family=font, size_pt=8, color=color, align="left")),
    ])
