"""Схемы запросов и ответов HTTP API. Владелец: задача T-13, варианты — T-12."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from designer.contracts import DeckPlan, Finding, Scene, SkillRef, SlideSpec


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


class LiveBoundaryRequest(BaseModel):
    thought: str = Field(min_length=1, max_length=16000, description="текст текущего слайда: мысль докладчика до сих пор")
    next_sentence: str = Field(min_length=1, max_length=4000, description="следующее распознанное предложение")


class LiveBoundaryResponse(BaseModel):
    new_thought: bool


class LiveSlideResponse(BaseModel):
    scene: Scene
    html: str
    image_png_base64: str | None = Field(default=None,
                                          description="картинка слайда; None, если движка конвертации нет")


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


class SlideNotesRequest(BaseModel):
    notes: str


class DeckRewriteRequest(BaseModel):
    finding_id: str


# ---------- агенты и модели (поток 2 отдаёт содержимое, здесь только форма ответа) ----------

class AgentAssignmentsRequest(BaseModel):
    deck: str | None = None
    live: str | None = None
    describe: str | None = None
