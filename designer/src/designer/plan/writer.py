"""Заполнение текстовых слотов слайда под вместимость паттерна.

Два скилла:
- fill_slots — уже собранное намерение слайда сокращается и подгоняется под лимиты
  знаков и число пунктов конкретного паттерна;
- speech_to_slide — фрагмент устной речи (живой режим) превращается в намерение слайда.

Локальный сервер не проверяет maxLength из JSON-схемы (см. llm/client._matches_schema),
поэтому длины и число пунктов проверяются кодом после ответа: один повтор с перечнем
нарушений, остаточные нарушения по длине сокращаются кодом без запроса к модели.
"""
from __future__ import annotations

import re
import uuid

from designer.contracts import Item, SlideIntent, SlideKind
from designer.llm.client import LlmClient
from designer.llm.skills import load_skill

_FILL_SKILL = "fill-slots"
_SPEECH_SKILL = "speech-to-slide"

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_SENTENCE_END = re.compile(r"[.!?]")

# У SlideIntent нет отдельных полей subtitle/body: подзаголовок и одиночный текстовый
# блок — это одно и то же ключевое сообщение слайда.
_TOP_ROLE_FIELD = {"title": "title", "subtitle": "key_message", "body": "key_message"}
_UNIT_ROLES = {"heading", "body", "number"}

_TOP_LABELS = {"title": "заголовок", "subtitle": "подзаголовок", "body": "текст"}
_UNIT_LABELS = {"heading": "заголовок пункта", "body": "текст пункта", "number": "число пункта"}


def fill_slots(intent: SlideIntent, limits: dict[str, int], unit_limits: dict[str, int],
                n_units: int, client: LlmClient) -> SlideIntent:
    """Переписывает title/key_message/items намерения под лимиты знаков и ровно n_units пунктов."""
    _check_roles(limits, unit_limits)
    skill = load_skill(_FILL_SKILL)
    schema = _fill_schema(limits, unit_limits, n_units)
    system = skill.render(kind=intent.kind.value, limits_text=_limits_text(limits, unit_limits),
                           n_units=str(n_units))
    user = _intent_material(intent)
    allowed_numbers = _numbers_in_intent(intent)
    original_items = list(intent.items)

    data = client.complete_json(system=system, user=user, schema=schema, params=skill.params)
    draft = _apply_fill_response(intent, data, limits, unit_limits)
    violations = _violations(draft, limits, unit_limits, n_units, allowed_numbers)
    if violations:
        retry_user = user + "\n\nВ прошлом ответе нарушения: " + "; ".join(violations) + ". Исправь и ответь заново."
        data = client.complete_json(system=system, user=retry_user, schema=schema, params=skill.params)
        draft = _apply_fill_response(intent, data, limits, unit_limits)

    _fit_item_count(draft, original_items, n_units)
    _drop_unknown_numbers(draft, allowed_numbers)
    _enforce_top_limits(draft, limits)
    _enforce_unit_limits(draft.items, unit_limits)
    return draft


def speech_to_slide(chunk_text: str, kinds: list[SlideKind], client: LlmClient) -> SlideIntent:
    """Фрагмент устной речи в намерение слайда. Пустой title значит «слайд не нужен»."""
    skill = load_skill(_SPEECH_SKILL)
    schema = _speech_schema(kinds)
    system = skill.render(kinds=", ".join(kind.value for kind in kinds))

    data = client.complete_json(system=system, user=chunk_text, schema=schema, params=skill.params)
    intent = _speech_intent(data, kinds)
    if intent.title:
        _drop_unknown_numbers(intent, _numbers_in_text(chunk_text))
    return intent


# ---------- схема ответа ----------

def _check_roles(limits: dict[str, int], unit_limits: dict[str, int]) -> None:
    unknown = (set(limits) - set(_TOP_ROLE_FIELD)) | (set(unit_limits) - _UNIT_ROLES)
    if unknown:
        raise ValueError(f"fill_slots: неизвестные роли слотов {sorted(unknown)}")


def _fill_schema(limits: dict[str, int], unit_limits: dict[str, int], n_units: int) -> dict:
    properties = {role: {"type": "string", "maxLength": limit} for role, limit in limits.items()}
    required = list(limits.keys())
    if n_units > 0:
        item_properties = {role: {"type": "string", "maxLength": limit} for role, limit in unit_limits.items()}
        properties["items"] = {
            "type": "array",
            "minItems": n_units,
            "maxItems": n_units,
            "items": {"type": "object", "properties": item_properties, "required": list(unit_limits.keys())},
        }
        required.append("items")
    return {"type": "object", "properties": properties, "required": required}


