"""Тесты палитры и контрастного текста. Владелец: задача T-05."""
from designer.contracts import ColorToken, Margins, Tokens
from designer.viz.palette import contrast_text_color, series_colors


def _tokens(colors: list[ColorToken]) -> Tokens:
    return Tokens(colors=colors, fonts=[], type_scale=[], margins=Margins(left=0, top=0, right=0, bottom=0))


def test_series_colors_accent_first_then_alt_then_by_share():
    tokens = _tokens([
        ColorToken(hex="112233", role="other", share=0.5, source="usage"),
        ColorToken(hex="0077FF", role="accent", share=0.3, source="theme"),
        ColorToken(hex="FF00AA", role="accent_alt", share=0.2, source="theme"),
        ColorToken(hex="FFFFFF", role="background", share=0.9, source="usage"),
        ColorToken(hex="000000", role="text", share=0.8, source="usage"),
        ColorToken(hex="9A9A9A", role="text_muted", share=0.7, source="usage"),
    ])
    assert series_colors(tokens) == ["0077FF", "FF00AA", "112233"]


def test_series_colors_rest_sorted_by_share_descending():
    tokens = _tokens([
        ColorToken(hex="AAAAAA", role="other", share=0.1, source="usage"),
        ColorToken(hex="BBBBBB", role="surface", share=0.4, source="usage"),
    ])
    assert series_colors(tokens) == ["BBBBBB", "AAAAAA"]


def test_series_colors_drops_duplicate_hex():
    tokens = _tokens([
        ColorToken(hex="0077FF", role="accent", share=0.3, source="theme"),
        ColorToken(hex="0077FF", role="other", share=0.9, source="usage"),
    ])
    assert series_colors(tokens) == ["0077FF"]


def test_contrast_text_color_light_fill_gets_dark_text():
    assert contrast_text_color("FFFFFF") == "000000"
    assert contrast_text_color("F2F2F2") == "000000"


def test_contrast_text_color_dark_fill_gets_light_text():
    assert contrast_text_color("000000") == "FFFFFF"
    assert contrast_text_color("0B1220") == "FFFFFF"
