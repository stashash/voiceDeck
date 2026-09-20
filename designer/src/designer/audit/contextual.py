"""Контекстные проверки по картинке слайда и по текстам колоды. Владелец: задача T-10.

Вопросы взяты из приложения 1 к ТЗ («Валидация контента»). Ответ модели строится по
схеме, которую собирает код из реестра CONTEXT_CHECKS: не нужно зашивать JSON-схему
в промпт, промпт только объясняет, какой ключ ответа за какой вопрос отвечает.
"""
from __future__ import annotations

from typing import NamedTuple

import httpx

from designer.contracts import Finding, Scene
from designer.llm.client import LlmClient, LlmResponseError
from designer.llm.skills import load_skill

_SLIDE_SKILL = "audit-slide"
_DECK_SKILL = "audit-deck"
_UNAVAILABLE = "context.unavailable"


class ContextCheckDef(NamedTuple):
    id: str
    question_ru: str
    level: str  # "slide" или "deck"


CONTEXT_CHECKS: list[ContextCheckDef] = [
    ContextCheckDef("context.title_is_conclusion", "Заголовок содержит вывод, а не просто называет тему?", "slide"),
    ContextCheckDef("context.body_matches_title", "Содержимое слайда соответствует заголовку?", "slide"),
    ContextCheckDef("context.one_sentence", "Слайд пересказывается одним предложением?", "slide"),
    ContextCheckDef("context.facts_in_source", "Все цифры и факты со слайда есть в исходных материалах?", "slide"),
    ContextCheckDef("context.has_content", "На слайде есть содержание, а не только заголовок?", "slide"),
    ContextCheckDef("context.visuals_on_topic", "Картинки и иконки относятся к теме слайда?", "slide"),
    ContextCheckDef("context.no_service_text", "Нет служебного мусора: реплик спикера, кусков промпта?", "slide"),
    ContextCheckDef("context.no_typos", "Текст без опечаток?", "slide"),
    ContextCheckDef("context.table_rows_work", "Все строки таблицы и элементы легенды работают на мысль слайда?", "slide"),
    ContextCheckDef("context.one_language", "Вся колода на одном языке?", "deck"),
    ContextCheckDef("context.neighbors_linked", "Соседние слайды связаны между собой по логике?", "deck"),
]

_SLIDE_CHECKS = [c for c in CONTEXT_CHECKS if c.level == "slide"]
_DECK_CHECKS = [c for c in CONTEXT_CHECKS if c.level == "deck"]

# Ошибки, при которых сервер не дал пригодный ответ: битый JSON после всех попыток
# или сам запрос не прошёл (сеть, таймаут, 5xx). Слайд получает context.unavailable,
# а не роняет аудит всей колоды.
_SERVER_FAILURES = (LlmResponseError, httpx.HTTPError)


def _short(check_id: str) -> str:
    return check_id.split(".", 1)[1]


def _answer_schema(checks: list[ContextCheckDef], extra_props: dict | None = None,
                    extra_required: list[str] | None = None) -> dict:
    props: dict = {}
    for check in checks:
        properties = {"answer": {"type": "boolean"}, "reason": {"type": "string"}}
        required = ["answer", "reason"]
        if extra_props:
            properties = {**properties, **extra_props}
            required = required + list(extra_required or [])
        props[_short(check.id)] = {
            "type": "object",
            "description": check.question_ru,
            "properties": properties,
            "required": required,
        }
    return {"type": "object", "properties": props, "required": list(props.keys())}


def _scene_text(scene: Scene) -> str:
    lines = [f"{el.role}: {el.text.strip()}" for el in scene.elements if el.type == "text" and el.text.strip()]
    return "\n".join(lines) if lines else "(текстовых элементов нет)"


def _deck_text(scenes: list[Scene]) -> str:
    return "\n\n".join(f"Слайд {scene.slide_id}:\n{_scene_text(scene)}" for scene in scenes)


def _unavailable_finding(slide_id: str, message: str) -> Finding:
    return Finding(
        id="", slide_id=slide_id, check_id=_UNAVAILABLE, kind="contextual",
        severity="warning", message=message, element_ids=[], box=None, fixable=False,
    )


def _findings_from_slide_answers(slide_id: str, data: dict) -> list[Finding]:
    findings: list[Finding] = []
    for check in _SLIDE_CHECKS:
        answer = data.get(_short(check.id), {})
        if answer.get("answer", True):
            continue
        reason = str(answer.get("reason", "")).strip() or check.question_ru
        findings.append(Finding(
            id="", slide_id=slide_id, check_id=check.id, kind="contextual",
            severity="warning", message=reason, element_ids=[], box=None, fixable=False,
        ))
    return findings


def audit_slide(scene: Scene, png: bytes, source_text: str, client: LlmClient) -> list[Finding]:
    """Контекстные проверки одного слайда по его картинке. Рендер картинки — забота вызывающего кода."""
    skill = load_skill(_SLIDE_SKILL)
    schema = _answer_schema(_SLIDE_CHECKS)
    system = skill.render()
    user = f"Исходные материалы:\n{source_text}\n\nТекст слайда по данным сборки:\n{_scene_text(scene)}"
    try:
        data = client.complete_json(system=system, user=user, schema=schema,
                                     images_png=[png], params=skill.params)
    except _SERVER_FAILURES as exc:
        return [_unavailable_finding(scene.slide_id, f"Контекстная проверка слайда не выполнена: {exc}")]
    return _findings_from_slide_answers(scene.slide_id, data)


def _findings_from_deck_answers(scenes: list[Scene], data: dict) -> list[Finding]:
    valid_ids = {scene.slide_id for scene in scenes}
    fallback_id = scenes[0].slide_id
    findings: list[Finding] = []
    for check in _DECK_CHECKS:
        answer = data.get(_short(check.id), {})
        if answer.get("answer", True):
            continue
        reason = str(answer.get("reason", "")).strip() or check.question_ru
        slide_id = str(answer.get("break_slide_id", "")).strip()
        if slide_id not in valid_ids:
            slide_id = fallback_id
        findings.append(Finding(
            id="", slide_id=slide_id, check_id=check.id, kind="contextual",
            severity="warning", message=reason, element_ids=[], box=None, fixable=False,
        ))
    return findings


def audit_deck(scenes: list[Scene], client: LlmClient) -> list[Finding]:
    """Контекстные проверки по всей колоде без картинок, по текстам сцен."""
    if not scenes:
        return []
    skill = load_skill(_DECK_SKILL)
    schema = _answer_schema(_DECK_CHECKS, extra_props={"break_slide_id": {"type": "string"}},
                             extra_required=["break_slide_id"])
    system = skill.render()
    user = _deck_text(scenes)
    try:
        data = client.complete_json(system=system, user=user, schema=schema, params=skill.params)
    except _SERVER_FAILURES as exc:
        return [_unavailable_finding(scenes[0].slide_id, f"Контекстная проверка колоды не выполнена: {exc}")]
    return _findings_from_deck_answers(scenes, data)
