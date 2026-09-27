"""Пиктограммы пунктов: подбор по подсказке модели и цвет значка образца."""
import io

from PIL import Image

from designer import icons


def test_pick_takes_name_alias_or_word():
    assert icons.pick("database") == "database"
    assert icons.pick("Team") == "users"
    assert icons.pick("truck delivery") == "truck"
    assert icons.pick("шестерёнка") is None
    assert icons.pick(None) is None


def test_icon_png_takes_template_color():
    png = icons.icon_png("clock", "0077FF")
    image = Image.open(io.BytesIO(png)).convert("RGBA")
    colors = {pixel[:3] for pixel in image.getdata() if pixel[3] > 200}
    assert colors == {(0, 0x77, 0xFF)}
    assert icons.dominant_color(png) is not None


def test_every_icon_in_prompt_list_has_a_picture():
    assert len(icons.icon_names()) > 100
    assert all((icons.ICON_DIR / f"{name}.png").is_file() for name in icons.names_text().split(", "))
