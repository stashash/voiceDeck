from designer.parse.tokens import extract_tokens


def _luminance(hexval: str) -> float:
    r = int(hexval[0:2], 16)
    g = int(hexval[2:4], 16)
    b = int(hexval[4:6], 16)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def test_accent_blue_in_top5_usage_colors(templates):
    for path in templates:
        tokens = extract_tokens(path)
        usage_hexes = [c.hex for c in tokens.colors if c.source == "usage"][:5]
        assert "0077FF" in usage_hexes, f"{path.name}: {usage_hexes}"


def test_play_font_detected(templates):
    for path in templates:
        tokens = extract_tokens(path)
        families = [f.family for f in tokens.fonts]
        assert "Play" in families, f"{path.name}: {families}"


def test_workspace_background_dark_others_light(templates):
    for path in templates:
        tokens = extract_tokens(path)
        bg = next(c for c in tokens.colors if c.source == "usage" and c.role == "background")
        is_dark = _luminance(bg.hex) < 128
        if "WorkSpace" in path.name:
            assert is_dark, f"{path.name}: фон {bg.hex} должен быть тёмным"
        else:
            assert not is_dark, f"{path.name}: фон {bg.hex} должен быть светлым"


def test_type_scale_nonempty_and_descending(templates):
    for path in templates:
        tokens = extract_tokens(path)
        sizes = [step.size_pt for step in tokens.type_scale]
        assert sizes, f"{path.name}: шкала кеглей пуста"
        assert sizes == sorted(sizes, reverse=True), f"{path.name}: {sizes}"


def test_foreign_pptx_does_not_raise(foreign_pptx):
    tokens = extract_tokens(foreign_pptx)
    assert tokens.colors or tokens.fonts or tokens.type_scale
