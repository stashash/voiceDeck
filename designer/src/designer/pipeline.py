"""Конвейер от шаблона и брифа до файлов колоды, и слайд из фрагмента живой речи. Владелец: задача T-13.

generate_deck ведёт слайд по цепочке уже слитых слоёв (план -> паттерн -> текст под лимиты ->
инструкция -> сцена -> аудит -> экспорт) и пишет результат, находки и карточку прогона в
хранилище (designer.store). Сбой модели на одном слайде не останавливает колоду: слайд
собирается из текста плана без переписывания под лимиты, событие сообщает об этом.
"""
from __future__ import annotations

import shutil
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from designer import store
from designer.audit.contextual import audit_deck, audit_slide
from designer.audit.deterministic import run_checks
from designer.contracts import Deck, DesignSystem, Finding, Pattern, Scene, SlideIntent, SlideSpec
from designer.export import convert
from designer.export.html import render_deck
from designer.export.pptx_deck import export_pptx
from designer.layout.capacity import main_group, slot_limits, unit_count
from designer.layout.compose import compose
from designer.layout.match import choose_pattern
from designer.layout.scene import build_scene
from designer.llm.client import LlmClient
from designer.llm.run import RunRecorder
from designer.llm.skills import load_skill
from designer.parse.package import build_package, load_package
from designer.plan.planner import make_plan
from designer.plan.writer import fill_slots, speech_to_slide

_PLAN_SKILL = "plan-deck"
_FILL_SKILL = "fill-slots"

_TOP_TITLE_ROLES = ("title", "heading")
_TOP_BODY_ROLES = ("subtitle", "body", "caption")
_UNIT_LIMIT_ROLES = ("heading", "body", "number")


@dataclass(frozen=True)
class PipelineEvent:
    """Шаг конвейера: имя, номер слайда (если событие относится к слайду) и время."""
    step: str
    slide_index: int | None
    at: float


OnEvent = Callable[[PipelineEvent], None]


def _emit(on_event: OnEvent, step: str, slide_index: int | None = None) -> None:
    on_event(PipelineEvent(step=step, slide_index=slide_index, at=time.time()))


# ---------- импорт шаблона ----------

def import_template(pptx_bytes: bytes, filename: str) -> DesignSystem:
    """Разбирает загруженный pptx и кладёт пакет дизайн-системы в хранилище."""
    with tempfile.TemporaryDirectory(prefix="designer-import-") as tmp:
        tmp_root = Path(tmp)
        pptx_path = tmp_root / "upload" / (Path(filename).name or "template.pptx")
        pptx_path.parent.mkdir(parents=True, exist_ok=True)
        pptx_path.write_bytes(pptx_bytes)

        staging_dir = tmp_root / "package"
        design_system = build_package(pptx_path, staging_dir)

        dest = store.design_system_dir(design_system.id)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.move(str(staging_dir), str(dest))
    return design_system


# ---------- генерация колоды ----------

def generate_deck(ds_id: str, brief: str, purpose: str, audience: str, slide_count: int | None,
                   on_event: OnEvent, *, deck_id: str | None = None,
                   client: LlmClient | None = None) -> Deck:
    """Бриф -> план -> слайды -> аудит -> файлы. Пишет deck.json, run.json и файлы в хранилище."""
    deck_id = deck_id or store.new_deck_id()
    store.init_deck(deck_id, ds_id)
    package_dir = store.design_system_dir(ds_id)
    ds = load_package(package_dir)

    owns_client = client is None
    client = client or LlmClient.from_env()
    recorder = RunRecorder(model=client.model)
    try:
        _emit(on_event, "plan")
        with recorder.stage("plan"):
            plan = make_plan(brief, purpose, audience, slide_count, client)
        recorder.use_skill(load_skill(_PLAN_SKILL))

        specs: list[SlideSpec] = []
        scenes: list[Scene] = []
        used_patterns: list[str] = []
        for index, intent in enumerate(plan.slides):
            _emit(on_event, "slide", index)
            spec, scene = _build_slide(intent, ds, package_dir, client, recorder, used_patterns, on_event, index)
            specs.append(spec)
            scenes.append(scene)

        _emit(on_event, "audit")
        with recorder.stage("audit"):
            findings = run_checks(scenes, ds)

        deck = Deck(id=deck_id, design_system_id=ds_id, variant="a", plan=plan, specs=specs, scenes=scenes)

        files_dir = store.deck_files_dir(deck_id)
        pptx_path = files_dir / "deck.pptx"
        _emit(on_event, "export-pptx")
        with recorder.stage("export-pptx"):
            export_pptx(specs, ds, package_dir, pptx_path)

        _emit(on_event, "export-html")
        with recorder.stage("export-html"):
            html_text = render_deck(deck, ds, package_dir)
        (files_dir / "deck.html").write_text(html_text, encoding="utf-8")

        _emit(on_event, "convert")
        png_paths: list[Path] = []
        if convert.available():
            try:
                with recorder.stage("convert"):
                    convert.to_pdf(pptx_path, files_dir / "deck.pdf")
                    png_paths = convert.to_png(pptx_path, files_dir / "png")
            except convert.ConverterUnavailable:
                _emit(on_event, "convert-failed")

        if png_paths:
            _emit(on_event, "audit-contextual")
            with recorder.stage("audit-contextual"):
                findings = findings + _contextual_findings(scenes, png_paths, brief, client)

        store.save_run(deck_id, recorder.manifest(design_system_id=ds_id))
        store.save_deck_result(deck_id, deck, findings)
        _emit(on_event, "done")
        return deck
    except Exception as exc:
        store.mark_deck_failed(deck_id, str(exc))
        raise
    finally:
        if owns_client:
            client.close()


