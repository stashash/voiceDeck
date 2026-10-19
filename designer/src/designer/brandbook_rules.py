"""Validated explicit placement/grid rules accompanying imported brand tokens."""
from __future__ import annotations

from pathlib import PurePosixPath
from designer.contracts import BrandRules, Tokens


def read_rules(root: dict) -> dict:
    raw = root.get("rules", {})
    if not isinstance(raw, dict) or set(raw) - ((set(BrandRules.model_fields) - {"logo_asset", "color_overrides"}) | {"logo"}):
        raise ValueError("Unknown brand rules; use logo, logo_box, clear_space, grid_columns, grid_gutter")
    logo = raw.get("logo")
    if logo is not None:
        path = PurePosixPath(logo) if isinstance(logo, str) else PurePosixPath("..")
        if not isinstance(logo, str) or "\\" in logo or path.is_absolute() or ".." in path.parts:
            raise ValueError("Logo must name an image inside the brandbook archive")
    rules = BrandRules.model_validate({key: value for key, value in raw.items() if key != "logo"})
    x, y, w, h = rules.logo_box
    if any(not 0 <= value <= 1 for value in rules.logo_box) or w <= 0 or h <= 0 or x + w > 1 or y + h > 1:
        raise ValueError("Logo box must fit inside the slide")
    result = rules.model_dump(exclude={"logo_asset", "color_overrides"}) if raw else {}
    if logo:
        result["logo"] = logo
    return result


def apply_grid(tokens: Tokens, rules: dict) -> Tokens:
    count = rules.get("grid_columns")
    if not count:
        return tokens
    left, right = tokens.margins.left, tokens.margins.right
    left, right = (left, right) if left + right < 0.75 else (0.06, 0.06)
    gutter = rules.get("grid_gutter", 0.02)
    width = (1 - left - right - gutter * (count - 1)) / count
    if width <= 0:
        raise ValueError("Grid gutters leave no room for columns")
    return tokens.model_copy(update={"guides_x": [left + i * (width + gutter) for i in range(count)]})
