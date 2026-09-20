from designer.parse.assets import extract_assets


def test_images_written_and_deduplicated_by_sha1(templates, tmp_path):
    for path in templates:
        out_dir = tmp_path / path.stem
        assets = extract_assets(path, out_dir)
        assert assets, f"{path.name}: нет ни одной картинки"
        sha1s = [a.sha1 for a in assets]
        assert len(sha1s) == len(set(sha1s)), f"{path.name}: дубликаты по sha1"
        for asset in assets:
            assert (out_dir / asset.path).is_file()
            assert asset.width_px > 0 and asset.height_px > 0
            assert asset.kind in ("background", "logo", "decor", "icon", "photo", "other")


def test_play_embedded_font_file_saved(templates, tmp_path):
    for path in templates:
        out_dir = tmp_path / path.stem
        extract_assets(path, out_dir)
        fonts_dir = out_dir / "fonts"
        play_files = list(fonts_dir.glob("play-*")) + list(fonts_dir.glob("Play-*"))
        assert play_files, f"{path.name}: нет файла шрифта Play в {fonts_dir}"


def test_foreign_pptx_does_not_raise(foreign_pptx, tmp_path):
    assets = extract_assets(foreign_pptx, tmp_path / "foreign")
    assert isinstance(assets, list)
