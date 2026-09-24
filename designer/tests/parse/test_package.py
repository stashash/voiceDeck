import re
import time

from designer.parse.package import build_package, load_package

# Одиночная буква диска с двоеточием и слэшем; «https://» и текст образцов со слайдов сюда не попадают.
_ABS_PATH_RE = re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]")


def test_manifest_roundtrips_without_loss(templates, tmp_path):
    for path in templates:
        out_dir = tmp_path / path.stem
        design_system = build_package(path, out_dir)
        again = load_package(out_dir)
        assert design_system == again, f"{path.name}: манифест не совпал после перечитывания"


def test_manifest_has_no_absolute_paths(templates, tmp_path):
    for path in templates:
        out_dir = tmp_path / path.stem
        build_package(path, out_dir)
        text = (out_dir / "manifest.json").read_text(encoding="utf-8")
        assert not _ABS_PATH_RE.search(text), f"{path.name}: в манифесте буква диска с двоеточием"
        assert "Users" not in text, f"{path.name}: в манифесте подстрока Users"


def test_one_template_builds_under_60_seconds(templates, tmp_path):
    path = templates[0]
    started = time.monotonic()
    build_package(path, tmp_path / "speed")
    assert time.monotonic() - started < 60


def test_foreign_pptx_builds_without_exception(foreign_pptx, tmp_path):
    design_system = build_package(foreign_pptx, tmp_path / "foreign")
    assert design_system.source_file == foreign_pptx.name


def test_play_font_token_has_file_in_package(templates, tmp_path):
    for path in templates:
        out_dir = tmp_path / path.stem
        design_system = build_package(path, out_dir)
        play_tokens = [f for f in design_system.tokens.fonts if f.family == "Play"]
        assert play_tokens, f"{path.name}: нет FontToken для Play"
        fonts_dir = out_dir / "fonts"
        saved = list(fonts_dir.glob("Play-*"))
        assert saved, f"{path.name}: нет сохранённого файла шрифта Play в {fonts_dir}"


# ---------- поток 1: name, created_at, embedded_state ----------

def test_manifest_has_name_and_created_at(templates, tmp_path):
    path = templates[0]
    design_system = build_package(path, tmp_path / "out")
    assert design_system.name  # непусто: посчитано из имени файла
    assert design_system.created_at  # ISO 8601, непусто


def test_display_name_replaces_underscore_and_dash_with_space(tmp_path):
    from designer.parse.package import _display_name

    assert _display_name("my_template-file.pptx") == "my template file"
    assert _display_name("Обычное имя.pptx") == "Обычное имя"


def test_build_package_uses_display_name_from_input_filename(templates, tmp_path):
    import shutil

    renamed = tmp_path / "my_template-file.pptx"
    shutil.copyfile(templates[0], renamed)

    design_system = build_package(renamed, tmp_path / "out")

    assert design_system.name == "my template file"


def test_font_embedded_state_is_extracted_or_missing(templates, tmp_path):
    for path in templates:
        design_system = build_package(path, tmp_path / path.stem)
        for font in design_system.tokens.fonts:
            if font.embedded_file:
                assert font.embedded_state == "extracted", f"{path.name}: {font.family}"
            else:
                assert font.embedded_state in ("embedded_not_extracted", "missing"), f"{path.name}: {font.family}"
