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


def _numbers_in(text: str) -> set[str]:
    return {match.replace(",", ".") for match in _NUMBER.findall(text)}


def _strip_unknown(text: str, allowed: set[str]) -> str:
    def _replace(match: re.Match[str]) -> str:
        return match.group(0) if match.group(0).replace(",", ".") in allowed else ""

    cleaned = _NUMBER.sub(_replace, text)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


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