def _build_slide(intent: SlideIntent, ds: DesignSystem, package_dir: Path, client: LlmClient,
                  recorder: RunRecorder, used_patterns: list[str], on_event: OnEvent,
                  index: int) -> tuple[SlideSpec, Scene]:
    """Паттерн, текст под лимиты, инструкция и сцена одного слайда.

    Сбой модели на этом слайде не пробрасывается дальше: слайд собирается из текста
    плана без переписывания, событие slide-fallback сообщает об этом.
    """
    pattern = choose_pattern(intent, ds, used_patterns)
    used_patterns.append(pattern.id)
    group = main_group(pattern)
    n_units = unit_count(group, len(intent.items)) if group is not None else 0

    slide_intent = intent
    try:
        limits, unit_limits = _role_limits(pattern, intent, n_units)
        with recorder.stage("fill-slots"):
            filled = fill_slots(intent, limits, unit_limits, n_units, client)
        recorder.use_skill(load_skill(_FILL_SKILL))
        if n_units == 0 and intent.items:
            # У паттерна нет повторяющегося блока под пункты: длину пунктов ограничит
            # подгонка кегля на сцене, а не скилл заполнения, — исходный текст не теряем.
            filled.items = list(intent.items)
        slide_intent = filled
    except Exception:
        _emit(on_event, "slide-fallback", index)

    spec = compose(slide_intent, pattern, ds)
    scene = build_scene(spec, pattern, ds, package_dir)
    return spec, scene


def _role_limits(pattern: Pattern, intent: SlideIntent, n_units: int) -> tuple[dict[str, int], dict[str, int]]:
    """Лимиты знаков по ролям для fill_slots: заголовок и ключевое сообщение слайда, роли блока."""
    limits: dict[str, int] = {}
    title_slot = next((slot for slot in pattern.slots if slot.role in _TOP_TITLE_ROLES), None)
    if title_slot is not None:
        limits["title"] = title_slot.max_chars
    if intent.key_message:
        body_slot = next((slot for slot in pattern.slots if slot.role in _TOP_BODY_ROLES), None)
        if body_slot is not None:
            key = "subtitle" if body_slot.role == "subtitle" else "body"
            limits[key] = body_slot.max_chars

    unit_limits: dict[str, int] = {}
    group = main_group(pattern)
    if group is not None and n_units > 0:
        scaled = slot_limits(pattern, n_units)
        for slot in group.unit_slots:
            if slot.role in _UNIT_LIMIT_ROLES and slot.role not in unit_limits:
                unit_limits[slot.role] = scaled.get(slot.id, slot.max_chars)
    return limits, unit_limits


def _contextual_findings(scenes: list[Scene], png_paths: list[Path], source_text: str,
                          client: LlmClient) -> list[Finding]:
    findings: list[Finding] = []
    for scene, png_path in zip(scenes, png_paths):
        findings.extend(audit_slide(scene, png_path.read_bytes(), source_text, client))
    findings.extend(audit_deck(scenes, client))
    return findings


# ---------- живой режим ----------

def live_slide(ds_id: str, chunk_text: str, used_pattern_ids: list[str], *,
                client: LlmClient | None = None) -> Scene | None:
    """Фрагмент устной речи -> сцена одного слайда в стиле дизайн-системы, либо None (слайд не нужен)."""
    package_dir = store.design_system_dir(ds_id)
    ds = load_package(package_dir)

    owns_client = client is None
    client = client or LlmClient.from_env()
    try:
        kinds = sorted({pattern.kind for pattern in ds.patterns})
        if not kinds:
            return None
        intent = speech_to_slide(chunk_text, kinds, client)
        if not intent.title:
            return None
        pattern = choose_pattern(intent, ds, used_pattern_ids)
        spec = compose(intent, pattern, ds)
        return build_scene(spec, pattern, ds, package_dir)
    finally:
        if owns_client:
            client.close()
