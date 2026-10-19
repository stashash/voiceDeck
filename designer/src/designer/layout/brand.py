"""Apply explicit, persisted brand-element placement to every exported scene."""
from designer.contracts import DesignSystem, Element


def apply_brand(elements: list[Element], ds: DesignSystem) -> list[Element]:
    rules = ds.brand_rules
    if rules is None:
        return elements
    for element in elements:
        if element.fill in rules.color_overrides:
            element.fill = rules.color_overrides[element.fill]
        if element.style and element.style.color in rules.color_overrides:
            element.style = element.style.model_copy(update={"color": rules.color_overrides[element.style.color]})
        if element.style and element.type == "text":
            role = "heading" if element.role in {"title", "heading"} else "body"
            family = next((font.family for font in ds.tokens.fonts if font.role == role), None)
            if family:
                element.style = element.style.model_copy(update={"family": family})
    if not rules.logo_asset:
        return elements
    original_logos = {asset.id for asset in ds.assets if asset.kind == "logo" and asset.id != rules.logo_asset}
    elements = [element for element in elements if element.asset not in original_logos]
    asset = next((asset for asset in ds.assets if asset.id == rules.logo_asset), None)
    if asset is None:
        return elements
    x, y, w, h = rules.logo_box
    slide_ratio = ds.slide_size_emu[0] / ds.slide_size_emu[1]
    ratio = asset.width_px / max(1, asset.height_px) / slide_ratio
    if w / h > ratio:
        final_w = h * ratio
        x += (w - final_w) / 2
        w = final_w
    else:
        final_h = w / ratio
        y += (h - final_h) / 2
        h = final_h
    gap = rules.clear_space
    for element in elements:
        if element.type != "text" or element.role not in {"title", "heading", "subtitle"}:
            continue
        ex, ey, ew, eh = element.box
        if ey < y + h + gap and ey + eh > y - gap and ex < x and ex + ew > x - gap:
            element.box = (ex, ey, max(0.05, x - gap - ex), eh)
    elements.append(Element(id="brand-logo", type="image", role="brand_logo", asset=asset.id,
                            box=(x, y, w, h), z=11000))
    return elements
