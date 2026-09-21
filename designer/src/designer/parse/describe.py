"""Описание слайда-образца по его картинке. Владелец: задача T-18.

Геометрия говорит, из чего слайд собран, но не говорит, для какого содержания он сделан.
Это досказывает модель по картинке: тип, назначение одной фразой и нужны ли свои фото.
Картинки слайдов готовит вызывающий код, живых вызовов здесь нет.
"""
from __future__ import annotations

import httpx

from designer.contracts import DesignSystem, Pattern, SlideKind
from designer.llm.client import LlmClient, LlmResponseError
from designer.llm.skills import Skill, load_skill

SKILL = "describe-pattern"

CONFIDENT = 0.7
"""Уверенность разбора, выше которой тип слайда модель не трогает."""

# Сервер не ответил или ответил мимо схемы: паттерн остаётся таким, каким его дал разбор.
_FAILURES = (LlmResponseError, httpx.HTTPError)

_KINDS = {k.value: k for k in SlideKind}

_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": [k.value for k in SlideKind]},
        "purpose": {"type": "string", "description": "для какого содержания слайд, одной фразой"},
        "needs_images": {"type": "boolean", "description": "слайд держится на фото или картинках"},
    },
    "required": ["kind", "purpose", "needs_images"],
}


def _facts(pattern: Pattern) -> str:
    """Что о слайде уже знает разбор: модель смотрит на картинку, а это подсказка о составе."""
    groups = ", ".join(
        f"{len(g.units)} блоков по {len(g.unit_slots)} подписей" for g in pattern.groups
    )
    lines = [
        f"Текстовых мест: {len(pattern.slots)}.",
        f"Повторяющихся групп: {len(pattern.groups)}" + (f" ({groups})." if groups else "."),
        f"Нетекстовых мест: {len(pattern.areas)}.",
    ]
    return "\n".join(lines)


def _describe_one(pattern: Pattern, png: bytes | None, skill: Skill, client: LlmClient) -> Pattern:
    if not png:
        return pattern
    try:
        data = client.complete_json(
            system=skill.render(),
            user=_facts(pattern),
            schema=_SCHEMA,
            images_png=[png],
            params=skill.params,
        )
    except _FAILURES:
        return pattern

    kind = pattern.kind
    if pattern.kind_confidence < CONFIDENT:
        kind = _KINDS.get(str(data.get("kind", "")), pattern.kind)
    return pattern.model_copy(update={
        "kind": kind,
        "purpose": str(data.get("purpose", "")).strip() or pattern.purpose,
        "needs_images": pattern.needs_images or bool(data.get("needs_images")),
    })


def describe_patterns(ds: DesignSystem, pngs: dict[str, bytes], client: LlmClient) -> DesignSystem:
    """Дописать паттернам назначение и уточнить тип по картинкам слайдов; ключ pngs это Pattern.id."""
    skill = load_skill(SKILL)
    described = [_describe_one(p, pngs.get(p.id), skill, client) for p in ds.patterns]
    return ds.model_copy(update={"patterns": described})
