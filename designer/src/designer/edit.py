"""Правка варианта колоды: текст на слайде, образец, лента слайдов, просьба агенту, история.

Каждая правка снимает прежний deck.json варианта в history/<n>.json (store.snapshot_deck_history),
пересобирает затронутые слайды, гоняет детерминированный аудит по всем сценам и переиздаёт
файлы варианта (pptx, html, pdf, картинки слайдов) — так же, как это делает
pipeline._build_and_export_variant после генерации. Контекстный (по картинке) аудит здесь
не пересчитывается: он дорогой, его запускает POST /decks/{id}/{v}/audit-contextual по запросу,
как и раньше; уже найденные контекстные замечания, кроме починенного, переносятся как есть.

Клиент модели для «попросить агента» и «переписать замечание» берётся через
agent_hook._client_for("deck") — тот же приём, что и в pipeline.py.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from designer import store
from designer.agent_hook import _client_for
from designer.audit.deterministic import run_checks
from designer.contracts import (
    Deck,
    DeckPlan,
    DesignSystem,
    Element,
    Finding,
    Item,
    Pattern,
    Scene,
    SlideIntent,
    SlideKind,
    SlideSpec,
)
from designer.export import convert, render
from designer.export.html import render_deck
from designer.export.html_image import render_deck_images
from designer.export.pptx_deck import export_pptx
from designer.layout.capacity import main_group, unit_count
from designer.layout.compose import compose
from designer.layout.match import choose_pattern, fits, score_pattern
from designer.layout.scene import build_scene
from designer.parse.package import load_package
from designer.plan.writer import fill_slots

_MAX_PATTERN_OPTIONS = 6
_UNIT_ID_RE = re.compile(r"^u(\d+)s(\d+)$")
_SLIDE_ACTIONS = ("add", "copy", "delete", "move")


class DeckNotFound(ValueError):
    """Колода или вариант не найдены."""


class SlideNotFound(ValueError):
    """Номер слайда (или позиция to) вне диапазона плана варианта."""


class ElementNotFound(ValueError):
    """id элемента нет на сцене слайда."""


class PatternNotFound(ValueError):
    """Образец с этим id не найден в дизайн-системе."""


class FindingNotFound(ValueError):
    """Замечание с этим id не найдено среди findings варианта."""


class NoHistory(ValueError):
    """Истории правок нет: откатывать нечего."""


# ---------- состояние варианта ----------

class _State:
    """Разобранное deck.json варианта; raw — исходный словарь для снимка истории."""

    def __init__(self, deck_id: str, variant: str, raw: dict, ds_id: str, package_dir: Path, ds: DesignSystem):
        self.deck_id = deck_id
        self.variant = variant
        self.raw = raw
        self.ds_id = ds_id
        self.package_dir = package_dir
        self.ds = ds
        self.plan = DeckPlan.model_validate(raw["plan"])
        self.specs: list[SlideSpec] = [SlideSpec.model_validate(item) for item in raw["specs"]]
        self.scenes: list[Scene] = [Scene.model_validate(item) for item in raw["scenes"]]
        self.findings: list[Finding] = [Finding.model_validate(item) for item in raw["findings"]]


def _load(deck_id: str, variant: str) -> _State:
    raw = store.load_deck_state(deck_id, variant)
    if raw is None:
        raise DeckNotFound(f"колода не найдена: {deck_id}/{variant}")
    ds_id = raw["design_system_id"]
    package_dir = store.design_system_dir(ds_id)
    ds = load_package(package_dir)
    return _State(deck_id, variant, raw, ds_id, package_dir, ds)


def _slide_index(state: _State, slide_number: int) -> int:
    index = slide_number - 1
    if index < 0 or index >= len(state.plan.slides):
        raise SlideNotFound(f"слайда {slide_number} нет: в варианте {len(state.plan.slides)} слайдов")
    return index


def _snapshot(state: _State) -> None:
    store.snapshot_deck_history(state.deck_id, state.variant, state.raw)


def _checks(state: _State, touched: set[str] | None = None, drop_ids: set[str] | None = None) -> list[Finding]:
    """Проверка по правилам заново плюс прежние замечания модели по слайдам, которых правка не касалась.

    Замечание модели считалось по картинке слайда: у изменённого слайда оно устарело, у остальных нет.
    """
    present = {spec.slide_id for spec in state.specs}
    touched = touched or set()
    drop_ids = drop_ids or set()
    kept = [f for f in state.findings if f.kind == "contextual" and f.slide_id in present
            and f.slide_id not in touched and f.id not in drop_ids]
    return run_checks(state.scenes, state.ds) + kept


def _persist(state: _State, findings: list[Finding]) -> None:
    """Переиздаёт файлы варианта (pptx, html, pdf, картинки) и пишет deck.json."""
    deck = Deck(id=state.deck_id, design_system_id=state.ds_id, variant=state.variant,
                plan=state.plan, specs=state.specs, scenes=state.scenes)

    files_dir = store.deck_variant_files_dir(state.deck_id, state.variant)
    pptx_path = files_dir / "deck.pptx"
    export_pptx(state.specs, state.ds, state.package_dir, pptx_path)
    markup_html = render_deck(deck, state.ds, state.package_dir)
    (files_dir / "deck.markup.html").write_text(markup_html, encoding="utf-8")
    (files_dir / "deck.html").write_text(markup_html, encoding="utf-8")

    if convert.available():
        try:
            convert.to_pdf(pptx_path, files_dir / "deck.pdf")
        except convert.ConverterUnavailable:
            pass
        try:
            pngs = render.render_slides(pptx_path, len(state.specs)) if state.specs else []
        except convert.ConverterUnavailable:
            pngs = []
        if pngs:
            slides_dir = store.deck_variant_slides_dir(state.deck_id, state.variant)
            for old in slides_dir.glob("slide-*.png"):
                old.unlink()
            for index, png in enumerate(pngs, start=1):
                (slides_dir / f"slide-{index:03d}.png").write_bytes(png)
            html_text = render_deck_images(deck, state.ds, pngs)
            (files_dir / "deck.html").write_text(html_text, encoding="utf-8")

    store.save_deck_result(state.deck_id, deck, findings, variant=state.variant)


def _recompose(state: _State, index: int, intent: SlideIntent, pattern: Pattern) -> None:
    spec = compose(intent, pattern, state.ds)
    scene = build_scene(spec, pattern, state.ds, state.package_dir)
    state.plan.slides[index] = intent
    state.specs[index] = spec
    state.scenes[index] = scene


# ---------- текст элемента на слайде ----------

def _slot_ref(el: Element, pattern: Pattern | None):
    """Слот паттерна для элемента сцены: верхнего уровня либо слот повторяющегося блока.

    Дублирует небольшую часть audit.fixes._slot_ref: тот модуль потоку 1 не принадлежит,
    трогать его нельзя, а связь «элемент сцены -> ключ SlideSpec» нужна и здесь.
    """
    if pattern is None:
        return None, None, None
    for slot in pattern.slots:
        if slot.id == el.id:
            return slot, None, None
    match = _UNIT_ID_RE.match(el.id)
    if not match or el.source_shape_id is None:
        return None, None, None
    index = int(match.group(1))
    for group in pattern.groups:
        for slot in group.unit_slots:
            if slot.shape_id == el.source_shape_id:
                return slot, group, index
    return None, None, None


def _set_slot_text(spec: SlideSpec, slot, group, index: int | None, text: str) -> None:
    if group is None:
        spec.slot_text[slot.id] = text
        return
    target = spec.linked_unit_text[group.id] if group.id in spec.linked_unit_text else spec.unit_text
    if index is not None and 0 <= index < len(target):
        target[index][slot.id] = text


def set_slide_text(deck_id: str, variant: str, slide_number: int, element_id: str, text: str) -> None:
    state = _load(deck_id, variant)
    index = _slide_index(state, slide_number)
    scene = state.scenes[index]
    el = next((e for e in scene.elements if e.id == element_id), None)
    if el is None:
        raise ElementNotFound(f"элемент {element_id} не найден на слайде {slide_number}")

    _snapshot(state)
    el.text = text
    pattern = next((p for p in state.ds.patterns if p.id == scene.pattern_id), None)
    slot, group, unit_index = _slot_ref(el, pattern)
    if slot is not None:
        _set_slot_text(state.specs[index], slot, group, unit_index, text)

    findings = _checks(state, {state.specs[index].slide_id})
    _persist(state, findings)


# ---------- образец слайда ----------

def set_slide_pattern(deck_id: str, variant: str, slide_number: int, pattern_id: str) -> None:
    state = _load(deck_id, variant)
    index = _slide_index(state, slide_number)
    pattern = next((p for p in state.ds.patterns if p.id == pattern_id), None)
    if pattern is None:
        raise PatternNotFound(f"образец {pattern_id} не найден в дизайн-системе")

    _snapshot(state)
    _recompose(state, index, state.plan.slides[index], pattern)

    findings = _checks(state, {state.specs[index].slide_id})
    _persist(state, findings)


def list_slide_patterns(deck_id: str, variant: str, slide_number: int) -> list[dict]:
    """До шести образцов, которые годятся под намерение слайда; текущий — первым."""
    state = _load(deck_id, variant)
    index = _slide_index(state, slide_number)
    intent = state.plan.slides[index]
    current_id = state.specs[index].pattern_id
    used = [spec.pattern_id for i, spec in enumerate(state.specs) if i != index]

    candidates = [p for p in state.ds.patterns if p.id == current_id or fits(intent, p, state.ds)]
    ranked = sorted(candidates, key=lambda p: (p.id != current_id, -score_pattern(intent, p, used, state.ds), p.id))
    chosen = ranked[:_MAX_PATTERN_OPTIONS]

    return [{
        "pattern_id": p.id,
        "kind": p.kind.value,
        "preview": f"/design-systems/{state.ds_id}/previews/{p.id}.png" if p.preview else None,
        "current": p.id == current_id,
    } for p in chosen]


# ---------- агент переписывает содержание слайда ----------

def _draft_schema() -> dict:
    item_schema = {
        "type": "object",
        "properties": {
            "heading": {"type": "string", "maxLength": 200},
            "body": {"type": "string", "maxLength": 400},
            "number": {"type": "string", "maxLength": 20},
        },
        "required": ["heading", "body"],
    }
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string", "maxLength": 200},
            "key_message": {"type": "string", "maxLength": 400},
            "items": {"type": "array", "items": item_schema},
            "notes": {"type": "string", "maxLength": 600},
        },
        "required": ["title", "key_message", "items", "notes"],
    }


def _draft_system(instruction: str) -> str:
    return (
        "Ты редактируешь слайд презентации по просьбе автора.\n"
        "Перепиши заголовок, ключевое сообщение, пункты и заметки докладчика по просьбе ниже; "
        "то, чего просьба не касается, оставь как есть по смыслу. Числа и факты бери только "
        "из текущего содержания слайда, не выдумывай новые. Ответ на языке текущего содержания.\n\n"
        f"Просьба автора: {instruction}\n\n"
        "Ответ — только JSON по схеме, без пояснений и без рассуждений вслух."
    )


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
    if intent.notes:
        lines.append(f"Заметки докладчика: {intent.notes}")
    return "\n".join(lines)


def _draft_intent(intent: SlideIntent, data: dict) -> SlideIntent:
    items = [
        Item(heading=str(raw.get("heading", "")), body=str(raw.get("body", "")),
             number=(str(raw["number"]) if raw.get("number") else None))
        for raw in data.get("items", []) or []
    ]
    return intent.model_copy(update={
        "title": str(data.get("title", intent.title)),
        "key_message": str(data.get("key_message", intent.key_message)),
        "items": items,
        "notes": str(data.get("notes", intent.notes)),
    })


def _fit_to_pattern(intent: SlideIntent, pattern: Pattern, ds: DesignSystem, client) -> SlideIntent:
    from designer import pipeline  # локальный импорт: те же лимиты слотов, что при генерации

    group = main_group(pattern)
    n_units = unit_count(group, len(intent.items)) if group is not None else 0
    limits, unit_limits = pipeline._role_limits(pattern, intent, n_units, ds.tokens.type_scale)
    if not limits and not unit_limits:
        return intent
    return fill_slots(intent, limits, unit_limits, n_units, client)


def _rewrite_intent(intent: SlideIntent, pattern: Pattern, instruction: str, ds: DesignSystem) -> SlideIntent:
    client = _client_for("deck")
    try:
        data = client.complete_json(system=_draft_system(instruction), user=_intent_material(intent),
                                     schema=_draft_schema())
        draft = _draft_intent(intent, data)
        return _fit_to_pattern(draft, pattern, ds, client)
    finally:
        client.close()


def ask_agent_rewrite(deck_id: str, variant: str, slide_number: int, instruction: str) -> None:
    state = _load(deck_id, variant)
    index = _slide_index(state, slide_number)
    intent = state.plan.slides[index]
    pattern = next((p for p in state.ds.patterns if p.id == state.specs[index].pattern_id), None)
    if pattern is None:
        pattern = choose_pattern(intent, state.ds, [s.pattern_id for s in state.specs])

    new_intent = _rewrite_intent(intent, pattern, instruction, state.ds)
    _snapshot(state)
    _recompose(state, index, new_intent, pattern)

    findings = _checks(state, {state.specs[index].slide_id})
    _persist(state, findings)


def rewrite_from_finding(deck_id: str, variant: str, finding_id: str) -> None:
    """Замечание модели: слайд переписывается с текстом замечания как просьбой автора."""
    state = _load(deck_id, variant)
    finding = next((f for f in state.findings if f.id == finding_id), None)
    if finding is None:
        raise FindingNotFound(f"замечание {finding_id} не найдено")
    index = next((i for i, spec in enumerate(state.specs) if spec.slide_id == finding.slide_id), None)
    if index is None:
        raise SlideNotFound(f"слайд замечания {finding_id} не найден")

    intent = state.plan.slides[index]
    pattern = next((p for p in state.ds.patterns if p.id == state.specs[index].pattern_id), None)
    if pattern is None:
        raise PatternNotFound("образец слайда не найден в дизайн-системе")

    new_intent = _rewrite_intent(intent, pattern, finding.message, state.ds)
    _snapshot(state)
    _recompose(state, index, new_intent, pattern)

    findings = _checks(state, {state.specs[index].slide_id}, {finding_id})
    _persist(state, findings)


# ---------- заметки докладчика ----------

def set_slide_notes(deck_id: str, variant: str, slide_number: int, notes: str) -> None:
    state = _load(deck_id, variant)
    index = _slide_index(state, slide_number)

    _snapshot(state)
    state.plan.slides[index].notes = notes
    state.specs[index].notes = notes

    findings = _checks(state)
    _persist(state, findings)


# ---------- лента слайдов: добавить, копия, удалить, переставить ----------

def apply_slide_action(deck_id: str, variant: str, action: str, index: int, to: int | None = None) -> None:
    if action not in _SLIDE_ACTIONS:
        raise ValueError(f"неизвестное действие: {action}")
    state = _load(deck_id, variant)
    n = len(state.plan.slides)

    if action == "delete":
        if n <= 1:
            raise ValueError("нельзя удалить последний слайд варианта")
        pos = _slide_index(state, index)
        _snapshot(state)
        del state.plan.slides[pos]
        del state.specs[pos]
        del state.scenes[pos]

    elif action == "move":
        if to is None:
            raise ValueError("move: нужен параметр to")
        pos = _slide_index(state, index)
        target = to - 1
        if target < 0 or target >= n:
            raise SlideNotFound(f"позиции {to} нет: в варианте {n} слайдов")
        _snapshot(state)
        intent, spec, scene = state.plan.slides.pop(pos), state.specs.pop(pos), state.scenes.pop(pos)
        state.plan.slides.insert(target, intent)
        state.specs.insert(target, spec)
        state.scenes.insert(target, scene)

    else:  # add | copy
        if action == "add" and index == 0:
            pos = -1
        else:
            pos = _slide_index(state, index)
        _snapshot(state)
        used = [s.pattern_id for s in state.specs]
        if action == "copy":
            source = state.plan.slides[pos]
            new_intent = source.model_copy(update={"id": uuid.uuid4().hex})
            pattern = (next((p for p in state.ds.patterns if p.id == state.specs[pos].pattern_id), None)
                       or choose_pattern(new_intent, state.ds, used))
        else:
            new_intent = SlideIntent(id=uuid.uuid4().hex, kind=SlideKind.bullets, title="Новый слайд")
            pattern = choose_pattern(new_intent, state.ds, used)
        spec = compose(new_intent, pattern, state.ds)
        scene = build_scene(spec, pattern, state.ds, state.package_dir)
        insert_at = pos + 1
        state.plan.slides.insert(insert_at, new_intent)
        state.specs.insert(insert_at, spec)
        state.scenes.insert(insert_at, scene)

    findings = _checks(state)
    _persist(state, findings)


# ---------- вернуть последнюю правку ----------

def revert(deck_id: str, variant: str) -> None:
    history_dir = store.deck_variant_history_dir(deck_id, variant)
    numbers = sorted((int(p.stem) for p in history_dir.glob("*.json") if p.stem.isdigit()), reverse=True)
    if not numbers:
        raise NoHistory("истории правок нет")
    path = history_dir / f"{numbers[0]}.json"
    raw = store.read_json_file(path)

    ds_id = raw["design_system_id"]
    package_dir = store.design_system_dir(ds_id)
    ds = load_package(package_dir)
    state = _State(deck_id, variant, raw, ds_id, package_dir, ds)

    _persist(state, state.findings)
    path.unlink()
