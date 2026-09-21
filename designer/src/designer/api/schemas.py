"""Схемы запросов и ответов HTTP API. Владелец: задача T-13."""
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


class DeckCreateResponse(BaseModel):
    deck_id: str


class DeckStateResponse(BaseModel):
    status: Literal["running", "done", "error"]
    design_system_id: str
    plan: DeckPlan | None = None
    specs: list[SlideSpec] = Field(default_factory=list)
    scenes: list[Scene] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    error: str | None = None


class LiveSlideRequest(BaseModel):
    design_system_id: str
    chunk_text: str
    used_pattern_ids: list[str] = Field(default_factory=list)


class LiveSlideResponse(BaseModel):
    scene: Scene
    html: str


class HealthResponse(BaseModel):
    model_ok: bool
    converters: list[str]
    skills: list[SkillRef]


class DesignSystemListResponse(BaseModel):
    ids: list[str]
