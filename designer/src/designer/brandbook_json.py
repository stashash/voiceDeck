"""Parse a small, explicit JSON brand-token format into service tokens.

Accepted fields are ``colors`` (role -> hex or a list of token objects),
``fonts``/``fontFamilies`` (role -> family or token objects),
``type_scale``/``fontSizes`` (role -> points or token objects), and
``margins``/``spacing`` (left/top/right/bottom fractions). The same fields may
be nested under ``tokens``. Unknown fields are rejected; this adapter does not
read paths or files itself.
"""
from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from designer.contracts import ColorToken, FontToken, Margins, Tokens, TypeStep


class BrandTokenError(ValueError):
    """Invalid brand-token input, with a JSON-style field path in the message."""


_HEX = re.compile(r"^#?[0-9A-Fa-f]{6}$")
_ROLES = {
    "colors": {"background", "surface", "text", "text_muted", "accent", "accent_alt", "other"},
    "fonts": {"heading", "body", "mono", "other"},
    "type_scale": {"display", "title", "heading", "body", "caption"},
}
_TOP_KEYS = {"tokens", "colors", "fonts", "fontFamilies", "type_scale", "typeScale", "fontSizes", "margins", "spacing"}


def _fail(path: str, message: str) -> None:
    raise BrandTokenError(f"{path}: {message}")


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        _fail(path, "expected an object with string keys")
    return value


def _field_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        _fail(path, "expected an array")
    return value


def _role(role: Any, category: str, path: str) -> str:
    if not isinstance(role, str) or role not in _ROLES[category]:
        _fail(path, f"unsupported {category} role {role!r}")
    return role


def _items(value: Any, category: str, path: str) -> list[dict[str, Any]]:
    """Accept either role-keyed W3C-ish values or explicit token objects."""
    if isinstance(value, Mapping):
        result = []
        for role, raw in value.items():
            role = _role(role, category, f"{path}.{role}")
            if isinstance(raw, Mapping):
                item = dict(raw)
                item.setdefault("role", role)
            else:
                item = {"role": role, "value": raw}
            result.append(item)
        return result
    result = []
    for index, raw in enumerate(_field_list(value, path)):
        item_path = f"{path}[{index}]"
        item = dict(_mapping(raw, item_path))
        allowed = {
            "colors": {"hex", "value", "role", "share", "source"},
            "fonts": {"family", "value", "role", "share"},
            "type_scale": {"size_pt", "value", "role", "share"},
        }[category]
        if set(item) - allowed:
            _fail(item_path, f"unknown fields: {', '.join(sorted(set(item) - allowed))}")
        result.append(item)
    return result


