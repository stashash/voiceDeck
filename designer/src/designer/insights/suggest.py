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
_PERIOD_KINDS = ("change_last", "change_total", "growth_count")
_FALLBACK_ORDER = ("change_last", "rows_grew", "share_top", "total_change", "leader_gap",
                   "change_total", "fastest_row", "growth_count")
_NUM = re.compile(r"(?<![\d.,])\d{1,3}(?:[ \u00a0\u202f]\d{3}(?!\d))+(?:[.,]\d+)?|\d+(?:[.,]\d+)?")


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
    statement: str = ""
    """Формулировка кода главного кандидата: на слайде под заголовком, без толкований модели."""
    topic: str = ""
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
            note = f"{_reason(exc)} Выводы посчитал и сформулировал код."
    picked += _fallback(facts, picked)
    for index, suggestion in enumerate(picked[:MAX_SUGGESTIONS], start=1):
        suggestion.id = f"s{index}"
    return picked[:MAX_SUGGESTIONS], note


def _fallback(facts: list[Fact], picked: list[Suggestion]) -> list[Suggestion]:
    """Добор до трёх подсказок кандидатами кода: сначала по разным темам таблицы, потом любые.

    Без этого все три подсказки запасного пути были про первую метрику («Выручка»), а остальные
    столбцы таблицы человек не видел (ред-тим 17.10, первый пользователь).
    """
    used = {fact_id for suggestion in picked for fact_id in suggestion.fact_ids}
    topics = {fact.topic for fact in facts if fact.id in used}
    extra: list[Suggestion] = []
    order = {kind: index for index, kind in enumerate(_FALLBACK_ORDER)}
    ranked = sorted((f for f in facts if f.kind in order), key=lambda f: order[f.kind])
    for fresh_topic_only in (True, False):
        for fact in ranked:
            if len(picked) + len(extra) >= MIN_SUGGESTIONS:
                return extra
            if fact.id in used or (fresh_topic_only and fact.topic in topics):
                continue
            extra.append(_from_fact(fact))
            used.add(fact.id)
            topics.add(fact.topic)
    return extra


