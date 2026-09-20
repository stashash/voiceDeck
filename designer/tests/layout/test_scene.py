"""Сборка сцены слайда: фигуры образца, новый текст, переложенные блоки. Задача T-07."""
import re

import pytest
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Emu, Pt

from designer.audit.deterministic import run_checks
from designer.contracts import Item, SlideIntent, SlideKind, TableSpec
from designer.layout.compose import compose
from designer.layout.match import choose_pattern
from designer.layout.scene import build_scene
from designer.parse.package import build_package

_UNIT_ID = re.compile(r"^u(\d+)s\d+$")
_SAMPLE_MIN = 8


def _textbox(slide, left, top, width, height, text, size_pt):
    box = slide.shapes.add_textbox(Emu(left), Emu(top), Emu(width), Emu(height))
    box.text_frame.text = text
    box.text_frame.paragraphs[0].runs[0].font.size = Pt(size_pt)
    return box


def _sample_pptx(path):
    """Шаблон из трёх карточек: заголовок слайда и повторяющийся блок с заголовком и текстом."""
    prs = Presentation()
    prs.slide_width = Emu(9144000)
    prs.slide_height = Emu(5143500)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _textbox(slide, 457200, 228600, 6000000, 700000, "Образцовый заголовок этого шаблона", 32)
    for i in range(3):
        left = 457200 + i * 2743200
        slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Emu(left), Emu(1600000), Emu(2400000), Emu(1800000))
        _textbox(slide, left + 150000, 1750000, 2100000, 400000, "Образец пункта шаблона", 20)
        _textbox(slide, left + 150000, 2250000, 2100000, 1000000, "Образцовое описание пункта в карточке", 12)
    prs.save(str(path))
    return path


@pytest.fixture(scope="module")
def sample_package(tmp_path_factory):
    root = tmp_path_factory.mktemp("obrazec")
    ds = build_package(_sample_pptx(root / "obrazec.pptx"), root / "paket")
    return ds, root / "paket"


def _plan() -> list[SlideIntent]:
    """Шесть намерений разных типов: титул, карточки, шаги, крупное число, таблица, финал."""
    return [
        SlideIntent(id="s1", kind=SlideKind.title, title="Цифровой дизайнер презентаций",
                    key_message="Колода из брифа в стиле вашего шаблона"),
        SlideIntent(id="s2", kind=SlideKind.cards, title="Три причины попробовать",
                    items=[Item(heading="Скорость", body="Колода собирается за минуты"),
                           Item(heading="Стиль", body="Всё берётся из вашего шаблона"),
                           Item(heading="Проверка", body="Аудит ловит наезды и переполнение")]),
        SlideIntent(id="s3", kind=SlideKind.steps, title="Как идёт работа",
                    items=[Item(number="1", heading="Разбор", body="Читаем шаблон"),
                           Item(number="2", heading="План", body="Делим бриф на слайды"),
                           Item(number="3", heading="Вёрстка", body="Кладём слова в слоты"),
                           Item(number="4", heading="Аудит", body="Считаем наезды"),
                           Item(number="5", heading="Экспорт", body="Отдаём файлы")]),
        SlideIntent(id="s4", kind=SlideKind.big_number, title="Сколько это занимает",
                    key_message="Столько идёт сборка колоды целиком",
                    items=[Item(number="5", heading="минут на колоду")]),
        SlideIntent(id="s5", kind=SlideKind.table, title="Что смотрит аудит",
                    table=TableSpec(columns=["Проверка", "Что ловит", "Итог"],
                                    rows=[["Границы", "выход за кадр", "ошибка"],
                                          ["Наезд", "пересечение блоков", "ошибка"],
                                          ["Плотность", "слишком много пунктов", "замечание"]])),
        SlideIntent(id="s6", kind=SlideKind.thanks, title="Спасибо за внимание",
                    key_message="Вопросы и связь"),
    ]


def _deck(ds, package_dir):
    used: list[str] = []
    scenes = []
    for intent in _plan():
        pattern = choose_pattern(intent, ds, used)
        used.append(pattern.id)
        scenes.append(build_scene(compose(intent, pattern, ds), pattern, ds, package_dir))
    return scenes


def _samples(ds) -> set[str]:
    texts = {slot.sample_text.strip() for pattern in ds.patterns for slot in pattern.slots}
    texts |= {slot.sample_text.strip()
              for pattern in ds.patterns for group in pattern.groups for slot in group.unit_slots}
    return {text for text in texts if len(text) >= _SAMPLE_MIN}