def _speech_schema(kinds: list[SlideKind]) -> dict:
    return {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": [kind.value for kind in kinds]},
            "title": {"type": "string"},
            "key_message": {"type": "string"},
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"heading": {"type": "string"}, "body": {"type": "string"}},
                    "required": ["heading", "body"],
                },
            },
        },
        "required": ["kind", "title", "key_message", "items"],
    }


# ---------- запрос модели ----------

def _limits_text(limits: dict[str, int], unit_limits: dict[str, int]) -> str:
    parts = [f"{_TOP_LABELS.get(role, role)} — до {limit} знаков" for role, limit in limits.items()]
    parts += [f"{_UNIT_LABELS.get(role, role)} — до {limit} знаков" for role, limit in unit_limits.items()]
    return "; ".join(parts) if parts else "без ограничений"


def _intent_material(intent: SlideIntent) -> str:
    lines = [f"Заголовок: {intent.title}"]
    if intent.key_message:
        lines.append(f"Ключевое сообщение: {intent.key_message}")
    for i, item in enumerate(intent.items, start=1):
        piece = item.heading
        if item.body:
            piece = f"{piece} — {item.body}" if piece else item.body
        if item.number:
            piece = f"{item.number} {piece}".strip()
        lines.append(f"Пункт {i}: {piece}")
    return "\n".join(lines)


# ---------- разбор ответа ----------

def _apply_fill_response(intent: SlideIntent, data: dict, limits: dict[str, int],
                          unit_limits: dict[str, int]) -> SlideIntent:
    draft = intent.model_copy(deep=True)
    for role in limits:
        if role in data:
            setattr(draft, _TOP_ROLE_FIELD[role], str(data[role]))
    if "items" in data and isinstance(data["items"], list):
        items = []
        for raw in data["items"]:
            kwargs: dict[str, str | None] = {}
            if "heading" in unit_limits:
                kwargs["heading"] = str(raw.get("heading", ""))
            if "body" in unit_limits:
                kwargs["body"] = str(raw.get("body", ""))
            if "number" in unit_limits:
                kwargs["number"] = str(raw.get("number", "")) or None
            items.append(Item(**kwargs))
        draft.items = items
    return draft


def _speech_intent(data: dict, kinds: list[SlideKind]) -> SlideIntent:
    allowed = {kind.value for kind in kinds}
    kind = SlideKind(data["kind"]) if data.get("kind") in allowed else kinds[0]
    title = str(data.get("title", "")).strip()
    if not title:
        return SlideIntent(id=uuid.uuid4().hex, kind=kind, title="")
    items = [
        Item(heading=str(raw.get("heading", "")), body=str(raw.get("body", "")))
        for raw in data.get("items", []) or []
    ]
    return SlideIntent(id=uuid.uuid4().hex, kind=kind, title=title,
                        key_message=str(data.get("key_message", "")), items=items)


# ---------- проверка нарушений ----------

def _top_violations(draft: SlideIntent, limits: dict[str, int]) -> list[str]:
    violations = []
    for role, limit in limits.items():
        value = getattr(draft, _TOP_ROLE_FIELD[role])
        if len(value) > limit:
            violations.append(f"{role}: {len(value)} знаков, лимит {limit}")
    return violations


def _unit_violations(items: list[Item], unit_limits: dict[str, int]) -> list[str]:
    violations = []
    for i, item in enumerate(items, start=1):
        for role, limit in unit_limits.items():
            value = getattr(item, role) or ""
            if len(str(value)) > limit:
                violations.append(f"пункт {i} {role}: {len(str(value))} знаков, лимит {limit}")
    return violations


def _number_violations(draft: SlideIntent, allowed: set[str]) -> list[str]:
    texts = [("заголовок", draft.title), ("ключевое сообщение", draft.key_message)]
    for i, item in enumerate(draft.items, start=1):
        texts.append((f"пункт {i}", item.heading))
        texts.append((f"пункт {i}", item.body))
        if item.number:
            texts.append((f"пункт {i} число", item.number))
    return [f"{label}: числа не из намерения" for label, text in texts if _numbers_in_text(text) - allowed]


def _violations(draft: SlideIntent, limits: dict[str, int], unit_limits: dict[str, int],
                 n_units: int, allowed_numbers: set[str]) -> list[str]:
    violations = _top_violations(draft, limits)
    violations += _unit_violations(draft.items, unit_limits)
    if len(draft.items) != n_units:
        violations.append(f"нужно ровно {n_units} пунктов, получено {len(draft.items)}")
    violations += _number_violations(draft, allowed_numbers)
    return violations