def _reason(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (401, 403, 404):
        return "Модель недоступна: сервер модели не принял ключ."
    if isinstance(exc, (httpx.HTTPError, ModelLoading)):
        return "Модель недоступна: нет связи с сервером модели."
    return "Модель ответила не по формату."


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
        main = facts[0]
        headline = _exact_period(pick.headline.strip(), main)
        if not (_names_topic(headline, main) and _names_period(headline, main)
                and _same_direction(headline + " " + pick.number, main)):
            continue
        seen.add(key)
        # «Зачем показывать» идёт в тултип и заметки: число в нём проходит ту же сверку, иначе поле пустое.
        why = pick.why.strip() if not numbers_in(pick.why) - allowed else ""
        # Справа в строке и крупно на слайде стоит главное число расчёта (изменение со знаком), а не уровень:
        # у вывода «отток снизился на 1,3 п. п.» модель ставила «5,1 %» (ред-тим 17.10).
        number = pick.number.strip()
        if main.big_number and not numbers_in(number) & numbers_in(main.big_number):
            number = main.big_number
        result.append(Suggestion(
            id="", headline=headline, number=number, visual=_visual(pick.visual, main),
            why=why, fact_ids=[fact.id for fact in facts], statement=main.statement, topic=main.topic,
            source="; ".join(f.source for f in facts),
            formula="; ".join(f.formula for f in facts), chart=main.chart, table=main.table,
            data_lines=[line for fact in facts for line in fact.data_lines], by_model=True))
    return result


_STEM = 4
_UP = re.compile(r"\b(вырос|выросл|рост|увелич|прибав|подня|ускор|больше)", re.I)
_DOWN = re.compile(r"\b(снизи|сниже|сократ|упал|упа|уменьш|паден|спад|меньше|потер)", re.I)
_YEARLY = re.compile(r"\b(за|в)\s+(19|20)\d{2}\s*(год\w*|г\.)|\bза\s+год\b|\bгодов\w*", re.I)


def _stems(text: str) -> set[str]:
    return {word.lower()[:_STEM] for word in re.findall(r"[а-яёa-z]{4,}", text, re.I)}


def _names_topic(headline: str, fact: Fact) -> bool:
    """Вывод называет показатель кандидата: «Новых клиентов…» для столбца «Новые клиенты» проходит."""
    topic = _stems(fact.topic)
    return not topic or bool(topic & _stems(headline))


def _period_marks(label: str) -> set[str]:
    """Отличительные слова подписи периода: «IV кв 2026» -> {«iv»}, «Октябрь 2026» -> {«октя»}."""
    marks = {word.lower() for word in re.findall(r"\b(?:I{1,3}V?|IV|Q[1-4]|H[12]|[1-4])\b", label)}
    marks |= {word.lower()[:_STEM] for word in re.findall(r"[а-яё]{3,}", label, re.I)} - {"квар", "кв", "полу"}
    return marks


def _names_period(headline: str, fact: Fact) -> bool:
    """Сравнение кварталов не называется годовым: вывод упоминает последний период кандидата.

    Ред-тим 17.10: «Выручка выросла на 47,5 % за 2026 год» при сравнении I и IV кварталов совет
    директоров прочтёт как годовой рост. Подписи из одних годов («2025 → 2026») годовые сами.
    """
    if not fact.periods:
        return True
    last = _period_marks(fact.periods[-1])
    if not last:
        return True
    words = {w.lower() for w in re.findall(r"\b(?:I{1,3}V?|IV|Q[1-4]|H[12]|[1-4])\b", headline)}
    words |= {w.lower()[:_STEM] for w in re.findall(r"[а-яё]{3,}", headline, re.I)}
    return bool(last & words) and not _YEARLY.search(headline)


def _exact_period(headline: str, fact: Fact) -> str:
    """«…за 2026 год» у сравнения кварталов меняется на точный период кандидата, остальная фраза модели остаётся.

    Прогон 17.10 на Qwen3.8-27B: модель писала «за 2026 год» у сравнения I и IV кварталов и после правила
    в скилле. Отказ отбрасывал хорошую формулировку, правка оборота сохраняет её и делает точной.
    """
    if not fact.periods or _names_period(headline, fact) or not _YEARLY.search(headline):
        return headline
    first, last = fact.periods[0], fact.periods[-1]
    exact = f"с {first} по {last}" if fact.kind == "change_total" else f"{first} → {last}"
    return _YEARLY.sub(exact, headline, count=1)


def _same_direction(text: str, fact: Fact) -> bool:
    """Знак изменения в выводе совпадает с расчётом: «снизилась на 18 %» при «+18 %» не проходит."""
    if not fact.numbers or fact.numbers[0][:1] not in "+−":
        return True
    up = fact.numbers[0].startswith("+")
    if up and (_DOWN.search(text) or "−" in text or re.search(r"(?<!\d)-\s?\d", text)):
        return False
    return not (not up and (_UP.search(text) or "+" in text))


def _visual(wanted: str, fact: Fact) -> str:
    """Вид показа, который у кандидата есть данными: таблица без таблицы становится диаграммой."""
    if wanted == "bar" and fact.kind in _PERIOD_KINDS:
        wanted = "column"  # периоды идут слева направо, горизонтальные полосы ставят их снизу вверх
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
                      visual=visual, why="", fact_ids=[fact.id], statement=fact.statement, topic=fact.topic,
                      source=fact.source, formula=fact.formula,
                      chart=fact.chart, table=fact.table, data_lines=fact.data_lines, by_model=False)


INSIGHT_NOTES = "Источник:"
"""Начало заметок слайда вывода из таблицы: по нему конвейер узнаёт такой слайд после плана."""


def is_insight_slide(intent: SlideIntent) -> bool:
    return intent.notes.startswith(INSIGHT_NOTES)


def insight_slide(suggestion: Suggestion) -> SlideIntent:
    """Слайд подсказки: вывод в заголовке, под ним формулировка кода, данные таблицы как есть.

    Толкование модели (why) идёт только в заметки докладчика: причин изменения в таблице нет,
    и подгонка текста под макет не должна вписать его в заголовок как факт.
    """
    notes = f"{INSIGHT_NOTES} {suggestion.source}. Расчёт: {suggestion.formula}."
    if suggestion.why:
        notes += f" Зачем показывать: {suggestion.why}"
    statement = suggestion.statement or suggestion.headline
    if suggestion.visual == "big_number" or (suggestion.chart is None and suggestion.table is None):
        return SlideIntent(id="", kind=SlideKind.big_number, title=suggestion.headline,
                           items=[Item(heading=statement, number=suggestion.number)], notes=notes)
    if suggestion.visual == "table" and suggestion.table is not None:
        return SlideIntent(id="", kind=SlideKind.table, title=suggestion.headline, key_message=statement,
                           table=suggestion.table, notes=notes)
    chart = suggestion.chart.model_copy(update={"type": suggestion.visual}) if suggestion.chart else None
    return SlideIntent(id="", kind=SlideKind.chart, title=suggestion.headline, key_message=statement,
                       chart=chart, notes=notes)