def _finite_number(value: Any, path: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        _fail(path, "expected a finite number")
    if positive and value <= 0:
        _fail(path, "expected a positive number")
    return float(value)


def _validation_error(exc: ValidationError, path: str) -> BrandTokenError:
    errors = exc.errors()
    first = errors[0]
    loc = ".".join(str(part) for part in first["loc"])
    return BrandTokenError(f"{path}.{loc}: {first['msg']}")


def parse_brand_tokens(json_bytes_or_dict: bytes | bytearray | Mapping[str, Any]) -> Tokens:
    """Parse JSON bytes or an already-decoded object into validated ``Tokens``.

    Colors are six-digit hex strings, with or without ``#``. Font sizes and
    margins use points and slide fractions respectively. Shares default to 1.
    """
    if isinstance(json_bytes_or_dict, (bytes, bytearray)):
        try:
            data = json.loads(json_bytes_or_dict)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BrandTokenError(f"$: invalid JSON ({exc})") from exc
    else:
        data = json_bytes_or_dict
    root = _mapping(data, "$")
    if set(root) - _TOP_KEYS:
        _fail("$", f"unknown fields: {', '.join(sorted(set(root) - _TOP_KEYS))}")
    if "tokens" in root:
        if len(root) != 1:
            _fail("$", "tokens cannot be combined with sibling token fields")
        root = _mapping(root["tokens"], "$.tokens")
        prefix = "$.tokens"
    else:
        prefix = "$"
    allowed = {"colors", "fonts", "fontFamilies", "type_scale", "typeScale", "fontSizes", "margins", "spacing"}
    unknown = set(root) - allowed
    if unknown:
        _fail(prefix, f"unknown fields: {', '.join(sorted(unknown))}")

    def choose(*keys: str) -> tuple[Any, str] | None:
        found = [key for key in keys if key in root]
        if len(found) > 1:
            _fail(prefix, f"use only one of: {', '.join(found)}")
        return (root[found[0]], f"{prefix}.{found[0]}") if found else None

    colors: list[ColorToken] = []
    chosen = choose("colors")
    if chosen:
        raw, path = chosen
        for index, item in enumerate(_items(raw, "colors", path)):
            item_path = f"{path}[{index}]" if isinstance(raw, list) else f"{path}.{item.get('role', index)}"
            role = _role(item.get("role"), "colors", item_path + ".role")
            hex_value = item.get("hex", item.get("value"))
            if not isinstance(hex_value, str) or not _HEX.fullmatch(hex_value):
                _fail(item_path + ".hex", "expected a six-digit hex color")
            try:
                share = _finite_number(item.get("share", 1.0), item_path + ".share")
                colors.append(ColorToken(hex=hex_value.lstrip("#").upper(), role=role,
                                         share=share, source=item.get("source", "theme")))
            except ValidationError as exc:
                raise _validation_error(exc, item_path) from exc

    fonts: list[FontToken] = []
    chosen = choose("fonts", "fontFamilies")
    if chosen:
        raw, path = chosen
        for index, item in enumerate(_items(raw, "fonts", path)):
            item_path = f"{path}[{index}]" if isinstance(raw, list) else f"{path}.{item.get('role', index)}"
            role = _role(item.get("role"), "fonts", item_path + ".role")
            family = item.get("family", item.get("value"))
            if not isinstance(family, str) or not family.strip():
                _fail(item_path + ".family", "expected a non-empty font family")
            try:
                share = _finite_number(item.get("share", 1.0), item_path + ".share")
                fonts.append(FontToken(family=family.strip(), role=role, share=share))
            except ValidationError as exc:
                raise _validation_error(exc, item_path) from exc

    scale: list[TypeStep] = []
    chosen = choose("type_scale", "typeScale", "fontSizes")
    if chosen:
        raw, path = chosen
        for index, item in enumerate(_items(raw, "type_scale", path)):
            item_path = f"{path}[{index}]" if isinstance(raw, list) else f"{path}.{item.get('role', index)}"
            role = _role(item.get("role"), "type_scale", item_path + ".role")
            size = item.get("size_pt", item.get("value"))
            try:
                size = _finite_number(size, item_path + ".size_pt", positive=True)
                share = _finite_number(item.get("share", 1.0), item_path + ".share")
                scale.append(TypeStep(size_pt=size, role=role, share=share))
            except ValidationError as exc:
                raise _validation_error(exc, item_path) from exc

    margins_raw = choose("margins", "spacing")
    margin_values = {"left": 0.0, "top": 0.0, "right": 0.0, "bottom": 0.0}
    if margins_raw:
        raw, path = margins_raw
        raw = _mapping(raw, path)
        if set(raw) - set(margin_values):
            _fail(path, f"unknown fields: {', '.join(sorted(set(raw) - set(margin_values)))}")
        for side, value in raw.items():
            margin = _finite_number(value, f"{path}.{side}")
            if not 0 <= margin <= 1:
                _fail(f"{path}.{side}", "expected a fraction from 0 to 1")
            margin_values[side] = margin
        try:
            margins = Margins(**margin_values)
        except ValidationError as exc:
            raise _validation_error(exc, path) from exc
    else:
        margins = Margins(**margin_values)
    try:
        return Tokens(colors=colors, fonts=fonts, type_scale=scale, margins=margins)
    except ValidationError as exc:
        raise _validation_error(exc, prefix) from exc


def resolve_tokens(template_tokens: Tokens, brand_tokens: Tokens, brand_priority: bool = True) -> Tokens:
    """Combine token groups, using non-empty brand groups as the preferred source.

    Guides always come from the template because brand JSON has no guide model.
    A zero-valued margins object is treated as omitted, allowing template fallback.
    """
    preferred, fallback = (brand_tokens, template_tokens) if brand_priority else (template_tokens, brand_tokens)
    margins_are_empty = all(getattr(preferred.margins, side) == 0 for side in ("left", "top", "right", "bottom"))
    return Tokens(
        colors=list(preferred.colors or fallback.colors),
        fonts=list(preferred.fonts or fallback.fonts),
        type_scale=list(preferred.type_scale or fallback.type_scale),
        margins=preferred.margins if not margins_are_empty else fallback.margins,
        guides_x=list(template_tokens.guides_x),
        guides_y=list(template_tokens.guides_y),
    )
