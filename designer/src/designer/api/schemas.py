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
    variants: list[str] = Field(default_factory=lambda: ["a"], description="a, b, c — любое подмножество")


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


class LiveSlideResponse(BaseModel):
    scene: Scene
    html: str
    image_png_base64: str | None = Field(default=None,
                                          description="картинка слайда; None, если движка конвертации нет")


class HealthResponse(BaseModel):
    model_ok: bool
    converters: list[str]
    skills: list[SkillRef]


class DesignSystemListResponse(BaseModel):
    ids: list[str]
