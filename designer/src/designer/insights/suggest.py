"""Подсказки по таблице: Qwen выбирает кандидатов и формулирует вывод, код сверяет каждое число.

Подсказка, где модель написала число, которого нет у выбранных кандидатов, выбрасывается. Если
подсказок осталось меньше трёх или модель не ответила, список добирается кандидатами как есть,
с пометкой by_model=False: человек видит, что формулировка кода, а не модели.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Literal

import httpx
from pydantic import BaseModel, Field

from designer.contracts import ChartSpec, DeckPlan, Item, SlideIntent, SlideKind, TableSpec
from designer.insights.facts import Fact
from designer.insights.table import Table
from designer.llm.client import LlmClient, LlmResponseError, ModelLoading
from designer.llm.skills import load_skill

SKILL = "suggest-insights"
MIN_SUGGESTIONS, MAX_SUGGESTIONS = 3, 7
PREVIEW_ROWS = 30
Visual = Literal["column", "bar", "line", "pie", "table", "big_number"]
_FALLBACK_ORDER = ("change_last", "rows_grew", "share_top", "total_change", "leader_gap",
                   "change_total", "fastest_row", "growth_count")
_NUM = re.compile(r"\d{1,3}(?:[   ]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?")


class _Pick(BaseModel):
    fact_ids: list[str] = Field(min_length=1, max_length=2)
    headline: str = Field(max_length=120)
    number: str = Field(max_length=40)
    visual: Visual
    why: str = Field(max_length=200)


class _Answer(BaseModel):
    suggestions: list[_Pick] = Field(min_length=1, max_length=MAX_SUGGESTIONS)


class Suggestion(BaseModel):
    id: str
    headline: str
    number: str
    visual: Visual
    why: str
    fact_ids: list[str]
    source: str
    formula: str
    chart: ChartSpec | None = None
    table: TableSpec | None = None
    data_lines: list[str] = Field(default_factory=list)
    by_model: bool


def numbers_in(text: str) -> set[str]:
    """Числа текста без знака и разделителей групп: «+18,0 %» и «18» дают одно и то же «18»."""
    found = set()
    for match in _NUM.findall(text):
        try:
            value = Decimal(re.sub(r"[   ]", "", match).replace(",", "."))
        except InvalidOperation:
            continue
        found.add(format(value.normalize(), "f"))
    return found


def suggest(table: Table, facts: list[Fact], brief: str, audience: str,
            client: LlmClient | None) -> tuple[list[Suggestion], str]:
    """Подсказки и пустая строка, либо подсказки кода и причина, почему модель не помогла."""
    by_id = {fact.id: fact for fact in facts}
    picked: list[Suggestion] = []
    note = ""
    if client is not None and facts:
        skill = load_skill(SKILL)
        system = skill.render(brief=brief.strip() or "не задан", audience=audience.strip() or "не задана")
        try:
            data = client.complete_json(system=system, user=_material(table, facts),
                                        schema=_Answer.model_json_schema(), params=skill.params)
            picked = _checked(_Answer.model_validate(data), by_id)
        except (LlmResponseError, ModelLoading, ValueError, httpx.HTTPError) as exc:
            note = f"Модель не ответила: {_reason(exc)}. Выводы сформулировал код"
    used = {fact_id for suggestion in picked for fact_id in suggestion.fact_ids}
    for kind in _FALLBACK_ORDER:
        if len(picked) >= MIN_SUGGESTIONS:
            break
        for fact in facts:
            if fact.kind == kind and fact.id not in used:
                picked.append(_from_fact(fact))
                used.add(fact.id)
                break
    for index, suggestion in enumerate(picked[:MAX_SUGGESTIONS], start=1):
        suggestion.id = f"s{index}"
    return picked[:MAX_SUGGESTIONS], note


def _reason(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (401, 403):
        return "сервер модели не принял ключ или Project-ID"
    if isinstance(exc, (httpx.HTTPError, ModelLoading)):
        return "нет связи с сервером модели"
    return "ответ не по схеме"


def _material(table: Table, facts: list[Fact]) -> str:
    lines = [f"Таблица «{table.name}», строк данных: {len(table.rows)}", " | ".join(table.headers)]
    lines += [" | ".join(row) for row in table.rows[:PREVIEW_ROWS]]
    if len(table.rows) > PREVIEW_ROWS:
        lines.append(f"… ещё {len(table.rows) - PREVIEW_ROWS} строк")
    lines.append("")
    lines.append("Кандидаты в выводы:")
    lines += [f"{fact.id}: {fact.statement}" for fact in facts]
    return "\n".join(lines)


def _checked(answer: _Answer, by_id: dict[str, Fact]) -> list[Suggestion]:
    result: list[Suggestion] = []
    seen: set[frozenset[str]] = set()
    for pick in answer.suggestions:
        facts = [by_id[fact_id] for fact_id in pick.fact_ids if fact_id in by_id]
        key = frozenset(fact.id for fact in facts)
        if not facts or len(facts) != len(pick.fact_ids) or key in seen:
            continue
        allowed: set[str] = set()
        for fact in facts:
            allowed |= numbers_in(fact.statement) | numbers_in(" ".join(fact.numbers))
        if numbers_in(pick.headline + " " + pick.number) - allowed:
            continue
        if not pick.headline.strip() or not pick.number.strip():
            continue
        seen.add(key)
        main = facts[0]
        result.append(Suggestion(
            id="", headline=pick.headline.strip(), number=pick.number.strip(), visual=_visual(pick.visual, main),
            why=pick.why.strip(), fact_ids=[fact.id for fact in facts], source="; ".join(f.source for f in facts),
            formula="; ".join(f.formula for f in facts), chart=main.chart, table=main.table,
            data_lines=[line for fact in facts for line in fact.data_lines], by_model=True))
    return result


def _visual(wanted: str, fact: Fact) -> str:
    """Вид показа, который у кандидата есть данными: таблица без таблицы становится диаграммой."""
    if wanted == "pie" and fact.kind != "share_top":
        wanted = fact.chart.type if fact.chart else "big_number"
    if wanted == "table" and fact.table is None:
        wanted = fact.chart.type if fact.chart else "big_number"
    if wanted in ("column", "bar", "line", "pie") and fact.chart is None:
        wanted = "big_number"
    if wanted == "big_number" and not fact.big_number:
        wanted = fact.chart.type if fact.chart else "table"
    return wanted


def _from_fact(fact: Fact) -> Suggestion:
    visual = fact.chart.type if fact.chart else ("table" if fact.table else "big_number")
    return Suggestion(id="", headline=fact.statement, number=fact.big_number or (fact.numbers[0] if fact.numbers else ""),
                      visual=visual, why="", fact_ids=[fact.id], source=fact.source, formula=fact.formula,
                      chart=fact.chart, table=fact.table, data_lines=fact.data_lines, by_model=False)


def insight_slide(suggestion: Suggestion) -> SlideIntent:
    """Слайд подсказки: вывод в заголовке, данные таблицы как есть, источник в заметках докладчика."""
    notes = f"Источник: {suggestion.source}. Расчёт: {suggestion.formula}."
    if suggestion.visual == "big_number" or (suggestion.chart is None and suggestion.table is None):
        return SlideIntent(id="", kind=SlideKind.big_number, title=suggestion.headline, key_message=suggestion.why,
                           items=[Item(heading=suggestion.headline, number=suggestion.number)], notes=notes)
    if suggestion.visual == "table" and suggestion.table is not None:
        return SlideIntent(id="", kind=SlideKind.table, title=suggestion.headline, key_message=suggestion.why,
                           table=suggestion.table, notes=notes)
    chart = suggestion.chart.model_copy(update={"type": suggestion.visual}) if suggestion.chart else None
    return SlideIntent(id="", kind=SlideKind.chart, title=suggestion.headline, key_message=suggestion.why,
                       chart=chart, notes=notes)


def brief_with_insights(brief: str, table_name: str, suggestions: list[Suggestion], with_data: bool) -> str:
    """Бриф с выводами из таблицы.

    План получает только выводы: с данными таблицы он строил бы свои диаграммы поверх готовых слайдов.
    Аудит получает и данные: числа на диаграммах выводов должно быть с чем сверить.
    """
    lines = [brief.strip(), "", f"Выводы из таблицы «{table_name}». Слайды с этими выводами и диаграммами "
             "уже собраны, отдельных слайдов про них не делай; построй вокруг них рассказ:"]
    for suggestion in suggestions:
        lines.append(f"- {suggestion.headline} ({suggestion.number})")
    if with_data:
        lines += ["", "Данные таблицы для этих выводов:"] + sorted({line for s in suggestions for line in s.data_lines})
    return "\n".join(lines)


def insert_insight_slides(plan: DeckPlan, suggestions: list[Suggestion]) -> None:
    """Слайды выводов встают после титула и оглавления, в том порядке, в каком автор их отметил."""
    position = 1 if plan.slides else 0
    if len(plan.slides) > 1 and plan.slides[1].kind == SlideKind.agenda:
        position = 2
    plan.slides[position:position] = [insight_slide(suggestion) for suggestion in suggestions]
    for index, slide in enumerate(plan.slides, start=1):
        slide.id = f"s{index}"
