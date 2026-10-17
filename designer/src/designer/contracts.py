"""Общие контракты сервиса «Цифровой дизайнер презентаций».

От этих моделей зависят все слои: разбор, план, вёрстка, аудит, экспорт.
Менять файл можно только отдельной задачей, иначе параллельные полосы разойдутся.

Координаты: Box = (x, y, w, h) в долях слайда, от 0 до 1, начало в левом верхнем углу.
Цвет: шесть шестнадцатеричных знаков в верхнем регистре без решётки, например "0077FF".
"""
from __future__ import annotations

from enum import Enum
import math
from typing import Literal

from pydantic import BaseModel, Field, model_validator

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
    embedded_state: Literal["extracted", "embedded_not_extracted", "missing"] = Field(
        default="missing",
        description="extracted — embedded_file заполнен; embedded_not_extracted — шрифт в ppt/fonts/*.fntdata "
                    "есть, но сжат и не извлекается; missing — в файле шрифта нет",
    )


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
    placeholder: bool = Field(default=False, description="серая заглушка под фото или картинку: без своей картинки слайд выглядит недоделанным")


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
    linked_group_ids: list[str] = Field(default_factory=list, description="группы, которые повторяются синхронно с этой: ряд номеров и ряд подписей под ними это один смысловой блок")


class DecorShape(BaseModel):
    """Фигура оформления с рамкой: вёрстка решает по ней, мешает ли оформление содержимому."""
    shape_id: int
    box: Box
    kind: Literal["shape", "image", "line", "text", "other"] = "shape"


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
    purpose: str = Field(default="", description="для какого содержания слайд, одной фразой; пишет модель по картинке слайда")
    needs_images: bool = Field(default=False, description="паттерн держится на фото или картинках, которых у нас может не быть")
    primary_group_id: str | None = Field(default=None, description="главная группа блоков, в неё идут пункты слайда")
    slots: list[Slot] = Field(default_factory=list)
    areas: list[Area] = Field(default_factory=list)
    groups: list[RepeatGroup] = Field(default_factory=list)
    decor_shape_ids: list[int] = Field(default_factory=list, description="фигуры оформления, которые при сборке не трогаем")
    decor: list[DecorShape] = Field(default_factory=list, description="те же фигуры оформления с рамками; у блоков групп оформление лежит в RepeatUnit.shape_ids")
    preview: str | None = None


class LayoutInfo(BaseModel):
    name: str
    master_index: int
    placeholders: list[Slot] = Field(default_factory=list)
    full_bleed_picture: bool = Field(default=False, description="макет несёт картинку на весь кадр: в ней могут быть нарисованы подложки и номера блоков образца")
    pictures: list[Box] = Field(default_factory=list, description="картинки макета не на весь кадр: диаграмма и таблица на них не встают")


class DescribeStatus(BaseModel):
    """Ход описания образцов моделью: пишет pipeline.run_describe, читает экран поллингом."""
    status: Literal["pending", "running", "done", "failed"] = "pending"
    done: int = 0
    total: int = 0
    error: str = ""


class DesignSystem(BaseModel):
    schema_version: str = SCHEMA_VERSION
    id: str
    source_file: str = Field(description="имя исходного файла без пути")
    name: str = Field(default="", description="имя системы; по умолчанию из имени файла")
    created_at: str = Field(default="", description="время импорта, ISO 8601")
    slide_size_emu: tuple[int, int]
    tokens: Tokens
    assets: list[Asset] = Field(default_factory=list)
    layouts: list[LayoutInfo] = Field(default_factory=list)
    patterns: list[Pattern] = Field(default_factory=list)
    pattern_overrides: dict[str, bool] = Field(
        default_factory=dict,
        description="решение автора по образцу: true — в вёрстке, false — убран; "
                    "нет ключа — действует предложение модели needs_images",
    )
    removal_confirmed: bool = Field(default=False, description="автор нажал «Согласен» под полосой убранных образцов")
    describe: DescribeStatus = Field(default_factory=DescribeStatus)


# ---------- План презентации ----------

class Item(BaseModel):
    heading: str = ""
    body: str = ""
    number: str | None = None
    icon_hint: str | None = None


class Series(BaseModel):
    name: str
    values: list[float]
    x_values: list[float] | None = None


