"""Схемы запросов и ответов HTTP API. Владелец: задача T-13, варианты — T-12."""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from designer.contracts import DeckPlan, Finding, Scene, SkillRef, SlideSpec, TableSpec


class DeckCreateRequest(BaseModel):
    design_system_id: str
    brief: str
    purpose: str = ""
    audience: str = ""
    slide_count: int | None = None
    variants: list[str] = Field(default_factory=lambda: ["a", "b", "c"], description="a, b, c — любое подмножество")


class DeckCreateResponse(BaseModel):
    deck_id: str


class DeckVariantState(BaseModel):
    """Состояние одного варианта колоды: своя инструкция, сцены, находки и обоснование оси."""
    status: Literal["running", "done", "error"]
    revision: str | None = None
    design_system_id: str
    plan: DeckPlan | None = None
    specs: list[SlideSpec] = Field(default_factory=list)
    scenes: list[Scene] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    error: str | None = None
    slide_images: list[str] = Field(default_factory=list,
                                     description="адреса картинок слайдов по порядку; пусто, если движка нет")
    brief: str = Field(default="", description="бриф автора, с которого собрана колода")


class DeckStateResponse(BaseModel):
    """Состояние колоды. Верхний уровень — вариант `a` (старые клиенты); variants — все варианты."""
    status: Literal["running", "done", "error"]
    design_system_id: str
    plan: DeckPlan | None = None
    specs: list[SlideSpec] = Field(default_factory=list)
    scenes: list[Scene] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    error: str | None = None
    slide_images: list[str] = Field(default_factory=list)
    brief: str = ""
    variants: dict[str, DeckVariantState] = Field(default_factory=dict)


class AuditContextualResponse(BaseModel):
    findings: list[Finding]


class DeckFixRequest(BaseModel):
    finding_ids: list[str]


class DeckFixResponse(BaseModel):
    report: list[dict]
    findings: list[Finding]


class LiveSlideRequest(BaseModel):
    design_system_id: str
    chunk_text: str
    used_pattern_ids: list[str] = Field(default_factory=list)


class LiveWarmRequest(BaseModel):
    design_system_id: str


class LiveBoundaryRequest(BaseModel):
    thought: str = Field(min_length=1, max_length=16000, description="текст текущего слайда: мысль докладчика до сих пор")
    next_sentence: str = Field(min_length=1, max_length=4000, description="следующее распознанное предложение")


class LiveBoundaryResponse(BaseModel):
    new_thought: bool
    timings: dict[str, int] = Field(default_factory=dict, description="время ответа модели и ожидания, мс")


class LiveSlideResponse(BaseModel):
    scene: Scene
    html: str
    image_png_base64: str | None = Field(default=None,
                                          description="картинка слайда; None, если движка конвертации нет")
    timings: dict[str, int] = Field(default_factory=dict,
                                     description="время этапов слайда, мс: модель, картинка, всего, запросов к модели в работе")


class HealthResponse(BaseModel):
    model_ok: bool
    converters: list[str]
    skills: list[SkillRef]


class DesignSystemListItem(BaseModel):
    id: str
    name: str
    source_file: str
    patterns: int
    preview: str | None = None
    created_at: str
    describe_status: Literal["pending", "running", "done", "failed"]


class DesignSystemListResponse(BaseModel):
    ids: list[str]
    items: list[DesignSystemListItem] = Field(default_factory=list)


class DesignSystemPatchRequest(BaseModel):
    name: str | None = None
    pattern_overrides: dict[str, bool] | None = None
    removal_confirmed: bool | None = None


# ---------- колоды: список, правка варианта ----------

class DeckListItem(BaseModel):
    id: str
    title: str
    design_system_id: str
    slides: int
    status: Literal["running", "done", "error"]
    started_at: str
    preview: str | None = None


class DeckListResponse(BaseModel):
    items: list[DeckListItem] = Field(default_factory=list)


class SlideTextRequest(BaseModel):
    element_id: str
    text: str


class SlideMoveElementRequest(BaseModel):
    element_id: str
    dx: float = Field(default=0, ge=-1, le=1, allow_inf_nan=False)
    dy: float = Field(default=0, ge=-1, le=1, allow_inf_nan=False)
    align: Literal['left', 'right', 'top', 'bottom', 'center'] | None = None


_CellText = Annotated[str, Field(strict=True, max_length=10000)]


class ElementTableRequest(TableSpec):
    model_config = ConfigDict(extra='forbid')
    columns: list[_CellText] = Field(min_length=1, max_length=5)
    rows: list[list[_CellText]] = Field(max_length=7)

    @model_validator(mode='after')
    def rectangular(self) -> ElementTableRequest:
        if any(len(row) != len(self.columns) for row in self.rows):
            raise ValueError('Every table row must match the number of columns')
        return self


class ElementActionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['add', 'delete', 'duplicate', 'style', 'background', 'z_order',
                    'table_cell', 'table_row_add', 'table_row_delete',
                    'table_column_add', 'table_column_delete']
    element_id: str | None = Field(default=None, min_length=1, max_length=200, pattern=r'\S')
    element_type: Literal['text', 'title', 'shape', 'card', 'table'] = 'text'
    text: _CellText = ''
    scale: float = Field(default=1, ge=.25, le=4, allow_inf_nan=False, strict=True)
    size_pt: float | None = Field(default=None, ge=6, le=144, allow_inf_nan=False, strict=True)
    color: str | None = Field(default=None, pattern=r'^[0-9A-Fa-f]{6}$')
    bold: bool | None = Field(default=None, strict=True)
    italic: bool | None = Field(default=None, strict=True)
    text_align: Literal['left', 'center', 'right'] | None = None
    fill: str | None = Field(default=None, pattern=r'^[0-9A-Fa-f]{6}$')
    width: float | None = Field(default=None, gt=0, le=1, allow_inf_nan=False, strict=True)
    height: float | None = Field(default=None, gt=0, le=1, allow_inf_nan=False, strict=True)
    order: Literal['front', 'back'] | None = None
    table: ElementTableRequest | None = None
    row: int | None = Field(default=None, ge=0, le=8, strict=True)
    column: int | None = Field(default=None, ge=1, le=6, strict=True)
    values: list[_CellText] | None = Field(default=None, max_length=7)

    @model_validator(mode='after')
    def action_fields(self) -> ElementActionRequest:
        allowed = {
            'add': {'element_type', 'text', 'width', 'height', 'fill', 'table'},
            'delete': set(), 'duplicate': set(),
            'style': {'size_pt', 'scale', 'color', 'bold', 'italic', 'text_align', 'fill', 'width', 'height'},
            'background': {'color'}, 'z_order': {'order'},
            'table_cell': {'row', 'column', 'text'},
            'table_row_add': {'row', 'values'}, 'table_row_delete': {'row'},
            'table_column_add': {'column', 'text', 'values'}, 'table_column_delete': {'column'},
        }[self.action]
        required = {
            'background': {'color'}, 'z_order': {'order'},
            'table_cell': {'row', 'column', 'text'},
            'table_row_delete': {'row'}, 'table_column_delete': {'column'},
        }.get(self.action, set())
        supplied = self.model_fields_set - {'action', 'element_id'}
        if supplied - allowed:
            raise ValueError(f'Unsupported fields for {self.action}: {sorted(supplied - allowed)}')
        if required - supplied:
            raise ValueError(f'Missing fields for {self.action}: {sorted(required - supplied)}')
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError('Omit unused fields; explicit null values are not supported')
        if self.action in ('add', 'background'):
            if self.element_id is not None:
                raise ValueError(f'{self.action} does not accept an element target')
        elif not self.element_id:
            raise ValueError('element_id is required')
        if self.action == 'style':
            if not supplied:
                raise ValueError('style requires at least one property')
            if {'size_pt', 'scale'} <= supplied:
                raise ValueError('Use either size_pt or scale')
        if self.action == 'add':
            if 'table' in supplied and self.element_type != 'table':
                raise ValueError('table data requires element_type table')
            if 'fill' in supplied and self.element_type not in ('shape', 'card'):
                raise ValueError('fill is supported only for shapes and cards')
            if 'text' in supplied and self.element_type not in ('text', 'title', 'card'):
                raise ValueError('text is supported only for text, titles and cards')
        if self.action in ('table_row_add', 'table_row_delete') and self.row == 0:
            raise ValueError('Body row indices start at 1')
        return self


class SlidePatternRequest(BaseModel):
    pattern_id: str


class SlidePatternOption(BaseModel):
    pattern_id: str
    kind: str
    preview: str | None = None
    current: bool = False


class SlidePatternsResponse(BaseModel):
    items: list[SlidePatternOption] = Field(default_factory=list)


class SlideAskRequest(BaseModel):
    instruction: str


class SlideActionRequest(BaseModel):
    action: Literal["add", "copy", "delete", "move"]
    index: int
    to: int | None = None
    expected_revision: str | None = Field(default=None, strict=True)
    target_slide_id: str | None = Field(default=None, min_length=1, strict=True)

    @model_validator(mode='after')
    def complete_preconditions(self) -> SlideActionRequest:
        if {'expected_revision', 'target_slide_id'} & self.model_fields_set:
            if self.expected_revision is None or self.target_slide_id is None:
                raise ValueError('expected_revision and target_slide_id must be supplied together')
        return self


class SlideNotesRequest(BaseModel):
    notes: str


class DeckRewriteRequest(BaseModel):
    finding_id: str


# ---------- агенты и модели (поток 2 отдаёт содержимое, здесь только форма ответа) ----------

class AgentAssignmentsRequest(BaseModel):
    deck: str | None = None
    live: str | None = None
    describe: str | None = None


class ModelSettingsRequest(BaseModel):
    """Экран «Агенты и модели»: адрес сервера модели, модель по умолчанию, модели CLI-агентов."""
    llm_url: str | None = Field(default=None, max_length=500)
    llm_model: str | None = Field(default=None, max_length=200)
    cli_models: dict[str, str] | None = None
