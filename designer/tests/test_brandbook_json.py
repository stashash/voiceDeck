import pytest
import re

from designer.brandbook_json import BrandTokenError, parse_brand_tokens, resolve_tokens
from designer.contracts import ColorToken, FontToken, Margins, Tokens, TypeStep


def _template() -> Tokens:
    return Tokens(
        colors=[ColorToken(hex="112233", role="accent", share=1, source="theme")],
        fonts=[FontToken(family="Template Sans", role="body", share=1)],
        type_scale=[TypeStep(size_pt=18, role="body", share=1)],
        margins=Margins(left=.1, top=.1, right=.1, bottom=.1),
        guides_x=[.2], guides_y=[.3],
    )


def test_parse_explicit_schema_and_w3cish_aliases():
    tokens = parse_brand_tokens(b'{"colors":{"accent":"#aabbcc"},"fontFamilies":{"body":"Inter"},"fontSizes":{"body":16},"spacing":{"left":0.05}}')
    assert tokens.colors[0].hex == "AABBCC"
    assert tokens.fonts[0].family == "Inter"
    assert tokens.type_scale[0].size_pt == 16
    assert tokens.margins.left == .05


def test_parse_explicit_token_arrays():
    tokens = parse_brand_tokens({"tokens": {
        "colors": [{"hex": "0077ff", "role": "accent", "source": "usage"}],
        "fonts": [{"family": "Inter", "role": "heading"}],
        "type_scale": [{"size_pt": 32, "role": "title"}],
        "margins": {"left": .04, "right": .04, "top": .05, "bottom": .05},
    }})
    assert tokens.colors[0].source == "usage"
    assert tokens.fonts[0].role == "heading"
    assert tokens.type_scale[0].role == "title"


@pytest.mark.parametrize(("data", "path"), [
    ({"colors": {"unknown": "ffffff"}}, "colors.unknown"),
    ({"colors": {"accent": "red"}}, "colors.accent.hex"),
    ({"fonts": [{"role": "body", "family": "  "}]}, "fonts[0].family"),
    ({"type_scale": {"body": -2}}, "type_scale.body.size_pt"),
    ({"margins": {"left": 1.2}}, "margins.left"),
    ({"surprise": True}, "unknown fields"),
    ({"colors": [{"hex": "FFFFFF", "role": "accent", "oops": 1}]}, "unknown fields"),
])
def test_invalid_input_reports_field_context(data, path):
    with pytest.raises(BrandTokenError, match=re.escape(path)):
        parse_brand_tokens(data)


def test_resolve_brand_priority_and_template_guides():
    template = _template()
    brand = parse_brand_tokens({"colors": {"accent": "AABBCC"}, "fontFamilies": {"body": "Inter"},
                                "fontSizes": {"body": 20}, "margins": {"left": .03}})
    resolved = resolve_tokens(template, brand)
    assert resolved.colors[0].hex == "AABBCC"
    assert resolved.fonts[0].family == "Inter"
    assert resolved.type_scale[0].size_pt == 20
    assert resolved.margins.left == .03
    assert resolved.margins.right == .0
    assert resolved.guides_x == [.2] and resolved.guides_y == [.3]


def test_empty_brand_groups_fall_back_and_priority_can_be_reversed():
    template = _template()
    empty = parse_brand_tokens({})
    resolved = resolve_tokens(template, empty)
    assert resolved.colors == template.colors
    assert resolved.margins == template.margins
    override = parse_brand_tokens({"colors": {"accent": "AABBCC"}})
    reversed_tokens = resolve_tokens(template, override, brand_priority=False)
    assert reversed_tokens.colors == template.colors