def brief_with_insights(brief: str, table_name: str, suggestions: list[Suggestion], with_data: bool) -> str:
    """Бриф с выводами из таблицы.

    План получает только темы готовых слайдов, без чисел: увидев числа, он строит по ним свои
    диаграммы и сам подписывает столбцы. Аудит получает выводы и данные таблицы: числа на
    диаграммах выводов должно быть с чем сверить.
    """
    if not with_data:
        topics = list(dict.fromkeys(s.topic or s.headline for s in suggestions))
        return "\n".join([brief.strip(), "", f"Слайды с выводами из таблицы «{table_name}» уже готовы, по одному "
                          f"на тему: {'; '.join(topics)}. Слайдов про эти темы и их цифры не делай. Сделай остальные "
                          "слайды рассказа вокруг них: зачем собрались, что эти итоги значат для решения аудитории, "
                          "какие решения нужны и следующие шаги. Фактов, причин и рисков, которых нет в брифе, "
                          "не добавляй."])
    lines = [brief.strip(), "", f"Выводы из таблицы «{table_name}»:"]
    lines += [f"- {s.headline} ({s.number})" for s in suggestions]
    lines += ["", "Данные таблицы для этих выводов:"] + sorted({line for s in suggestions for line in s.data_lines})
    return "\n".join(lines)


_KEEP_KINDS = (SlideKind.title, SlideKind.agenda, SlideKind.thanks, SlideKind.cta)
_DATA_KINDS = (SlideKind.chart, SlideKind.big_number, SlideKind.table)
_YEAR = re.compile(r"^(19|20)\d{2}$")
_WORD = re.compile(r"[а-яёa-z]{4,}", re.I)


def _insight_numbers(suggestion: Suggestion) -> set[str]:
    found = numbers_in(suggestion.headline + " " + suggestion.number)
    if suggestion.chart:
        found |= {format(Decimal(repr(v)).normalize(), "f") for s in suggestion.chart.series for v in s.values}
    return {n for n in found if not _YEAR.match(n)}


def _slide_numbers(slide: SlideIntent) -> set[str]:
    text = " ".join([slide.title, slide.key_message] + [f"{i.heading} {i.body} {i.number or ''}" for i in slide.items])
    found = numbers_in(text)
    if slide.chart:
        found |= {format(Decimal(repr(v)).normalize(), "f") for s in slide.chart.series for v in s.values}
    return {n for n in found if not _YEAR.match(n)}


def _words(text: str) -> set[str]:
    return {w.lower()[:6] for w in _WORD.findall(text)}


def drop_repeats(plan: DeckPlan, suggestions: list[Suggestion]) -> None:
    """Убирает слайды плана, которые повторяют выводы из таблицы.

    План просят не повторять готовые выводы, но модель всё равно делает свои слайды с теми же
    числами и сама подписывает столбцы. Повтор: слайд с данными, где есть число вывода, или
    слайд, у которого заголовок больше чем наполовину из тех же слов, что и вывод.
    """
    numbers = set().union(*(_insight_numbers(s) for s in suggestions)) if suggestions else set()
    heads = [_words(s.headline) for s in suggestions]

    def repeats(slide: SlideIntent) -> bool:
        if slide.kind in _KEEP_KINDS:
            return False
        if slide.kind in _DATA_KINDS and _slide_numbers(slide) & numbers:
            return True
        words = _words(slide.title)
        return any(words and head and len(words & head) / len(words | head) >= 0.5 for head in heads)

    plan.slides = [slide for slide in plan.slides if not repeats(slide)]


def insert_insight_slides(plan: DeckPlan, suggestions: list[Suggestion]) -> None:
    """Слайды выводов встают после титула и оглавления, в том порядке, в каком автор их отметил."""
    drop_repeats(plan, suggestions)
    position = 1 if plan.slides else 0
    if len(plan.slides) > 1 and plan.slides[1].kind == SlideKind.agenda:
        position = 2
    plan.slides[position:position] = [insight_slide(suggestion) for suggestion in suggestions]
    for index, slide in enumerate(plan.slides, start=1):
        slide.id = f"s{index}"