# ---------- принудительная нормализация кодом ----------

def _fit_item_count(draft: SlideIntent, original_items: list[Item], n_units: int) -> None:
    items = draft.items
    if len(items) > n_units:
        del items[n_units:]
    elif len(items) < n_units:
        extra = original_items[len(items):]
        for i in range(n_units - len(items)):
            items.append(extra[i].model_copy() if i < len(extra) else Item())
    draft.items = items


def _numbers_in_text(text: str) -> set[str]:
    return {match.replace(",", ".") for match in _NUMBER.findall(text)}


def _numbers_in_intent(intent: SlideIntent) -> set[str]:
    numbers = _numbers_in_text(intent.title) | _numbers_in_text(intent.key_message) | _numbers_in_text(intent.attribution)
    for item in intent.items:
        numbers |= _numbers_in_text(item.heading) | _numbers_in_text(item.body)
        if item.number:
            numbers |= _numbers_in_text(item.number)
    if intent.chart is not None:
        for series in intent.chart.series:
            for value in series.values:
                numbers.add(str(int(value)) if value == int(value) else str(value))
    if intent.table is not None:
        for row in intent.table.rows:
            for cell in row:
                numbers |= _numbers_in_text(cell)
    return numbers


def _strip_unknown_numbers(text: str, allowed: set[str]) -> str:
    def _replace(match: re.Match[str]) -> str:
        return match.group(0) if match.group(0).replace(",", ".") in allowed else ""

    cleaned = _NUMBER.sub(_replace, text)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def _drop_unknown_numbers(draft: SlideIntent, allowed: set[str]) -> None:
    draft.title = _strip_unknown_numbers(draft.title, allowed)
    draft.key_message = _strip_unknown_numbers(draft.key_message, allowed)
    for item in draft.items:
        item.heading = _strip_unknown_numbers(item.heading, allowed)
        item.body = _strip_unknown_numbers(item.body, allowed)
        if item.number is not None and _numbers_in_text(item.number) - allowed:
            item.number = None


_TRAILING_PUNCT = {",", "-", "—", "–"}
_TRAILING_WORDS = {"и", "в", "на", "с"}


def _strip_trailing_junk(text: str) -> str:
    """Убирает с конца висящие союзы, предлоги и знаки: «и», «в», «на», «с», запятую, тире."""
    result = text
    while True:
        stripped = result.rstrip()
        if stripped != result:
            result = stripped
            continue
        if result and result[-1] in _TRAILING_PUNCT:
            result = result[:-1]
            continue
        words = result.split(" ")
        if len(words) > 1 and words[-1] in _TRAILING_WORDS:
            result = " ".join(words[:-1])
            continue
        break
    return result.rstrip()


def _word_boundary_cut(window: str) -> str:
    word_end = window.rfind(" ")
    return window[:word_end].rstrip() if word_end > 0 else window


def _truncate(text: str, limit: int) -> str:
    """Сокращает по границе предложения, иначе по границе слова, без обрыва посреди слова.

    С конца результата убираются висящие союзы, предлоги и знаки. Если после этого
    осталось меньше половины лимита, берётся сокращение по границе слова без чистки хвоста.
    """
    if len(text) <= limit:
        return text
    window = text[:limit]

    sentence_end = -1
    for match in _SENTENCE_END.finditer(window):
        sentence_end = match.end()
    cut = window[:sentence_end].rstrip() if sentence_end > 0 else _word_boundary_cut(window)

    cleaned = _strip_trailing_junk(cut)
    if len(cleaned) < limit / 2:
        return _word_boundary_cut(window)
    return cleaned


def _enforce_top_limits(draft: SlideIntent, limits: dict[str, int]) -> None:
    for role, limit in limits.items():
        field = _TOP_ROLE_FIELD[role]
        setattr(draft, field, _truncate(getattr(draft, field), limit))


def _enforce_unit_limits(items: list[Item], unit_limits: dict[str, int]) -> None:
    for item in items:
        if "heading" in unit_limits:
            item.heading = _truncate(item.heading, unit_limits["heading"])
        if "body" in unit_limits:
            item.body = _truncate(item.body, unit_limits["body"])
        if "number" in unit_limits and item.number is not None:
            item.number = _truncate(item.number, unit_limits["number"])