def _unit_overlaps(findings) -> list:
    """Наложения между блоками одной группы: оба элемента из разных блоков."""
    out = []
    for finding in findings:
        if finding.check_id != "layout.overlap" or len(finding.element_ids) != 2:
            continue
        left, right = (_UNIT_ID.match(el) for el in finding.element_ids)
        if left and right and left.group(1) != right.group(1):
            out.append(finding)
    return out


# ---------- шаблон, собранный прямо в тесте ----------

def test_blocks_are_rebuilt_for_a_smaller_count(sample_package):
    ds, package_dir = sample_package
    intent = SlideIntent(id="s1", kind=SlideKind.cards, title="Две причины",
                         items=[Item(heading="Скорость", body="Минуты вместо дней"),
                                Item(heading="Стиль", body="Всё из вашего шаблона")])
    pattern = choose_pattern(intent, ds, [])
    scene = build_scene(compose(intent, pattern, ds), pattern, ds, package_dir)

    units = {el.id for el in scene.elements if _UNIT_ID.match(el.id)}
    assert {_UNIT_ID.match(el).group(1) for el in units} == {"0", "1"}
    cards = [el for el in scene.elements if el.type == "shape" and _UNIT_ID.match(el.id)]
    assert len(cards) == 2
    assert cards[0].box[2] > pattern.groups[0].unit_size[0]
    assert cards[0].box[0] + cards[0].box[2] <= cards[1].box[0] + 1e-6


def test_sample_text_does_not_reach_the_scene(sample_package):
    ds, package_dir = sample_package
    intent = SlideIntent(id="s1", kind=SlideKind.cards, title="Две причины",
                         items=[Item(heading="Скорость", body="Минуты вместо дней"),
                                Item(heading="Стиль", body="Всё из вашего шаблона")])
    pattern = choose_pattern(intent, ds, [])
    scene = build_scene(compose(intent, pattern, ds), pattern, ds, package_dir)

    texts = [el.text for el in scene.elements if el.type == "text"]
    assert "Две причины" in texts
    assert all("Образц" not in text and "Образец" not in text for text in texts)


def test_scene_keeps_the_link_to_the_source_shapes(sample_package):
    ds, package_dir = sample_package
    intent = SlideIntent(id="s1", kind=SlideKind.cards, title="Две причины",
                         items=[Item(heading="Скорость", body="Минуты вместо дней")])
    pattern = choose_pattern(intent, ds, [])
    scene = build_scene(compose(intent, pattern, ds), pattern, ds, package_dir)
    assert scene.pattern_id == pattern.id
    assert all(el.source_shape_id is not None for el in scene.elements)


# ---------- выданные шаблоны и сторонний файл ----------

@pytest.fixture(scope="session")
def packages(templates, foreign_pptx, tmp_path_factory):
    root = tmp_path_factory.mktemp("pakety")
    built = []
    for index, path in enumerate([*templates, foreign_pptx]):
        out = root / f"ds{index}"
        built.append((path.stem, build_package(path, out), out))
    return built


def test_six_intents_give_six_scenes_on_every_template(packages):
    for name, ds, package_dir in packages:
        scenes = _deck(ds, package_dir)
        assert len(scenes) == 6, name
        for scene in scenes:
            assert scene.elements, f"{name}, слайд {scene.slide_id}"
            assert any(el.type in ("text", "chart", "table") for el in scene.elements), name


def test_no_sample_text_of_the_template_on_every_template(packages):
    for name, ds, package_dir in packages:
        samples = _samples(ds)
        for scene in _deck(ds, package_dir):
            for el in scene.elements:
                if el.type != "text":
                    continue
                found = [sample for sample in samples if sample in el.text]
                assert not found, f"{name}, слайд {scene.slide_id}: {found[:1]}"


def test_audit_finds_no_out_of_bounds_and_no_overlap_inside_groups(packages):
    for name, ds, package_dir in packages:
        scenes = _deck(ds, package_dir)
        findings = run_checks(scenes, ds)
        out_of_bounds = [f for f in findings if f.check_id == "layout.out_of_bounds"]
        assert not out_of_bounds, f"{name}: {[f.message for f in out_of_bounds[:3]]}"
        overlaps = _unit_overlaps(findings)
        assert not overlaps, f"{name}: {[f.message for f in overlaps[:3]]}"
