"""Тесты палитры и контрастного текста. Владелец: T-05, контраст темы и приглушённая сетка — T-20."""
import pytest

from designer.contracts import ColorToken, Margins, Tokens
from designer.viz.palette import (
    contrast_ratio, contrast_text_color, is_dark, muted_gridline_color, series_colors, theme_text_color,
)


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


def test_contrast_ratio_black_on_white_is_maximum():
    assert contrast_ratio("000000", "FFFFFF") == pytest.approx(21.0)


def test_contrast_ratio_same_color_is_one():
    assert contrast_ratio("336699", "336699") == pytest.approx(1.0)


def test_is_dark_splits_by_luminance():
    assert is_dark("000000") is True
    assert is_dark("FFFFFF") is False


def test_theme_text_color_picks_the_most_contrasting_token():
    tokens = _tokens([
        ColorToken(hex="0B1220", role="background", share=0.6, source="theme"),
        ColorToken(hex="223344", role="text", share=0.2, source="usage"),
        ColorToken(hex="FAFAFA", role="accent", share=0.2, source="theme"),
    ])
    assert theme_text_color(tokens, "dark") == "FAFAFA"


def test_theme_text_color_none_without_a_background_token():
    tokens = _tokens([ColorToken(hex="F2F2F2", role="text", share=0.5, source="usage")])
    assert theme_text_color(tokens, "dark") is None


def test_muted_gridline_color_is_between_text_and_background():
    tokens = _tokens([
        ColorToken(hex="0B1220", role="background", share=0.6, source="theme"),
        ColorToken(hex="F2F2F2", role="text", share=0.2, source="usage"),
    ])
    gridline = muted_gridline_color(tokens, "dark")
    assert gridline is not None
    assert contrast_ratio("F2F2F2", "0B1220") > contrast_ratio(gridline, "0B1220") > 1.0