class ChartSpec(BaseModel):
    type: Literal["column", "bar", "line", "pie", "donut", "scatter", "grouped_column", "stacked_column"]
    title: str = ""
    categories: list[str] = Field(default_factory=list)
    series: list[Series]
    unit: str = ""
    x_axis_title: str = ""
    y_axis_title: str = ""

    @model_validator(mode="after")
    def validate_extended_chart(self):
        if self.type not in {"scatter", "grouped_column", "stacked_column"}:
            if any(s.x_values is not None for s in self.series):
                raise ValueError("x_values are only supported by scatter charts")
            return self
        if not 1 <= len(self.series) <= 5:
            raise ValueError("Extended charts need one to five series")
        for series in self.series:
            if not series.values or not all(math.isfinite(v) for v in series.values):
                raise ValueError("Chart values must be nonempty and finite")
            if self.type == "scatter":
                if self.categories or series.x_values is None or len(series.x_values) != len(series.values):
                    raise ValueError("Scatter requires paired x_values and values without categories")
                if not all(math.isfinite(v) for v in series.x_values):
                    raise ValueError("Scatter X values must be finite")
            elif series.x_values is not None or len(series.values) != len(self.categories):
                raise ValueError("Column series must match the categories; no zero filling")
        if self.type == "stacked_column":
            totals = [sum(s.values[i] for s in self.series) for i in range(len(self.categories))]
            if any(v < 0 for s in self.series for v in s.values) or not all(math.isfinite(v) for v in totals):
                raise ValueError("Stacked composition requires nonnegative values and finite totals")
        return self


class TableSpec(BaseModel):
    columns: list[str]
    rows: list[list[str]]


class SlideImage(BaseModel):
    """Картинка слайда от модели text-to-image: что нарисовано и где лежит файл."""
    prompt: str
    path: str = Field(default="", description="файл картинки относительно каталога данных designer")
    alt: str = ""


class DataProvenance(BaseModel):
    """Server-computed evidence for an analytical slide; never model-generated."""
    version: int = 1
    dataset_id: str
    source_sha256: str
    content_hash: str
    file_name: str
    sheet: str = ""
    table_index: int
    columns: list[str]
    total_rows: int
    row_lines: list[int]
    excluded_row_lines: list[int]
    displayed_row_lines: list[int]
    visualization: str
    aggregation: str
    missing_policy: str
    formula: str
    unit: str = ""
    denominator: str | None = None
    denominator_field: str | None = None
    warnings: list[str] = Field(default_factory=list)
    page_index: int | None = None
    page_count: int | None = None


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
    source_note: str = ""
    provenance: DataProvenance | None = None
    image: SlideImage | None = Field(default=None, description="ставит шаг иллюстраций, не план")


class DeckPlan(BaseModel):
    title: str
    purpose: str = Field(description="фича, продукт, проект, инициатива или свободная формулировка")
    audience: str = ""
    language: str = "ru"
    slides: list[SlideIntent]


# ---------- Вёрстка ----------

class ElementPosition(BaseModel):
    original_box: Box
    box: Box
    source_shape_id: int | None = None
    deleted: bool = False
    text: str | None = None
    style: TextStyle | None = None
    fill: str | None = None
    z: int | None = None


class SlideSpec(BaseModel):
    """Инструкция сборки слайда на паттерне: какой образец клонировать и чем заполнить."""
    slide_id: str
    pattern_id: str
    variant: str = "a"
    slot_text: dict[str, str] = Field(default_factory=dict, description="id слота паттерна -> текст")
    element_positions: dict[str, ElementPosition] = Field(default_factory=dict)
    added_elements: list[Element] = Field(default_factory=list)
    background_color: str | None = None
    group_id: str | None = None
    unit_text: list[dict[str, str]] = Field(default_factory=list, description="по блоку: id слота блока -> текст")
    linked_unit_text: dict[str, list[dict[str, str]]] = Field(default_factory=dict, description="id связанной группы -> тексты её блоков; число блоков то же, что в unit_text")
    fitted_size_pt: dict[str, float] = Field(default_factory=dict, description="id слота или слота блока -> кегль после подгонки; экспорт ставит его фигурам")
    unit_icons: list[str | None] = Field(default_factory=list, description="по блоку: имя пиктограммы из набора designer/icons вместо значка образца; None оставляет значок образца")
    viz_box: Box | None = Field(default=None, description="рамка диаграммы или таблицы, её выбирает вёрстка")
    remove_shape_ids: list[int] = Field(default_factory=list, description="фигуры образца, которые вёрстка решила убрать: незаполненные группы, образцы в рамке визуализации, заглушки под фото")
    chart: ChartSpec | None = None
    table: TableSpec | None = None
    viz_area_id: str | None = None
    notes: str = ""
    image_area_id: str | None = Field(default=None, description="место образца, где фото образца меняется на картинку слайда")
    image_path: str | None = Field(default=None, description="файл картинки относительно каталога данных designer")


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
    icon: str | None = Field(default=None, description="пиктограмма набора designer/icons вместо картинки образца")
    image: str | None = Field(default=None, description="картинка слайда вместо фото образца: файл относительно каталога данных")
    source_shape_id: int | None = None
    chart: ChartSpec | None = None
    table: TableSpec | None = None


# Resolve Element before request threads can trigger concurrent lazy rebuilds.
SlideSpec.model_rebuild()


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
