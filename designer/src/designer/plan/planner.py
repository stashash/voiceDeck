"""План презентации по брифу. Владелец: задача T-04."""
from __future__ import annotations

import re

from designer.contracts import ChartSpec, DeckPlan, SlideKind
from designer.llm.client import LlmClient
from designer.llm.skills import load_skill

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_SKILL_NAME = "plan-deck"


def make_plan(brief: str, purpose: str, audience: str, slide_count: int | None, client: LlmClient) -> DeckPlan:
    skill = load_skill(_SKILL_NAME)
    schema = DeckPlan.model_json_schema()
    system = skill.render(purpose=purpose, audience=audience, slide_count_hint=_slide_count_hint(slide_count))

    data = client.complete_json(system=system, user=brief, schema=schema, params=skill.params)
    plan = DeckPlan.model_validate(data)

    violations = _structural_violations(plan, slide_count)
    violations += _visualization_violations(plan, brief)
    violations += _content_violations(plan)
    if violations:
        retry_user = brief + "\n\nВ прошлом ответе нарушения: " + "; ".join(violations) + ". Исправь и ответь заново."
        data = client.complete_json(system=system, user=retry_user, schema=schema, params=skill.params)
        plan = DeckPlan.model_validate(data)

    # Числа, которых нет в брифе, убираются кодом безусловно: повтор не гарантирует,
    # что модель сама этого не нарушит второй раз.
    _drop_numbers_missing_from_brief(plan, brief)
    return plan


def _slide_count_hint(slide_count: int | None) -> str:
    if slide_count is None:
        return "от 10 до 15"
    return f"ровно {slide_count}"


def _structural_violations(plan: DeckPlan, slide_count: int | None) -> list[str]:
    violations: list[str] = []
    n = len(plan.slides)
    if slide_count is not None:
        if n != slide_count:
            violations.append(f"нужно ровно {slide_count} слайдов, получено {n}")
    elif not (10 <= n <= 15):
        violations.append(f"нужно от 10 до 15 слайдов, получено {n}")
    if plan.slides:
        if plan.slides[0].kind != SlideKind.title:
            violations.append("первый слайд должен быть title")
        if plan.slides[-1].kind not in (SlideKind.thanks, SlideKind.cta):
            violations.append("последний слайд должен быть thanks или cta")
    return violations


_VIZ_KINDS = (SlideKind.chart, SlideKind.table, SlideKind.big_number)
_LIST_KINDS = (
    SlideKind.agenda, SlideKind.bullets, SlideKind.cards, SlideKind.steps,
    SlideKind.timeline, SlideKind.compare, SlideKind.team,
)


def _content_violations(plan: DeckPlan) -> list[str]:
    """Слайд без содержания выходит пустым: модель склонна писать данные в notes, а items и chart оставлять пустыми."""
    violations: list[str] = []
    for slide in plan.slides:
        if slide.kind in _LIST_KINDS and len(slide.items) < 2:
            violations.append(f"слайд {slide.id} ({slide.kind.value}): в items меньше двух пунктов")
        elif slide.kind == SlideKind.big_number and not any(item.number for item in slide.items):
            violations.append(f"слайд {slide.id} (big_number): нет пункта с number")
        elif slide.kind == SlideKind.chart and slide.chart is None:
            violations.append(f"слайд {slide.id} (chart): поле chart пустое")
        elif slide.kind == SlideKind.table and slide.table is None:
            violations.append(f"слайд {slide.id} (table): поле table пустое")
    return violations


def _brief_has_comparable_numbers(brief: str) -> bool:
    """Пара сопоставимых чисел — два и больше разных числа в одном предложении брифа
    (было-стало, план-факт, ряд по периодам)."""
    for sentence in re.split(r"[.!?]", brief):
        if len(_numbers_in(sentence)) >= 2:
            return True
    return False


def _visualization_violations(plan: DeckPlan, brief: str) -> list[str]:
    if not _brief_has_comparable_numbers(brief):
        return []
    if any(slide.kind in _VIZ_KINDS for slide in plan.slides):
        return []
    return ["в брифе есть сопоставимые числа, а в плане нет слайда с диаграммой, таблицей или крупным числом"]


def _numbers_in(text: str) -> set[str]:
    return {match.replace(",", ".") for match in _NUMBER.findall(text)}


def _strip_unknown(text: str, allowed: set[str]) -> str:
    """Текст не режем. Вырезание цифр из фразы калечило её: «к 11:00» превращалось в «к 11:».
    Незнакомое число в тексте находит аудит (сверка чисел слайда с исходным текстом), а здесь
    убирается только то, что можно убрать целиком: номер пункта, диаграмма."""
    return text


def _chart_numbers_known(chart: ChartSpec, allowed: set[str]) -> bool:
    for series in chart.series:
        for value in series.values:
            text = str(int(value)) if value == int(value) else str(value)
            if text not in allowed:
                return False
    return True


def _drop_numbers_missing_from_brief(plan: DeckPlan, brief: str) -> None:
    allowed = _numbers_in(brief)
    for slide in plan.slides:
        slide.title = _strip_unknown(slide.title, allowed)
        slide.key_message = _strip_unknown(slide.key_message, allowed)
        for item in slide.items:
            item.heading = _strip_unknown(item.heading, allowed)
            item.body = _strip_unknown(item.body, allowed)
            if item.number is not None and _numbers_in(item.number) - allowed:
                item.number = None
        if slide.chart is not None and not _chart_numbers_known(slide.chart, allowed):
            slide.chart = None
        if slide.table is not None:
            slide.table.rows = [[_strip_unknown(cell, allowed) for cell in row] for row in slide.table.rows]
