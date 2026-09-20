"""Общие контракты сервиса «Цифровой дизайнер презентаций».

От этих моделей зависят все слои: разбор, план, вёрстка, аудит, экспорт.
Менять файл можно только отдельной задачей, иначе параллельные полосы разойдутся.

Координаты: Box = (x, y, w, h) в долях слайда, от 0 до 1, начало в левом верхнем углу.
Цвет: шесть шестнадцатеричных знаков в верхнем регистре без решётки, например "0077FF".
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1"

Box = tuple[float, float, float, float]


class SlideKind(str, Enum):
    title = "title"
    section = "section"
    agenda = "agenda"
    bullets = "bullets"
    cards = "cards"
    steps = "steps"
    big_number = "big_number"
    quote = "quote"
    team = "team"
    timeline = "timeline"
    chart = "chart"
    table = "table"
    compare = "compare"
    image_text = "image_text"
    code = "code"
    cta = "cta"
    thanks = "thanks"
    other = "other"


# ---------- Дизайн-система: результат разбора pptx ----------

class ColorToken(BaseModel):
    hex: str
    role: Literal["background", "surface", "text", "text_muted", "accent", "accent_alt", "other"]
    share: float = Field(ge=0, le=1, description="доля среди цветов этого источника")
    source: Literal["theme", "usage"]


class FontToken(BaseModel):
    family: str
    role: Literal["heading", "body", "mono", "other"]
    share: float = Field(ge=0, le=1)
    embedded_file: str | None = Field(default=None, description="путь внутри пакета, если шрифт встроен в pptx")


class TypeStep(BaseModel):
    size_pt: float
    role: Literal["display", "title", "heading", "body", "caption"]
    share: float = Field(ge=0, le=1)


class Margins(BaseModel):
    left: float
    top: float
    right: float
    bottom: float


class Tokens(BaseModel):
    colors: list[ColorToken]
    fonts: list[FontToken]
    type_scale: list[TypeStep]
    margins: Margins
    guides_x: list[float] = Field(default_factory=list, description="частые левые края блоков, доли ширины")
    guides_y: list[float] = Field(default_factory=list, description="частые верхние края блоков, доли высоты")


class Asset(BaseModel):
    id: str
    path: str = Field(description="путь внутри пакета дизайн-системы")
    kind: Literal["background", "logo", "decor", "icon", "photo", "other"]
    width_px: int
    height_px: int
    sha1: str
    used_on: list[int] = Field(default_factory=list, description="номера слайдов с единицы; 0 означает макет или мастер")


class TextStyle(BaseModel):
    family: str | None = None
    size_pt: float | None = None
    bold: bool = False
    italic: bool = False
    color: str | None = None
    align: Literal["left", "center", "right"] | None = None


SlotRole = Literal["title", "subtitle", "heading", "body", "caption", "number", "label", "footer", "other"]


class Slot(BaseModel):
    """Текстовое место паттерна. shape_id это id фигуры в исходном pptx."""
    id: str
    role: SlotRole
    shape_id: int
    box: Box
    style: TextStyle = Field(default_factory=TextStyle)
    max_chars: int = Field(description="сколько знаков помещается при исходном кегле")
    max_lines: int
    sample_text: str = ""


class Area(BaseModel):
    """Нетекстовое место: картинка, значок, диаграмма, таблица."""
    id: str
    kind: Literal["image", "icon", "chart", "table"]
    box: Box
    shape_id: int | None = None


class RepeatUnit(BaseModel):
    index: int
    box: Box
    shape_ids: list[int]


class RepeatGroup(BaseModel):
    """Повторяющийся блок слайда: карточки, шаги, строки списка.

    unit_slots и unit_areas описаны по первому блоку; их box задан относительно
    левого верхнего угла блока, в долях слайда.
    """
    id: str
    direction: Literal["row", "column", "grid"]
    cols: int
    rows: int
    step: tuple[float, float] = Field(description="шаг между блоками по x и по y")
    unit_size: tuple[float, float]
    units: list[RepeatUnit]
    unit_slots: list[Slot] = Field(default_factory=list)
    unit_areas: list[Area] = Field(default_factory=list)
    min_units: int = 1
    max_units: int = Field(description="сколько блоков помещается на сетке шаблона без выхода в поля")


class Pattern(BaseModel):
    """Слайд-образец как паттерн вёрстки."""
    id: str
    source_slide: int = Field(description="номер слайда в исходном файле, с единицы")
    layout_name: str
    kind: SlideKind
    kind_confidence: float = Field(ge=0, le=1)
    theme: Literal["light", "dark"]
    background_asset: str | None = Field(default=None, description="Asset.id картинки фона: первые 12 знаков sha1 содержимого")
    background_color: str | None = None
    slots: list[Slot] = Field(default_factory=list)
    areas: list[Area] = Field(default_factory=list)
    groups: list[RepeatGroup] = Field(default_factory=list)
    decor_shape_ids: list[int] = Field(default_factory=list, description="фигуры оформления, которые при сборке не трогаем")
    preview: str | None = None


class LayoutInfo(BaseModel):
    name: str
    master_index: int
    placeholders: list[Slot] = Field(default_factory=list)


class DesignSystem(BaseModel):
    schema_version: str = SCHEMA_VERSION
    id: str
    source_file: str = Field(description="имя исходного файла без пути")
    slide_size_emu: tuple[int, int]
    tokens: Tokens
    assets: list[Asset] = Field(default_factory=list)
    layouts: list[LayoutInfo] = Field(default_factory=list)
    patterns: list[Pattern] = Field(default_factory=list)


# ---------- План презентации ----------

class Item(BaseModel):
    heading: str = ""
    body: str = ""
    number: str | None = None
    icon_hint: str | None = None


class Series(BaseModel):
    name: str
    values: list[float]


class ChartSpec(BaseModel):
    type: Literal["column", "bar", "line", "pie", "donut"]
    title: str = ""
    categories: list[str]
    series: list[Series]
    unit: str = ""


class TableSpec(BaseModel):
    columns: list[str]
    rows: list[list[str]]


class SlideIntent(BaseModel):
    """Что слайд должен сказать, до выбора паттерна."""
    id: str
    kind: SlideKind
    title: str
    key_message: str = ""
    items: list[Item] = Field(default_factory=list)
    chart: ChartSpec | None = None
    table: TableSpec | None = None
    attribution: str = Field(default="", description="автор цитаты или подпись")
    notes: str = ""


class DeckPlan(BaseModel):
    title: str
    purpose: str = Field(description="фича, продукт, проект, инициатива или свободная формулировка")
    audience: str = ""
    language: str = "ru"
    slides: list[SlideIntent]


# ---------- Вёрстка ----------

class SlideSpec(BaseModel):
    """Инструкция сборки слайда на паттерне: какой образец клонировать и чем заполнить."""
    slide_id: str
    pattern_id: str
    variant: str = "a"
    slot_text: dict[str, str] = Field(default_factory=dict, description="id слота паттерна -> текст")
    group_id: str | None = None
    unit_text: list[dict[str, str]] = Field(default_factory=list, description="по блоку: id слота блока -> текст")
    chart: ChartSpec | None = None
    table: TableSpec | None = None
    viz_area_id: str | None = None
    notes: str = ""


class Element(BaseModel):
    """Объект готового слайда с окончательной геометрией."""
    id: str
    type: Literal["text", "shape", "image", "icon", "chart", "table"]
    role: str = "other"
    box: Box
    z: int = 0
    text: str = ""
    style: TextStyle | None = None
    fill: str | None = None
    asset: str | None = None
    source_shape_id: int | None = None
    chart: ChartSpec | None = None
    table: TableSpec | None = None


class Scene(BaseModel):
    slide_id: str
    pattern_id: str
    variant: str = "a"
    theme: Literal["light", "dark"] = "light"
    background_asset: str | None = None
    background_color: str | None = None
    elements: list[Element] = Field(default_factory=list)


class Deck(BaseModel):
    id: str
    design_system_id: str
    variant: str
    plan: DeckPlan
    specs: list[SlideSpec] = Field(default_factory=list)
    scenes: list[Scene] = Field(default_factory=list)


# ---------- Аудит ----------

class Finding(BaseModel):
    id: str
    slide_id: str
    check_id: str
    kind: Literal["deterministic", "contextual"]
    severity: Literal["error", "warning"]
    message: str
    element_ids: list[str] = Field(default_factory=list)
    box: Box | None = None
    fixable: bool = False
    fix_hint: str = ""


# ---------- Версии скиллов и агентов ----------

class SkillRef(BaseModel):
    name: str
    version: str
    sha256: str


class RunManifest(BaseModel):
    run_id: str
    started_at: str
    model: str
    design_system_id: str | None = None
    skills: list[SkillRef] = Field(default_factory=list)
    timings_ms: dict[str, int] = Field(default_factory=dict)
