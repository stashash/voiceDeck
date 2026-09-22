"""Конвейер от шаблона и брифа до файлов колоды, и слайд из фрагмента живой речи. Владелец: задача T-13.

generate_deck ведёт слайд по цепочке уже слитых слоёв (план -> паттерн -> текст под лимиты ->
инструкция -> сцена -> аудит -> экспорт) и пишет результат, находки и карточку прогона в
хранилище (designer.store). Сбой модели на одном слайде не останавливает колоду: слайд
собирается из текста плана без переписывания под лимиты, событие сообщает об этом.

Вид слайда в браузере (задача T-26): после экспорта pptx каждый слайд снимается картинкой
через постоянную сессию движка и кладётся в хранилище; deck.html собирается из картинок
с текстовым слоем, прежний вид чистой разметкой лежит рядом как deck.markup.html. Движка
нет: остаётся вид разметкой, событие хода работы сообщает об этом.

Варианты (задача T-12): план строится один раз, layout.variants.make_variants даёт три его
преобразования, каждое собирается и экспортируется отдельно и лежит в своём подкаталоге
хранилища. Контекстный (по картинке) аудит идёт на модели дорого, поэтому автоматически
считается только для первого запрошенного варианта; для остальных его запускает
run_contextual_audit по запросу человека, apply_fixes чинит выбранные находки одного варианта.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from designer import store
from designer.audit import fixes as audit_fixes
from designer.audit.contextual import audit_deck, audit_slide
from designer.audit.deterministic import run_checks
from designer.contracts import Deck, DeckPlan, DesignSystem, Finding, Pattern, Scene, SlideIntent, SlideSpec
from designer.export import convert, render
from designer.export.html import render_deck
from designer.export.html_image import render_deck_images, slide_html
from designer.export.pptx_deck import export_pptx
from designer.layout import variants as variant_axes
from designer.layout.capacity import main_group, slot_limits, unit_count
from designer.layout.compose import compose
from designer.layout.match import choose_pattern
from designer.layout.scene import build_scene
from designer.llm.client import LlmClient
from designer.llm.run import RunRecorder
from designer.llm.skills import load_skill
from designer.parse.describe import describe_patterns
from designer.parse.package import build_package, load_package
from designer.plan.planner import make_plan
from designer.plan.writer import fill_slots, speech_to_slide

_PLAN_SKILL = "plan-deck"
_FILL_SKILL = "fill-slots"

_TOP_TITLE_ROLES = ("title", "heading")
_TOP_BODY_ROLES = ("subtitle", "body", "caption")
_UNIT_LIMIT_ROLES = ("heading", "body", "number")

_KNOWN_VARIANTS = ("a", "b", "c")
_DEFAULT_VARIANTS = ["a"]


@dataclass(frozen=True)
class PipelineEvent:
    """Шаг конвейера: имя, номер слайда (если событие относится к слайду), вариант и время."""
    step: str
    slide_index: int | None
    at: float
    variant: str | None = None


OnEvent = Callable[[PipelineEvent], None]


def _emit(on_event: OnEvent, step: str, slide_index: int | None = None, variant: str | None = None) -> None:
    on_event(PipelineEvent(step=step, slide_index=slide_index, at=time.time(), variant=variant))


def _clean_variants(variants: list[str] | None) -> list[str]:
    codes = [v for v in (variants or _DEFAULT_VARIANTS) if v in _KNOWN_VARIANTS]
    seen: list[str] = []
    for code in codes:
        if code not in seen:
            seen.append(code)
    return seen or list(_DEFAULT_VARIANTS)


def _pattern_ids_for_plan(plan: DeckPlan, ds: DesignSystem) -> list[str]:
    """Паттерн на слайд плана при пустом списке занятых: опора для variant_used_seed варианта `c`."""
    used: list[str] = []
    for intent in plan.slides:
        used.append(choose_pattern(intent, ds, used).id)
    return used


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
        design_system = _describe(design_system, pptx_path, staging_dir)

        dest = store.design_system_dir(design_system.id)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.move(str(staging_dir), str(dest))
    return design_system


# ---------- генерация колоды ----------

def _describe(ds: DesignSystem, pptx_path: Path, package_dir: Path) -> DesignSystem:
    """Модель досказывает по картинке образца, для чего слайд и держится ли он на фото.

    Геометрия не видит плашку под фото, вшитую в фон макета: без описания такой паттерн
    берётся под текст и на слайде остаётся пустой белый квадрат. Сбой модели или движка
    картинок импорт не роняет: паттерны остаются такими, какими их дал разбор.
    DESIGNER_DESCRIBE=0 выключает шаг.
    """
    if os.environ.get("DESIGNER_DESCRIBE", "1") == "0" or not ds.patterns:
        return ds
    try:
        client = LlmClient.from_env()
        session = convert.get_session()
        by_slide = {p.source_slide - 1: p.id for p in ds.patterns}
        with ThreadPoolExecutor(max_workers=_llm_parallel()) as pool:
            pngs = dict(zip(by_slide.values(), pool.map(lambda i: session.png(pptx_path, i, 640), by_slide)))
        described = describe_patterns(ds, pngs, client)
    except Exception as error:  # noqa: BLE001 - шаг необязательный, причина уходит в журнал
        print(f"описание паттернов пропущено: {error}", flush=True)
        return ds
    (package_dir / "manifest.json").write_text(described.model_dump_json(indent=2), encoding="utf-8")
    return described


def generate_deck(ds_id: str, brief: str, purpose: str, audience: str, slide_count: int | None,
                   on_event: OnEvent, *, deck_id: str | None = None,
                   client: LlmClient | None = None, variants: list[str] | None = None) -> Deck:
    """Бриф -> план -> слайды -> аудит -> файлы. Пишет deck.json, run.json и файлы в хранилище.

    variants — какие варианты вёрстки собрать (по умолчанию только `a`). План строится один
    раз, layout.variants.make_variants даёт его преобразования под остальные варианты.
    Контекстный аудит по картинке автоматически считается только для первого варианта
    из списка: на все три варианта в 5 минут он не укладывается, для остальных его запускает
    run_contextual_audit по запросу. Возвращает Deck первого запрошенного варианта.
    """
    variant_codes = _clean_variants(variants)
    first_variant = variant_codes[0]
    deck_id = deck_id or store.new_deck_id()
    store.init_deck(deck_id, ds_id, variant_codes, brief=brief)
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

        plans = variant_axes.make_variants(plan, ds)
        chosen_by_a = _pattern_ids_for_plan(plans["a"], ds)

        decks: dict[str, Deck] = {}
        for variant_code in variant_codes:
            deck = _build_and_export_variant(
                deck_id, ds_id, variant_code, plans[variant_code], chosen_by_a, ds, package_dir,
                client, recorder, on_event, brief=brief,
                with_contextual_audit=(variant_code == first_variant),
            )
            store.save_run(deck_id, recorder.manifest(design_system_id=ds_id), variant=variant_code,
                            axis=variant_axes.VARIANT_AXES.get(variant_code, ""))
            decks[variant_code] = deck

        _emit(on_event, "done")
        return decks[first_variant]
    except Exception as exc:
        for variant_code in variant_codes:
            store.mark_deck_failed(deck_id, str(exc), variant=variant_code)
        raise
    finally:
        if owns_client:
            client.close()


def _build_and_export_variant(deck_id: str, ds_id: str, variant_code: str, variant_plan: DeckPlan,
                               chosen_by_a: list[str], ds: DesignSystem, package_dir: Path, client: LlmClient,
                               recorder: RunRecorder, on_event: OnEvent, *, brief: str,
                               with_contextual_audit: bool) -> Deck:
    """Слайды, аудит, экспорт и файлы одного варианта. Пишет deck.json варианта в хранилище."""
    used_patterns = variant_axes.variant_used_seed(variant_code, chosen_by_a)
    # Паттерны подбираются по порядку (каждый выбор учитывает предыдущие), а текст под слоты
    # пишется одновременно для всех слайдов: сервер модели с несколькими слотами отдаёт
    # почти втрое больше токенов в секунду, чем по одному запросу.
    patterns: list[Pattern] = []
    for intent in variant_plan.slides:
        pattern = choose_pattern(intent, ds, used_patterns)
        used_patterns.append(pattern.id)
        patterns.append(pattern)

    def _fill(job: tuple[int, SlideIntent, Pattern]) -> SlideIntent:
        index, intent, pattern = job
        _emit(on_event, "slide", index, variant_code)
        return _fill_intent(intent, pattern, client, on_event, index, variant_code, ds.tokens.type_scale)

    with recorder.stage(f"{variant_code}-fill-slots"):
        with ThreadPoolExecutor(max_workers=_llm_parallel()) as pool:
            filled = list(pool.map(_fill, [(i, intent, patterns[i]) for i, intent in enumerate(variant_plan.slides)]))
    recorder.use_skill(load_skill(_FILL_SKILL))

    specs: list[SlideSpec] = []
    scenes: list[Scene] = []
    for intent, pattern in zip(filled, patterns):
        spec = compose(intent, pattern, ds)
        specs.append(spec)
        scenes.append(build_scene(spec, pattern, ds, package_dir))

    _emit(on_event, "audit", None, variant_code)
    with recorder.stage(f"{variant_code}-audit"):
        findings = run_checks(scenes, ds)

    deck = Deck(id=deck_id, design_system_id=ds_id, variant=variant_code,
                plan=variant_plan, specs=specs, scenes=scenes)

    files_dir = store.deck_variant_files_dir(deck_id, variant_code)
    pptx_path = files_dir / "deck.pptx"
    _emit(on_event, "export-pptx", None, variant_code)
    with recorder.stage(f"{variant_code}-export-pptx"):
        export_pptx(specs, ds, package_dir, pptx_path)

    _emit(on_event, "export-html", None, variant_code)
    with recorder.stage(f"{variant_code}-export-html"):
        markup_html = render_deck(deck, ds, package_dir)
    # Вид чистой разметкой остаётся рядом: он не зависит от движка конвертации.
    (files_dir / "deck.markup.html").write_text(markup_html, encoding="utf-8")
    (files_dir / "deck.html").write_text(markup_html, encoding="utf-8")

    _emit(on_event, "convert", None, variant_code)
    png_paths: list[Path] = []
    if convert.available():
        try:
            with recorder.stage(f"{variant_code}-convert"):
                convert.to_pdf(pptx_path, files_dir / "deck.pdf")
        except convert.ConverterUnavailable:
            _emit(on_event, "convert-failed", None, variant_code)

        _emit(on_event, "render-slides", None, variant_code)
        with recorder.stage(f"{variant_code}-render-slides"):
            png_paths = _save_slide_images(deck_id, variant_code, pptx_path, len(specs), on_event)
        if png_paths:
            html_text = render_deck_images(deck, ds, [path.read_bytes() for path in png_paths])
            (files_dir / "deck.html").write_text(html_text, encoding="utf-8")
    else:
        _emit(on_event, "slide-images-skipped", None, variant_code)

    if png_paths and with_contextual_audit:
        _emit(on_event, "audit-contextual", None, variant_code)
        with recorder.stage(f"{variant_code}-audit-contextual"):
            findings = findings + _contextual_findings(scenes, png_paths, brief, client)

    store.save_deck_result(deck_id, deck, findings, variant=variant_code)
    return deck


def _save_slide_images(deck_id: str, variant: str, pptx_path: Path, count: int,
                        on_event: OnEvent) -> list[Path]:
    """Картинки слайдов варианта в хранилище. Пусто, если движок не смог их снять."""
    try:
        pngs = render.render_slides(pptx_path, count)
    except convert.ConverterUnavailable:
        _emit(on_event, "slide-images-failed", None, variant)
        return []

    slides_dir = store.deck_variant_slides_dir(deck_id, variant)
    for old in slides_dir.glob("slide-*.png"):
        old.unlink()
    paths: list[Path] = []
    for index, png in enumerate(pngs, start=1):
        path = slides_dir / f"slide-{index:03d}.png"
        path.write_bytes(png)
        paths.append(path)
    return paths


def _stored_slide_images(deck_id: str, variant: str) -> list[Path]:
    return sorted(store.deck_variant_slides_dir(deck_id, variant).glob("slide-*.png"))


def _role_limits(pattern: Pattern, intent: SlideIntent, n_units: int,
                 scale: list | None = None) -> tuple[dict[str, int], dict[str, int]]:
    """Лимиты знаков по ролям для fill_slots: заголовок и ключевое сообщение слайда, роли блока."""
    # Предел считается по рамке и нижнему кеглю роли, а не по кеглю образца: иначе заголовку достаётся одно слово.
    room = slot_limits(pattern, max(n_units, 0), scale)
    limits: dict[str, int] = {}
    title_slot = next((slot for slot in pattern.slots if slot.role in _TOP_TITLE_ROLES), None)
    if title_slot is not None:
        limits["title"] = room.get(title_slot.id, title_slot.max_chars)
    if intent.key_message:
        body_slot = next((slot for slot in pattern.slots if slot.role in _TOP_BODY_ROLES), None)
        if body_slot is not None:
            key = "subtitle" if body_slot.role == "subtitle" else "body"
            limits[key] = room.get(body_slot.id, body_slot.max_chars)

    unit_limits: dict[str, int] = {}
    group = main_group(pattern)
    if group is not None and n_units > 0:
        scaled = room
        for slot in group.unit_slots:
            if slot.role in _UNIT_LIMIT_ROLES and slot.role not in unit_limits:
                unit_limits[slot.role] = scaled.get(slot.id, slot.max_chars)
    return limits, unit_limits


def _llm_parallel() -> int:
    """Сколько запросов к модели идёт одновременно. Сервер должен быть поднят с тем же числом слотов."""
    try:
        return max(1, int(os.environ.get("DESIGNER_LLM_PARALLEL", "4")))
    except ValueError:
        return 4


def _fill_intent(intent: SlideIntent, pattern: Pattern, client: LlmClient, on_event: OnEvent,
                  index: int, variant: str = "a", scale: list | None = None) -> SlideIntent:
    """Текст слайда под лимиты выбранного паттерна.

    Сбой модели на этом слайде не пробрасывается дальше: слайд собирается из текста
    плана без переписывания, событие slide-fallback сообщает об этом.
    """
    group = main_group(pattern)
    n_units = unit_count(group, len(intent.items)) if group is not None else 0
    try:
        limits, unit_limits = _role_limits(pattern, intent, n_units, scale)
        filled = fill_slots(intent, limits, unit_limits, n_units, client)
        if n_units == 0 and intent.items:
            # У паттерна нет повторяющегося блока под пункты: длину пунктов ограничит
            # подгонка кегля на сцене, а не скилл заполнения, исходный текст не теряем.
            filled.items = list(intent.items)
        return filled
    except Exception:
        _emit(on_event, "slide-fallback", index, variant)
        return intent


def _contextual_findings(scenes: list[Scene], png_paths: list[Path], source_text: str,
                          client: LlmClient) -> list[Finding]:
    def _one(job: tuple[Scene, Path]) -> list[Finding]:
        scene, png_path = job
        return audit_slide(scene, png_path.read_bytes(), source_text, client)

    findings: list[Finding] = []
    with ThreadPoolExecutor(max_workers=_llm_parallel()) as pool:
        for found in pool.map(_one, list(zip(scenes, png_paths))):
            findings.extend(found)
    findings.extend(audit_deck(scenes, client))
    return findings


# ---------- контекстный аудит и починка по запросу (T-12: остальные варианты) ----------

def run_contextual_audit(deck_id: str, variant: str, *, client: LlmClient | None = None) -> list[Finding]:
    """Контекстный аудит варианта по запросу человека: сцены и картинки уже лежат в хранилище.

    generate_deck считает контекстный аудит автоматически только для первого запрошенного
    варианта; для остальных эта функция запускается позже отдельным вызовом API.
    """
    state = store.load_deck_state(deck_id, variant)
    if state is None:
        raise ValueError(f"колода не найдена: {deck_id}/{variant}")

    png_paths = _stored_slide_images(deck_id, variant)
    if not png_paths:
        raise RuntimeError("картинок слайдов нет: конвертер недоступен")

    scenes = [Scene.model_validate(item) for item in state["scenes"]]
    owns_client = client is None
    client = client or LlmClient.from_env()
    try:
        new_findings = _contextual_findings(scenes, png_paths, state.get("brief", ""), client)
    finally:
        if owns_client:
            client.close()

    existing = [Finding.model_validate(item) for item in state["findings"]]
    deck = Deck(id=deck_id, design_system_id=state["design_system_id"], variant=variant,
                plan=DeckPlan.model_validate(state["plan"]),
                specs=[SlideSpec.model_validate(item) for item in state["specs"]], scenes=scenes)
    store.save_deck_result(deck_id, deck, existing + new_findings, variant=variant)
    return new_findings


def apply_fixes(deck_id: str, variant: str, finding_ids: list[str]) -> tuple[list[dict], list[Finding]]:
    """Чинит выбранные находки варианта: пересобирает сцены, файлы и отдаёт отчёт с новыми находками.

    Саму починку делает designer.audit.fixes.apply_fixes (задача T-21) по замороженной
    сигнатуре: инструкции, сцены, находки, id выбранных находок, дизайн-система.
    """
    state = store.load_deck_state(deck_id, variant)
    if state is None:
        raise ValueError(f"колода не найдена: {deck_id}/{variant}")

    ds_id = state["design_system_id"]
    package_dir = store.design_system_dir(ds_id)
    ds = load_package(package_dir)

    specs = [SlideSpec.model_validate(item) for item in state["specs"]]
    scenes = [Scene.model_validate(item) for item in state["scenes"]]
    findings = [Finding.model_validate(item) for item in state["findings"]]

    new_specs, new_scenes, report = audit_fixes.apply_fixes(specs, scenes, findings, finding_ids, ds)

    # Детерминированные находки пересчитываются заново по новым сценам: гео могла поменяться.
    # Контекстные находки, которые не чинили, переносятся как есть — их даёт только модель.
    kept_contextual = [f for f in findings if f.kind == "contextual" and f.id not in finding_ids]
    all_findings = run_checks(new_scenes, ds) + kept_contextual

    deck = Deck(id=deck_id, design_system_id=ds_id, variant=variant,
                plan=DeckPlan.model_validate(state["plan"]), specs=new_specs, scenes=new_scenes)

    files_dir = store.deck_variant_files_dir(deck_id, variant)
    pptx_path = files_dir / "deck.pptx"
    export_pptx(new_specs, ds, package_dir, pptx_path)
    markup_html = render_deck(deck, ds, package_dir)
    (files_dir / "deck.markup.html").write_text(markup_html, encoding="utf-8")
    (files_dir / "deck.html").write_text(markup_html, encoding="utf-8")
    if convert.available():
        try:
            convert.to_pdf(pptx_path, files_dir / "deck.pdf")
        except convert.ConverterUnavailable:
            pass
        png_paths = _save_slide_images(deck_id, variant, pptx_path, len(new_specs), lambda event: None)
        if png_paths:
            html_text = render_deck_images(deck, ds, [path.read_bytes() for path in png_paths])
            (files_dir / "deck.html").write_text(html_text, encoding="utf-8")

    store.save_deck_result(deck_id, deck, all_findings, variant=variant)
    return report, all_findings


# ---------- живой режим ----------

@dataclass(frozen=True)
class LiveSlide:
    """Слайд живого режима: сцена, её HTML и картинка слайда (None, если движка нет)."""
    scene: Scene
    html: str
    png: bytes | None = None


def live_slide(ds_id: str, chunk_text: str, used_pattern_ids: list[str], *,
                client: LlmClient | None = None) -> LiveSlide | None:
    """Фрагмент устной речи -> слайд в стиле дизайн-системы, либо None (слайд не нужен)."""
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
        scene = build_scene(spec, pattern, ds, package_dir)
    finally:
        if owns_client:
            client.close()

    png = _live_png(spec, ds, package_dir)
    if png is None:
        # Движка нет: на сцену идёт прежний вид чистой разметкой.
        solo = Deck(id="live", design_system_id=ds_id, variant="a",
                    plan=DeckPlan(title="", purpose="", slides=[]), specs=[spec], scenes=[scene])
        return LiveSlide(scene=scene, html=render_deck(solo, ds, package_dir))
    return LiveSlide(scene=scene, html=slide_html(png, scene, ds), png=png)


def _live_png(spec: SlideSpec, ds: DesignSystem, package_dir: Path) -> bytes | None:
    if not convert.available():
        return None
    try:
        return render.render_spec(spec, ds, package_dir)
    except convert.ConverterUnavailable:
        return None
