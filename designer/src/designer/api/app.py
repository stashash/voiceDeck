"""FastAPI-сервис: пакеты дизайн-систем, генерация колоды, живой режим. Владелец: задача T-13, варианты — T-12."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import math
import os
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from decimal import Decimal

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse, HTMLResponse
from designer.edit_runtime import ensure_export, lock

from designer import edit, pipeline, store
from designer.agent_hook import AgentCheckUnavailable, _client_for
from designer.agent_hook import check_agent as agent_check
from designer.agent_hook import list_agents as agent_list
from designer.agent_hook import load_assignments as agent_load_assignments
from designer.agent_hook import save_assignments as agent_save_assignments
from designer.agents import load_model_settings, save_model_settings
from designer.api.schemas import (
    AgentAssignmentsRequest,
    AuditContextualResponse,
    DeckCreateRequest,
    DeckCreateResponse,
    DeckFixRequest,
    DeckFixResponse,
    DeckListResponse,
    DeckRewriteRequest,
    DeckStateResponse,
    DeckVariantState,
    DatasetBundlePlanResponse,
    DatasetTablePlan,
    DesignSystemListResponse,
    DesignSystemPatchRequest,
    HealthResponse,
    InsightView,
    InsightsResponse,
    LiveBoundaryRequest,
    LiveWarmRequest,
    ModelSettingsRequest,
    LiveBoundaryResponse,
    LiveSlideRequest,
    LiveSlideResponse,
    SlideActionRequest,
    SlideAskRequest,
    SlideNotesRequest,
    SlidePatternRequest,
    SlidePatternsResponse,
    SlideTextRequest,
    SlideMoveElementRequest,
    ElementActionRequest,
    TablePreview,
)
from designer.contracts import ChartSpec, DataProvenance, DesignSystem, RunManifest, Series, TableSpec
from designer.contracts import Tokens
from designer.brandbook_json import BrandTokenError, resolve_tokens
from designer.brandbook_import import MAX_SOURCE_BYTES, parse_brandbook_source
from designer.export import convert
from designer.insights import source as insights_source
from designer.insights.plan import chart_number_supported, plan_table
from designer.insights.profile import profile_table
from designer.insights.provenance import persist_source
from designer.insights.labels import field_label
from designer.insights import suggest as insights_suggest
from designer.insights import table as insights_table
from designer.llm.client import LlmClient, LlmResponseError, ModelLoading, auth_headers
from designer.llm.skills import SkillError, load_skill
from designer.parse.package import load_package
from designer.plan.writer import speech_boundary

_ORIGINS_ENV = "DESIGNER_ALLOWED_ORIGINS"
_HEALTH_SKILLS = ("plan-deck", "fill-slots", "speech-to-slide", "speech-boundary", "audit-slide", "audit-deck")

from designer.api.editor import router as editor_router

app = FastAPI(title="Цифровой дизайнер презентаций")
app.include_router(editor_router)
from designer.api.deck_voice import router as deck_voice_router
app.include_router(deck_voice_router)
from designer.api.editor_documents import router as editor_documents_router
app.include_router(editor_documents_router)
from designer.api.library import router as library_router
app.include_router(library_router)

_origins = [origin.strip() for origin in os.environ.get(_ORIGINS_ENV, "").split(",") if origin.strip()]
# Приложение открывают и по localhost, и по 127.0.0.1: второй адрес пускается так же, как в Java-сервисе,
# иначе со страницы http://127.0.0.1:8088 не открывается ни один запрос к designer.
_origins += [o.replace("localhost", "127.0.0.1") for o in _origins if "localhost" in o and o.replace("localhost", "127.0.0.1") not in _origins]
if _origins:
    app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_methods=["*"], allow_headers=["*"])


def get_llm_client() -> LlmClient:
    """Клиент модели на запрос: через агента, назначенного на генерацию колоды.

    Переопределяется в тестах через app.dependency_overrides.
    """
    return _client_for("deck")


def get_live_llm_client() -> LlmClient:
    """Клиент модели живого режима: агент, назначенный на Live, короткое ожидание загрузки."""
    return _client_for("live")


def _close(client: object) -> None:
    """Клиент держит пул соединений к серверу модели: закрывается после запроса, иначе за долгое
    выступление соединения копятся. Тестовые заглушки без close пропускаются."""
    close = getattr(client, "close", None)
    if callable(close):
        close()


_live_lock = threading.Lock()
_live_busy = 0


@contextmanager
def _live_call() -> Iterator[int]:
    """Считает запросы Live к модели, идущие одновременно: по этому числу видно очередь в сервере модели."""
    global _live_busy
    with _live_lock:
        _live_busy += 1
        busy = _live_busy
    try:
        yield busy
    finally:
        with _live_lock:
            _live_busy -= 1


def _not_found(ds_id_error: bool = False):
    return HTTPException(404, "дизайн-система не найдена" if ds_id_error else "не найдено")


# ---------- дизайн-системы ----------

@app.on_event("startup")
def _upgrade_legacy_design_systems() -> None:
    # Готовые данные из репозитория кладутся до приёма запросов: список систем не видит их наполовину.
    store.seed_demo()
    store.recover_interrupted_decks()
    # Превью старых пакетов строятся движком конвертации: в фоне, чтобы сервис поднялся сразу.
    import threading
    threading.Thread(target=pipeline.upgrade_legacy_packages, daemon=True).start()


@app.post("/design-systems", response_model=DesignSystem)
async def upload_design_system(background_tasks: BackgroundTasks, file: UploadFile = File(...)) -> DesignSystem:
    if not (file.filename or "").lower().endswith(".pptx"):
        raise HTTPException(400, "Файл не pptx")
    data = await file.read()
    try:
        design_system = pipeline.import_template(data, file.filename or "template.pptx")
    except pipeline.CorruptedTemplateError:
        raise HTTPException(400, "Файл повреждён или сохранён не до конца")
    background_tasks.add_task(pipeline.run_describe, design_system.id)
    return design_system


@app.get("/design-systems", response_model=DesignSystemListResponse)
def list_design_systems() -> DesignSystemListResponse:
    return DesignSystemListResponse(ids=store.list_design_system_ids(), items=pipeline.list_design_systems())


@app.get("/design-systems/{ds_id}", response_model=DesignSystem)
def get_design_system(ds_id: str) -> DesignSystem:
    try:
        return load_package(store.design_system_dir(ds_id))
    except (store.InvalidId, FileNotFoundError):
        raise _not_found(True)


_MAX_BRANDBOOK_BYTES = MAX_SOURCE_BYTES
_BRANDBOOK_STATE = "brandbook-state.json"
_BRANDBOOK_ASSETS = "brandbook-assets"


def _brandbook_paths(ds_id: str):
    package = store.design_system_dir(ds_id)
    return package, package / _BRANDBOOK_STATE


def _resolved_brandbook_tokens(template: Tokens, brand: Tokens, priority: str) -> Tokens:
    if priority not in {"brand", "template"}:
        raise HTTPException(422, "Приоритет должен быть brand или template.")
    return resolve_tokens(template, brand, brand_priority=(priority == "brand"))


def _brandbook_response(ds: DesignSystem, state: dict) -> dict:
    return {
        "design_system": ds.model_dump(mode="json"),
        "file_name": state["file_name"],
        "sha256": state["sha256"],
        "priority": state["priority"],
        "source_format": state.get("source_format", "json"),
        "warnings": state.get("warnings", []),
        "assets": state.get("assets", []),
        "rules": state.get("brand_rules"),
        "source": state.get("source"),
        "brand_fields": state["brand_fields"],
        "applied_fields": [name for name in state["brand_fields"] if name in {"colors", "fonts", "type_scale", "margins", "grid", "chart_style", "logo"}],
    }


@app.get("/design-systems/{ds_id}/brandbook")
def get_brandbook(ds_id: str) -> dict:
    try:
        package, state_path = _brandbook_paths(ds_id)
        ds = load_package(package)
        if not state_path.is_file():
            return {"design_system": ds.model_dump(mode="json"), "file_name": "", "sha256": "",
                    "priority": "brand", "brand_fields": [], "applied_fields": []}
        state = json.loads(state_path.read_text(encoding="utf-8"))
        return _brandbook_response(ds, state)
    except (store.InvalidId, FileNotFoundError):
        raise _not_found(True)


@app.post("/design-systems/{ds_id}/brandbook")
async def import_brandbook(ds_id: str, file: UploadFile | None = File(None), priority: str = Form("brand")) -> dict:
    """Import bounded JSON/PDF/ZIP brandbooks, or change priority using saved tokens."""
    try:
        package, state_path = _brandbook_paths(ds_id)
        ds = load_package(package)
    except (store.InvalidId, FileNotFoundError):
        raise _not_found(True)
    state = None
    if state_path.is_file():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(500, "Состояние брендбука повреждено; повторно загрузите исходный файл.") from exc
    if priority not in {"brand", "template"}:
        raise HTTPException(422, "Приоритет должен быть brand или template.")
    if file is not None:
        try:
            raw = await file.read(_MAX_BRANDBOOK_BYTES + 1)
        finally:
            await file.close()
        if len(raw) > _MAX_BRANDBOOK_BYTES:
            raise HTTPException(413, "Файл брендбука больше 20 МиБ.")
        if (file.filename or "").lower().endswith(".json") and len(raw) > 256 * 1024:
            raise HTTPException(413, "JSON с токенами больше 256 КиБ.")
        try:
            imported = await run_in_threadpool(parse_brandbook_source, raw, file.filename or "brandbook.json")
            brand = imported.tokens
        except BrandTokenError as exc:
            raise HTTPException(422, str(exc)) from exc
        try:
            template = Tokens.model_validate(state["template_tokens"]) if state else ds.tokens
        except (KeyError, ValueError) as exc:
            raise HTTPException(500, "Сохранённые исходные токены повреждены.") from exc
        filename = insights_table.file_name(file.filename or "brandbook.json")
        source_hash = imported.raw_sha256
        brand_fields = [name for name, values in (("colors", brand.colors), ("fonts", brand.fonts),
                                                   ("type_scale", brand.type_scale)) if values]
        if any(getattr(brand.margins, side) != 0 for side in ("left", "top", "right", "bottom")):
            brand_fields.append("margins")
        if brand.guides_x or brand.guides_y:
            brand_fields.append("grid")
        if brand.chart_style:
            brand_fields.append("chart_style")
        if imported.rules and imported.rules.get("logo"):
            brand_fields.append("logo")
    else:
        if state is None:
            raise HTTPException(422, "Сначала загрузите файл JSON с токенами.")
        try:
            template = Tokens.model_validate(state["template_tokens"])
            brand = Tokens.model_validate(state["brand_tokens"])
        except (KeyError, ValueError) as exc:
            raise HTTPException(500, "Сохранённые токены брендбука повреждены.") from exc
        filename, source_hash, brand_fields = state["file_name"], state["sha256"], state["brand_fields"]
        imported = None
    resolved = _resolved_brandbook_tokens(template, brand, priority)
    if priority == "brand" and any(color.role == "background" for color in brand.colors) and not any(color.role == "text" for color in brand.colors):
        from designer.contracts import ColorToken
        from designer.viz.palette import contrast_ratio
        bg = next(color.hex for color in brand.colors if color.role == "background")
        text = next((color.hex for color in resolved.colors if color.role == "text"), "202124")
        if contrast_ratio(bg, text) < 4.5:
            text = max(("FFFFFF", "162032"), key=lambda color: contrast_ratio(bg, color))
            resolved.colors = [ColorToken(hex=text, role="text", share=1, source="usage")] + [color for color in resolved.colors if color.role != "text"]
    from designer.brand_assets import save_brand_assets
    from designer.contracts import BrandRules
    original_rules = state.get("template_rules") if state else (ds.brand_rules.model_dump() if ds.brand_rules else None)
    if imported is not None:
        try:
            brand_assets, imported_rules, saved_assets = save_brand_assets(package, imported)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        assets = [asset for asset in ds.assets if not asset.path.startswith("brandbook-assets/")] + brand_assets
        brand_rules = imported_rules.model_dump() if imported_rules else None
    else:
        assets, saved_assets = ds.assets, state.get("assets", [])
        brand_rules = state.get("brand_rules")
    active_rules = brand_rules if priority == "brand" else original_rules
    if priority == "brand" and brand.fonts and not active_rules:
        active_rules = {"clear_space": .012}
    if priority == "brand":
        preferred_colors = {color.role: color.hex for color in reversed(resolved.colors) if color.role != "other"}
        overrides = {color.hex: preferred_colors[color.role] for color in template.colors
                     if color.role in preferred_colors and color.hex != preferred_colors[color.role]}
        if overrides:
            active_rules = {**(active_rules or {}), "color_overrides": overrides}
    background = next((color.hex for color in resolved.colors if color.role == "background"), None)
    from designer.contracts import Pattern
    patterns = [Pattern.model_validate(pattern) for pattern in state["template_patterns"]] if state and state.get("template_patterns") else ds.patterns
    if priority == "brand" and any(color.role == "background" for color in brand.colors) and background:
        luminance = sum(weight * int(background[index:index + 2], 16) for weight, index in ((.2126, 0), (.7152, 2), (.0722, 4)))
        patterns = [pattern.model_copy(update={"background_color": background, "theme": "dark" if luminance < 128 else "light"}) for pattern in ds.patterns]
    from designer.brand_assets import embed_fonts
    resolved = embed_fonts(package, resolved)
    updated = ds.model_copy(update={"tokens": resolved, "assets": assets,
                                    "patterns": patterns,
                                    "brand_rules": BrandRules.model_validate(active_rules) if active_rules else None})
    store.write_text_atomic(package / "manifest.json", updated.model_dump_json(indent=2))
    new_state = {"schema_version": 1, "file_name": filename, "sha256": source_hash, "priority": priority,
                 "brand_fields": brand_fields, "template_tokens": template.model_dump(mode="json"),
                 "brand_tokens": brand.model_dump(mode="json"),
                 "template_rules": original_rules, "brand_rules": brand_rules,
                 "template_patterns": state.get("template_patterns") if state else [pattern.model_dump(mode="json") for pattern in ds.patterns],
                 "source": imported.source if imported is not None else state.get("source"),
                 "source_format": imported.source_format if imported else state.get("source_format", "json"),
                 "warnings": list(imported.warnings) if imported else state.get("warnings", []),
                 "assets": saved_assets}
    store.write_text_atomic(state_path, json.dumps(new_state, ensure_ascii=False, indent=2))
    return _brandbook_response(updated, new_state)


@app.delete("/design-systems/{ds_id}/brandbook")
def remove_brandbook(ds_id: str) -> dict:
    """Remove the brand overlay and restore the original template tokens."""
    try:
        package, state_path = _brandbook_paths(ds_id)
        ds = load_package(package)
    except (store.InvalidId, FileNotFoundError):
        raise _not_found(True)
    if not state_path.is_file():
        return {"design_system": ds.model_dump(mode="json"), "removed": False}
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        template = Tokens.model_validate(state["template_tokens"])
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        raise HTTPException(500, "Сохранённые исходные токены повреждены.") from exc
    from designer.contracts import BrandRules
    original_rules = state.get("template_rules")
    updated = ds.model_copy(update={"tokens": template,
        "assets": [asset for asset in ds.assets if not asset.path.startswith("brandbook-assets/")],
        "brand_rules": BrandRules.model_validate(original_rules) if original_rules else None})
    if state.get("template_patterns"):
        from designer.contracts import Pattern
        updated.patterns = [Pattern.model_validate(pattern) for pattern in state["template_patterns"]]
    store.write_text_atomic(package / "manifest.json", updated.model_dump_json(indent=2))
    state_path.unlink(missing_ok=True)
    import shutil
    shutil.rmtree(package / _BRANDBOOK_ASSETS, ignore_errors=True)
    return {"design_system": updated.model_dump(mode="json"), "removed": True}


@app.patch("/design-systems/{ds_id}", response_model=DesignSystem)
def patch_design_system(ds_id: str, payload: DesignSystemPatchRequest) -> DesignSystem:
    try:
        return pipeline.patch_design_system(
            ds_id, name=payload.name, pattern_overrides=payload.pattern_overrides,
            removal_confirmed=payload.removal_confirmed,
        )
    except (store.InvalidId, FileNotFoundError):
        raise _not_found(True)


@app.delete("/design-systems/{ds_id}", status_code=204)
def delete_design_system(ds_id: str) -> Response:
    try:
        store.design_system_dir(ds_id)  # проверка id, дальше молча — удаление идемпотентно
    except store.InvalidId:
        raise _not_found(True)
    store.delete_design_system(ds_id)
    return Response(status_code=204)


@app.post("/design-systems/{ds_id}/describe", response_model=DesignSystem)
def describe_design_system(ds_id: str, background_tasks: BackgroundTasks) -> DesignSystem:
    try:
        design_system = pipeline.start_describe(ds_id)
    except (store.InvalidId, FileNotFoundError):
        raise _not_found(True)
    background_tasks.add_task(pipeline.run_describe, ds_id)
    return design_system


@app.get("/design-systems/{ds_id}/previews/{pattern_id}.png")
def get_design_system_preview(ds_id: str, pattern_id: str) -> FileResponse:
    try:
        path = store.design_system_asset_path(ds_id, f"previews/{pattern_id}.png")
    except store.InvalidId:
        raise _not_found(True)
    if path is None:
        raise HTTPException(400, "недопустимый путь")
    if not path.is_file():
        raise HTTPException(404, "превью не найдено")
    return FileResponse(str(path), media_type="image/png")


@app.get("/design-systems/{ds_id}/tokens.css")
def get_tokens_css(ds_id: str) -> FileResponse:
    try:
        path = store.design_system_dir(ds_id) / "tokens.css"
    except store.InvalidId:
        raise _not_found(True)
    if not path.is_file():
        raise HTTPException(404, "нет tokens.css")
    return FileResponse(str(path), media_type="text/css")


@app.get("/design-systems/{ds_id}/assets/{name:path}")
def get_design_system_asset(ds_id: str, name: str) -> FileResponse:
    try:
        path = store.design_system_asset_path(ds_id, f"assets/{name}")
    except store.InvalidId:
        raise _not_found(True)
    if path is None:
        raise HTTPException(400, "недопустимый путь")
    if not path.is_file():
        raise HTTPException(404, "файл не найден")
    return FileResponse(str(path))


# ---------- колоды ----------

@app.get("/decks", response_model=DeckListResponse)
def list_decks() -> DeckListResponse:
    return DeckListResponse(items=[d for d in pipeline.list_decks() if not (store.deck_dir(d['id']) / '.deleted').exists()])


@app.post("/insights/table", response_model=TablePreview)
async def table_preview(file: UploadFile = File(...)) -> TablePreview:
    """Разбор файла без модели: строки и столбцы на плашке и ошибка файла приходят сразу, до подсказок.

    Таблицу на картинке (png, jpg, картинка в xlsx) прочитает модель: здесь только пометка from_image.
    """
    data = await file.read(insights_table.MAX_IMAGE_BYTES + 1)
    name = insights_table.file_name(file.filename or "")
    try:
        table, from_image = await run_in_threadpool(insights_source.preview, data, file.filename or "")
    except insights_table.TableError as exc:
        raise HTTPException(422, str(exc)) from exc
    if table is None:
        return TablePreview(table_name=name, from_image=from_image)
    return TablePreview(table_name=table.name, sheet=table.sheet, rows=len(table.rows), columns=len(table.headers))


_MAX_PLAN_FILES = 7
_MAX_PLAN_TABLES = 21
_MAX_PLAN_TOTAL_BYTES = insights_table.MAX_BYTES * _MAX_PLAN_FILES
_REFERENCE_PAGE_ROWS = 7  # native PPTX table renderer limits readable tables to seven rows
_MAX_REFERENCE_PAGES = 30  # 201 source rows need 29 slides at this page size
_MAX_BUNDLE_SLIDES = 60


def _json_safe(value):
    """Serialize internal immutable plan dataclasses without rounding Decimal values."""
    if isinstance(value, Decimal):
        return format(value, "f")
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    return value


def _reference_pages(suggestion: dict, snapshot: dict) -> list[dict]:
    """Split a large reference dataset into readable, provenance-bounded slide pages."""
    if suggestion.get("visual") != "table":
        return [suggestion]
    table = snapshot.get("table") or {}
    rows = table.get("rows") or []
    lines = table.get("row_lines") or []
    headers = table.get("headers") or []
    if not rows or len(rows) != len(lines) or len(headers) != len(rows[0]):
        raise HTTPException(422, "Исходная таблица неполна и не может быть разбита на страницы.")
    pages = math.ceil(len(rows) / _REFERENCE_PAGE_ROWS)
    if pages > _MAX_REFERENCE_PAGES:
        raise HTTPException(422, f"Таблица требует {pages} слайдов; предел {_MAX_REFERENCE_PAGES}. Отфильтруйте источник.")
    result = []
    if pages > 1:
        summary = dict(suggestion)
        summary.update(visual="big_number", table=None, chart=None, number=str(len(rows)),
                       headline=f"{len(rows)} строк справочника сохранены в приложении",
                       statement=f"Полный справочник: {pages} страниц в приложении после основных выводов; исходные значения сохранены.",
                       data_lines=[], coverage=f"Всего {len(rows)} строк; полный постраничный показ — в приложении.")
        summary["provenance"] = dict(summary.get("provenance") or {}, displayed_row_lines=[])
        result.append(summary)
    for page_index in range(pages):
        start = page_index * _REFERENCE_PAGE_ROWS
        end = min(len(rows), start + _REFERENCE_PAGE_ROWS)
        page = dict(suggestion)
        page_rows = rows[start:end]
        page_lines = lines[start:end]
        page_count = pages
        page["headline"] = f"{'Приложение · ' if pages > 1 else ''}Справочник · строки {start + 1}–{end} из {len(rows)}"
        page["statement"] = f"Справочная таблица: строки {start + 1}–{end} из {len(rows)}; страница {page_index + 1} из {page_count}."
        page["table"] = {"columns": headers, "rows": page_rows}
        page["coverage"] = (f"Охват: страница {page_index + 1}/{page_count}; строки источника "
                            f"{page_lines[0]}–{page_lines[-1]} из {len(rows)}; пропуски показаны как в источнике.")
        page["formula"] = f"Постраничный показ исходных строк; {len(rows)} строк всего; без агрегации."
        page["data_lines"] = [" | ".join([*headers, *row]) for row in page_rows]
        provenance = dict(page.get("provenance") or {})
        provenance.update({"displayed_row_lines": page_lines, "formula": page["formula"],
                           "missing_policy": "preserve_all_rows", "page_index": page_index + 1,
                           "page_count": page_count})
        page["provenance"] = provenance
        result.append(page)
    return result


def _bundle_plan(inputs: list[tuple[str, bytes]], goal: str) -> list[DatasetTablePlan]:
    datasets = []
    for file_index, (filename, data) in enumerate(inputs):
        try:
            tables = insights_table.read_tables(data, filename)
        except insights_table.TableError as exc:
            raise HTTPException(422, f"«{insights_table.file_name(filename)}»: {exc}") from exc
        for table_index, table in enumerate(tables):
            if len(datasets) >= _MAX_PLAN_TABLES:
                raise HTTPException(422, f"Найдено больше {_MAX_PLAN_TABLES} таблиц: разделите файлы на несколько запросов.")
            profile = profile_table(table)
            plan = plan_table(table, goal)
            dataset_id, source_sha256 = persist_source(data, filename, table_index, table)
            datasets.append(DatasetTablePlan(
                file_index=file_index, table_index=table_index,
                dataset_id=dataset_id, source_sha256=source_sha256,
                file_name=insights_table.file_name(filename), table_name=table.name, sheet=table.sheet,
                rows=len(table.rows), columns=len(table.headers), headers=table.headers,
                preview_rows=[row[:10] for row in table.rows[:5]],
                profile=_json_safe(profile), plan=_json_safe(plan),
            ))
    return datasets


@app.post("/insights/plan", response_model=DatasetBundlePlanResponse)
async def dataset_bundle_plan(files: list[UploadFile] = File(...), goal: str = Form("", max_length=2000)) -> DatasetBundlePlanResponse:
    """Profile 1–7 CSV/XLSX/JSON/TXT/Markdown files and rank deterministic slide options.

    This additive endpoint deliberately does not call an LLM or alter the existing
    single-file `/insights` workflow. XLSX sheets containing independent tables are
    exposed as separate datasets, with a bounded overall table count.
    """
    if not 1 <= len(files) <= _MAX_PLAN_FILES:
        raise HTTPException(422, f"Прикрепите от 1 до {_MAX_PLAN_FILES} файлов данных.")
    inputs, total = [], 0
    try:
        for upload in files:
            filename = upload.filename or ""
            data = await upload.read(insights_table.MAX_BYTES + 1)
            if len(data) > insights_table.MAX_BYTES:
                raise HTTPException(413, f"«{insights_table.file_name(filename)}» больше 1 МБ.")
            total += len(data)
            if total > _MAX_PLAN_TOTAL_BYTES:
                raise HTTPException(413, f"Общий размер файлов больше {_MAX_PLAN_TOTAL_BYTES // (1024 * 1024)} МБ.")
            inputs.append((filename, data))
        datasets = await run_in_threadpool(_bundle_plan, inputs, goal)
    finally:
        for upload in files:
            await upload.close()
    if not datasets:
        raise HTTPException(422, "В файлах не найдено табличных данных.")
    response = DatasetBundlePlanResponse(file_count=len(files), table_count=len(datasets), goal=goal, datasets=datasets)
    response.id = store.save_dataset_bundle(response.model_dump(mode="json"))
    return response


@app.get("/insights/plan/{bundle_id}", response_model=DatasetBundlePlanResponse)
async def get_dataset_bundle_plan(bundle_id: str) -> DatasetBundlePlanResponse:
    try:
        saved = store.load_dataset_bundle(bundle_id)
    except store.InvalidId as exc:
        raise HTTPException(422, "Некорректный идентификатор пакета данных.") from exc
    if saved is None:
        raise HTTPException(404, "Пакет данных не найден.")
    return DatasetBundlePlanResponse(**saved)


@app.post("/insights/plan/materialize", response_model=InsightsResponse)
async def materialize_plan_candidate(file: UploadFile = File(...), goal: str = Form("", max_length=2000),
                                     table_index: int = Form(0), candidate_kind: str = Form(...),
                                     required_fields: str = Form("[]")) -> InsightsResponse:
    """Convert one verified option to the existing insight contract consumed by /decks."""
    data = await file.read(insights_table.MAX_BYTES + 1)
    await file.close()
    if len(data) > insights_table.MAX_BYTES:
        raise HTTPException(413, "Файл больше 1 МБ.")
    return await run_in_threadpool(_materialize_plan_candidate, data, file.filename or "", goal,
                                  table_index, candidate_kind, required_fields)


def _materialize_plan_candidate(data: bytes, filename: str, goal: str, table_index: int,
                                candidate_kind: str, required_fields: str) -> InsightsResponse:
    try:
        if table_index < 0:
            raise ValueError("Номер таблицы не может быть отрицательным.")
        tables = insights_table.read_tables(data, filename)
        fields = json.loads(required_fields)
        if not isinstance(fields, list) or not all(isinstance(field, str) for field in fields):
            raise ValueError("Список полей должен быть массивом строк.")
        table = tables[table_index]
        plan = plan_table(table, goal)
        candidate = next(c for c in plan.candidates if c.kind == candidate_kind and list(c.required_fields) == fields)
    except (insights_table.TableError, ValueError, IndexError, StopIteration, json.JSONDecodeError) as exc:
        raise HTTPException(422, f"Выбранный вариант больше не доступен: {exc}") from exc
    if not candidate.renderable or candidate.kind not in {"line", "bar", "column", "pie", "histogram", "table", "kpi", "scatter", "grouped_column", "stacked_column"}:
        raise HTTPException(422, "Этот тип пока нельзя передать в рендерер слайда.")

    row_map = dict(zip(table.lines, table.rows))
    source_rows = [row_map[line] for line in candidate.row_lines if line in row_map]
    positions = {header: index for index, header in enumerate(table.headers)}
    visual, chart, table_spec = "big_number", None, None
    warnings = " ".join(candidate.warnings)
    measure_label, measure_unit = field_label(candidate.measure_fields[0]) if candidate.measure_fields else ("", "")
    # Only a literal unit declaration can supply a missing unit. Surrounding
    # prose remains on the source line, including the original period wording.
    if not measure_unit and any("units:" in line.casefold() and "counts" in line.casefold().split()
                                for line in table.context):
        measure_unit = "шт."
    dimension_label = field_label(candidate.dimension_fields[0])[0] if candidate.dimension_fields else ""
    if candidate.kind == "histogram":
        metric = candidate.measure_fields[0]
        exact_values = [insights_table.parse_number(row[positions[metric]]) for row in source_rows]
        if not exact_values or any(value is None for value in exact_values):
            raise HTTPException(422, "Для распределения нужны полные числовые наблюдения.")
        values = sorted(exact_values)
        assert all(value is not None for value in values)
        numeric_values = [value for value in values if value is not None]
        if any(not chart_number_supported(value) for value in numeric_values):
            raise HTTPException(422, "Точность значений не поддерживается диаграммой; выберите таблицу.")
        count = len(numeric_values)

        def quantile(fraction: Decimal) -> Decimal:
            position = Decimal(count - 1) * fraction
            lower = int(position)
            upper = min(lower + 1, count - 1)
            part = position - lower
            return numeric_values[lower] + (numeric_values[upper] - numeric_values[lower]) * part

        minimum, maximum = numeric_values[0], numeric_values[-1]
        span = maximum - minimum
        span_float = float(span)
        if not math.isfinite(span_float):
            raise HTTPException(422, "Диапазон данных слишком велик для шкалы диаграммы; выберите таблицу.")
        iqr = quantile(Decimal("0.75")) - quantile(Decimal("0.25"))
        iqr_float = float(iqr)
        if not math.isfinite(iqr_float):
            raise HTTPException(422, "Разброс данных слишком велик для шкалы диаграммы; выберите таблицу.")
        width = 2.0 * iqr_float / math.pow(count, 1 / 3) if iqr > 0 else 0
        bins = math.ceil(span_float / width) if width > 0 else math.ceil(math.log2(count) + 1)
        # Retain outliers without allowing FD to create unreadable narrow bins.
        bins = min(8, math.ceil(math.sqrt(count)), max(1, bins))
        counts = [0] * bins
        for value in numeric_values:
            index = min(bins - 1, int((value - minimum) * bins / span))
            counts[index] += 1
        edges = [minimum + span * index / bins for index in range(bins + 1)]
        edge_labels = [format(float(edge), ".4g") for edge in edges]
        if len(set(edge_labels)) != len(edge_labels):
            edge_labels = [format(edge.normalize(), "f") for edge in edges]
        categories = []
        for index in range(bins):
            low_text, high_text = edge_labels[index:index + 2]
            categories.append(f"[{low_text}–{high_text}" + ("]" if index == bins - 1 else ")"))
        visual = "column"
        chart = ChartSpec(type="column", title=f"Распределение · {measure_label}" + (f", {measure_unit}" if measure_unit else ""),
                          unit="наблюдений", categories=categories,
                          x_axis_title=measure_label + (f", {measure_unit}" if measure_unit else ""),
                          y_axis_title="Число наблюдений",
                          series=[Series(name="Число наблюдений", values=[float(value) for value in counts])])
        statement = f"Распределение {metric}: частота по {bins} интервалам; учтены все {count} значений."
        number = str(count)
        rule = "Freedman–Diaconis" if iqr > 0 else "Sturges (IQR = 0)"
        formula = f"{rule}, ограничение читаемости min(8, ceil(sqrt(n))); {bins} равных интервалов; подписи границ до 4 значащих цифр, при совпадении — полная точность; сумма частот = {sum(counts)}; n = {count}."
    elif candidate.kind in {"scatter", "grouped_column", "stacked_column"}:
        numeric = {}
        for field in candidate.measure_fields:
            exact = [insights_table.parse_number(row[positions[field]]) for row in source_rows]
            if not exact or any(v is None or not chart_number_supported(v) for v in exact):
                raise HTTPException(422, "Точность значений не поддерживается диаграммой; выберите таблицу.")
            numeric[field] = [float(v) for v in exact]
        visual = candidate.kind
        if visual == "scatter":
            x_field, y_field = candidate.measure_fields
            x_label, x_unit = field_label(x_field)
            y_label, measure_unit = field_label(y_field)
            chart = ChartSpec(type=visual, title=f"{y_label} · {x_label}", unit=measure_unit,
                              x_axis_title=x_label + (f", {x_unit}" if x_unit else ""),
                              y_axis_title=y_label + (f", {measure_unit}" if measure_unit else ""),
                              series=[Series(name=y_label, x_values=numeric[x_field], values=numeric[y_field])])
            statement = f"{y_field} и {x_field}: {len(source_rows)} полных пар; связь не доказывает причинность."
            formula = f"X = {x_field}; Y = {y_field}; исходные пары без агрегации; корреляция не вычислялась."
        else:
            dimension = candidate.dimension_fields[0]
            chart = ChartSpec(type=visual, title=f"{' · '.join(field_label(f)[0] for f in candidate.measure_fields)} · {dimension_label}",
                              categories=[row[positions[dimension]] for row in source_rows], unit=measure_unit,
                              x_axis_title=dimension_label,
                              y_axis_title=" · ".join(field_label(f)[0] for f in candidate.measure_fields) + (f", {measure_unit}" if measure_unit else ""),
                              series=[Series(name=field_label(f)[0], values=numeric[f]) for f in candidate.measure_fields])
            statement = f"{' и '.join(candidate.measure_fields)} по полю «{dimension}»; исходные значения полных строк."
            formula = ("Накопление исходных компонентов в каждой категории; без нормирования; аддитивность задана автором."
                       if visual == "stacked_column" else "Сопоставление рядов внутри каждой категории; значения не суммировались.")
        number = str(len(source_rows))
    elif candidate.kind in {"line", "bar", "column", "pie"}:
        dimension, measure = candidate.dimension_fields[0], candidate.measure_fields[0]
        categories = [row[positions[dimension]] for row in source_rows]
        exact_values = [insights_table.parse_number(row[positions[measure]]) for row in source_rows]
        if not categories or any(value is None for value in exact_values):
            raise HTTPException(422, "В выбранных исходных строках есть пропуски или нечисловые значения.")
        if any(not chart_number_supported(value) for value in exact_values):
            raise HTTPException(422, "Точность значений не поддерживается диаграммой; выберите таблицу.")
        values = [float(value) for value in exact_values]
        if any(not math.isfinite(value) for value in values):
            raise HTTPException(422, "Значения слишком велики для диаграммы; используйте таблицу.")
        visual = candidate.kind
        chart = ChartSpec(type=visual, title=f"{measure_label} · {dimension_label}", categories=categories,
                          x_axis_title=(measure_label + (f", {measure_unit}" if measure_unit else "")) if visual == "bar" else dimension_label,
                          y_axis_title=dimension_label if visual == "bar" else measure_label + (f", {measure_unit}" if measure_unit else ""),
                          unit=measure_unit, series=[Series(name=measure_label, values=values)])
        statement = f"{measure} по полю «{dimension}»; показаны исходные значения без группировки."
        number = format(candidate.denominator, "f") if candidate.denominator is not None else str(len(categories))
        formula = (f"Сумма показанных долей: {candidate.denominator}; охват — {len(categories)} наблюдений."
                   if candidate.denominator is not None else f"{len(categories)} исходных наблюдений; агрегация не выполнялась.")
    elif candidate.kind == "table":
        # The native slide table has a hard seven-row limit. Keep the preview
        # readable and state the omitted-row count; the complete file and its
        # provenance remain retained separately, never squeezed onto one slide.
        preview = source_rows[:7]
        table_spec = TableSpec(columns=table.headers, rows=preview)
        visual = "table"
        statement = f"Справочные данные: {len(table.rows)} строк; показаны первые {len(preview)} из {len(table.rows)}."
        number, formula = str(len(table.rows)), "Количество строк источника; значения не агрегировались."
        if len(table.rows) > len(preview):
            warnings = (warnings + " " if warnings else "") + f"Слайд показывает только первую страницу; ещё {len(table.rows) - len(preview)} строк сохранены в источнике и на этот слайд не помещены."
    else:
        number = format(candidate.value or Decimal(0), "f")
        statement = f"Количество исходных записей: {number}."
        formula = "Число строк источника, включая записи с пропусками; суммы мер не вычислялись."

    if candidate.statement:
        statement = candidate.statement
        number = candidate.number
        formula = candidate.formula + (" " + formula if candidate.kind in {"histogram", "grouped_column"} else "")

    source = insights_table.file_name(filename or "таблица")
    if table.sheet:
        source += f" · лист «{table.sheet}»"
    if table.context:
        source += " · " + " · ".join(table.context)
    source += f" · {len(candidate.row_lines)} исходных строк"
    displayed_lines = list(candidate.row_lines[:7] if candidate.kind == "table" else candidate.row_lines)
    coverage = f"Охват: {len(candidate.row_lines)} из {len(table.rows)} строк; исключено: {len(candidate.excluded_row_lines)}."
    if candidate.kind == "table":
        coverage += f" На слайде: {len(displayed_lines)}; не показано: {len(candidate.row_lines) - len(displayed_lines)}."
    dataset_id, source_sha256 = persist_source(data, filename, table_index, table)
    provenance = DataProvenance(
        dataset_id=dataset_id, source_sha256=source_sha256, content_hash=plan.content_hash,
        file_name=insights_table.file_name(filename), sheet=table.sheet, table_index=table_index,
        columns=list(candidate.required_fields), total_rows=len(table.rows),
        row_lines=list(candidate.row_lines), excluded_row_lines=list(candidate.excluded_row_lines),
        displayed_row_lines=displayed_lines, visualization=candidate.kind, aggregation=candidate.aggregation,
        missing_policy="preserve_all_rows" if candidate.kind in {"table", "kpi"} else "exclude_incomplete_selected_fields",
        formula=formula, denominator=format(candidate.denominator, "f") if candidate.denominator is not None else None,
        unit=measure_unit,
        denominator_field=candidate.denominator_field, warnings=list(candidate.warnings),
    )
    headline = candidate.headline or (f"Распределение: {measure_label}" if candidate.kind == "histogram" else
                f"{measure_label}: динамика" if candidate.kind == "line" else
                f"{measure_label} · {dimension_label}"
                if candidate.measure_fields and candidate.dimension_fields else statement)
    suggestion = insights_suggest.Suggestion(
        id="s1", headline=headline, number=number, visual=visual, why=candidate.reason,
        fact_ids=[f"{plan.content_hash[:16]}:{candidate.kind}:{','.join(candidate.required_fields)}"],
        statement=statement, topic=candidate.measure_fields[0] if candidate.measure_fields else table.name,
        source=source, formula=formula, chart=chart, table=table_spec,
        provenance=provenance, coverage=coverage,
        data_lines=[" | ".join([*table.headers, *row]) for row in source_rows], by_model=False,
    )
    suggestion.number_at = insights_suggest.number_span(suggestion.headline, suggestion.number)
    stored = {"table_name": table.name, "rows": len(table.rows), "columns": len(table.headers),
              "dataset_id": dataset_id, "analytical_plan": _json_safe(plan), "selected_candidate": _json_safe(candidate),
              "suggestions": [suggestion.model_dump(mode="json")], "note": warnings, "from_image": False}
    insights_id = store.save_insights(stored)
    return InsightsResponse(id=insights_id, table_name=table.name, sheet=table.sheet, rows=len(table.rows),
                            columns=len(table.headers), suggestions=[InsightView(**suggestion.model_dump())],
                            note=warnings, from_image=False)


@app.post("/insights/plan/materialize-bundle", response_model=InsightsResponse)
async def materialize_plan_bundle(bundle_id: str = Form(...), selections: str = Form(..., max_length=30000)) -> InsightsResponse:
    """Revalidate chosen tables against durable original bytes, then build one deck input."""
    try:
        bundle = store.load_dataset_bundle(bundle_id)
        choices = json.loads(selections)
        if not isinstance(choices, list) or not 1 <= len(choices) <= _MAX_PLAN_TABLES:
            raise ValueError("Выберите от 1 до 21 варианта.")
        if bundle is None:
            raise HTTPException(404, "Пакет данных не найден.")
        by_id = {item["dataset_id"]: item for item in bundle["datasets"]}
        validated = []
        seen = set()
        for choice in choices:
            if not isinstance(choice, dict):
                raise ValueError("Некорректный выбор варианта.")
            dataset_id = choice["dataset_id"]
            if dataset_id not in by_id or dataset_id in seen:
                raise ValueError("Таблица отсутствует в пакете или выбрана повторно.")
            seen.add(dataset_id)
            snapshot = store.load_dataset(dataset_id)
            if snapshot is None:
                raise ValueError("Исходные данные таблицы не найдены.")
            raw = base64.b64decode(snapshot["source_base64"], validate=True)
            import hashlib
            if hashlib.sha256(raw).hexdigest() != by_id[dataset_id]["source_sha256"]:
                raise ValueError("Контрольная сумма исходного файла не совпадает.")
            validated.append((dataset_id, raw, snapshot["file_name"], bundle["goal"], snapshot["table_index"],
                              choice["candidate_kind"], json.dumps(choice["required_fields"])))
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(422, f"Пакет не может быть использован: {exc}") from exc
    results = []
    suggestions = []
    for dataset_id, *args in validated:
        result = await run_in_threadpool(_materialize_plan_candidate, *args)
        item = store.load_insights(result.id)
        results.append(item)
        suggestions.extend(_reference_pages(dict(item["suggestions"][0]), store.load_dataset(dataset_id)))
        if len(suggestions) > _MAX_BUNDLE_SLIDES:
            raise HTTPException(422, f"Выбор создаёт больше {_MAX_BUNDLE_SLIDES} слайдов; уменьшите число таблиц или объём справочника.")
    for index, suggestion in enumerate(suggestions, start=1):
        suggestion["id"] = f"s{index}"
    combined = {"bundle_id": bundle_id, "table_name": "Пакет данных", "rows": sum(item["rows"] for item in results),
                "columns": sum(item["columns"] for item in results), "suggestions": suggestions,
                "analyses": [{key: item[key] for key in ("dataset_id", "analytical_plan", "selected_candidate")} for item in results],
                "note": " ".join(item["note"] for item in results if item["note"]), "from_image": False}
    insights_id = store.save_insights(combined)
    return InsightsResponse(id=insights_id, **{key: combined[key] for key in
                            ("table_name", "rows", "columns", "suggestions", "note", "from_image")})


async def _wait_unless_gone(task: asyncio.Future, request: Request, client: object, poll_s: float = 0.5) -> bool:
    """Ждёт подсказки. Браузер оборвал запрос («Остановить», пересчёт под новый бриф): рвёт вызов модели.

    Иначе модель дописывала ответ, который никто не прочтёт, и слот локальной модели был занят
    до таймаута (ред-тим 17.10, инженер ядра). False, если клиент ушёл.
    """
    while True:
        done, _ = await asyncio.wait({task}, timeout=poll_s)
        if done:
            return True
        if await request.is_disconnected():
            _close(client)
            task.add_done_callback(lambda t: t.cancelled() or t.exception())
            return False


def _insights_work(data: bytes, filename: str, brief: str, audience: str, client: LlmClient | None):
    table, facts = insights_source.load(data, filename, client)
    suggestions, note = insights_suggest.suggest(table, facts, brief, audience, client)
    return table, suggestions, note


@app.post("/insights", response_model=InsightsResponse)
async def table_insights(request: Request, file: UploadFile = File(...), brief: str = Form(""), audience: str = Form(""),
                         use_model: bool = Form(True),
                         client: LlmClient = Depends(get_llm_client)) -> InsightsResponse | Response:
    """Таблица автора -> подсказки, что из неё показать. Числа считает код, модель выбирает и формулирует.

    use_model=false: автор остановил долгий ответ модели, подсказки сразу формулирует код. Таблицу на
    картинке без модели можно взять только из кэша прочитанных картинок.
    """
    data = await file.read(insights_table.MAX_IMAGE_BYTES + 1)
    try:
        task = asyncio.ensure_future(run_in_threadpool(_insights_work, data, file.filename or "", brief, audience,
                                                       client if use_model else None))
        if not await _wait_unless_gone(task, request, client):
            return Response(status_code=499)
        table, suggestions, note = task.result()
        if not use_model:
            note = "Модель остановлена: выводы посчитаны и записаны без неё."
    except insights_table.TableError as exc:
        raise HTTPException(422, str(exc)) from exc
    except (LlmResponseError, ModelLoading, httpx.HTTPError) as exc:
        # Таблицу с картинки читает модель: без неё подсказок нет, файл при этом годный.
        raise HTTPException(503, f"Таблица на картинке: прочитать её может только модель, а она не ответила ({exc}).") from exc
    finally:
        _close(client)
    result = {"table_name": table.name, "sheet": table.sheet, "rows": len(table.rows), "columns": len(table.headers),
              "suggestions": [s.model_dump(mode="json") for s in suggestions], "note": note,
              "from_image": table.from_image}
    insights_id = store.save_insights(result)
    return InsightsResponse(id=insights_id, table_name=table.name, sheet=table.sheet, rows=len(table.rows), columns=len(table.headers),
                            suggestions=[InsightView(**s.model_dump(include=set(InsightView.model_fields)))
                                         for s in suggestions], note=note, from_image=table.from_image)


@app.post("/decks", response_model=DeckCreateResponse)
def create_deck(payload: DeckCreateRequest, background_tasks: BackgroundTasks,
                 client: LlmClient = Depends(get_llm_client)) -> DeckCreateResponse:
    deck_id = store.new_deck_id()
    variant_codes = payload.variants or ["a"]
    insights: list[insights_suggest.Suggestion] = []
    table_name = ""
    if payload.insights_id and payload.insight_ids:
        try:
            saved = store.load_insights(payload.insights_id)
        except store.InvalidId:
            saved = None
        if saved is None:
            _close(client)
            raise HTTPException(404, "Подсказки по таблице не найдены: загрузите таблицу заново")
        chosen = {item["id"]: item for item in saved["suggestions"]}
        insights = [insights_suggest.Suggestion(**chosen[i]) for i in payload.insight_ids if i in chosen]
        table_name = saved.get("table_name", "")

    def _on_event(event: pipeline.PipelineEvent) -> None:
        store.append_event(deck_id, {"step": event.step, "slide_index": event.slide_index,
                                      "variant": event.variant, "at": event.at})

    def _run() -> None:
        try:
            pipeline.generate_deck(
                payload.design_system_id, payload.brief, payload.purpose, payload.audience,
                payload.slide_count, _on_event, deck_id=deck_id, client=client,
                variants=variant_codes, insights=insights, table_name=table_name,
            )
        except Exception:
            pass  # состояние ошибки уже записано pipeline.generate_deck в store.mark_deck_failed
        finally:
            _close(client)

    # Persist the pending job before returning its identifier. A fast client can
    # otherwise poll before the background worker reaches generate_deck/init_deck.
    store.init_deck(deck_id, payload.design_system_id, variant_codes, brief=payload.brief)
    background_tasks.add_task(_run)
    return DeckCreateResponse(deck_id=deck_id)


@app.get("/decks/{deck_id}/events")
def deck_events(deck_id: str) -> StreamingResponse:
    events = store.read_events(deck_id)

    def _stream() -> Iterator[str]:
        for event in events:
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")


@app.get("/decks/{deck_id}", response_model=DeckStateResponse)
def get_deck(deck_id: str) -> DeckStateResponse:
    try:
        variant_codes = store.deck_variants(deck_id)
    except store.InvalidId:
        raise _not_found()
    if not variant_codes:
        raise _not_found()

    variant_states = {code: _variant_state(deck_id, code) for code in variant_codes}
    primary = variant_states.get("a") or next(iter(variant_states.values()))
    return DeckStateResponse(
        status=primary.status, design_system_id=primary.design_system_id, plan=primary.plan,
        specs=primary.specs, scenes=primary.scenes, findings=primary.findings, error=primary.error,
        slide_images=primary.slide_images, brief=primary.brief, variants=variant_states,
    )


def _variant_state(deck_id: str, variant: str) -> DeckVariantState:
    """Состояние варианта с адресами картинок слайдов: их пишет конвейер после экспорта pptx."""
    state = DeckVariantState(**store.load_deck_state(deck_id, variant))
    # После починки картинка перерисована по тому же адресу: метка времени файла в адресе
    # не даёт браузеру показать прежнюю из кэша.
    def _stamp(number: int) -> int:
        path = store.deck_variant_slide_path(deck_id, variant, number)
        return int(path.stat().st_mtime) if path is not None else 0

    state.slide_images = [f"/decks/{deck_id}/{variant}/slides/{number}.png?v={_stamp(number)}"
                           for number in store.deck_variant_slide_numbers(deck_id, variant)]
    marker = store.deck_variant_files_dir(deck_id, variant) / "export-revision.json"
    if marker.is_file():
        exported = store.read_json_file(marker)
        if exported.get("images", True):
            state.images_revision = exported.get("revision")
    return state


@app.get("/decks/{deck_id}/run", response_model=RunManifest)
def get_deck_run(deck_id: str) -> RunManifest:
    manifest = store.load_run(deck_id)
    if manifest is None:
        raise HTTPException(404, "карточка прогона ещё не готова")
    return manifest


@app.get("/decks/{deck_id}/files/{name}")
def get_deck_file(deck_id: str, name: str) -> FileResponse:
    path = store.deck_file_path(deck_id, name)
    if path is None:
        raise HTTPException(400, "недопустимое имя файла")
    ensure_export(deck_id, "a")
    if not path.is_file():
        raise HTTPException(404, "файл не найден")
    return FileResponse(str(path), filename=path.name)


@app.get("/decks/{deck_id}/{variant}/files/{name}")
def get_deck_variant_file(deck_id: str, variant: str, name: str) -> FileResponse:
    try:
        path = store.deck_variant_file_path(deck_id, variant, name)
    except store.InvalidId:
        raise HTTPException(400, "недопустимое имя файла")
    if path is None:
        raise HTTPException(400, "недопустимое имя файла")
    try:
        ensure_export(deck_id, variant)
    except Exception as exc:
        raise HTTPException(503, "Не удалось подготовить актуальный экспорт. Повторите скачивание.") from exc
    if not path.is_file():
        raise HTTPException(404, "файл не найден")
    return FileResponse(str(path), filename=path.name)


@app.get("/decks/{deck_id}/{variant}/slides/{number}/live", response_class=HTMLResponse)
def get_live_slide(deck_id: str, variant: str, number: int):
    try:
        return HTMLResponse(edit.live_slide(deck_id, variant, number), headers={"Cache-Control": "no-store"})
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/decks/{deck_id}/{variant}/slides/{number}.png")
def get_deck_slide_image(deck_id: str, variant: str, number: str) -> FileResponse:
    """Картинка слайда: ровно то, что откроется в PowerPoint."""
    try:
        path = store.deck_variant_slide_path(deck_id, variant, number)
    except store.InvalidId:
        raise HTTPException(400, "недопустимый путь")
    if path is None:
        raise HTTPException(400, "недопустимый путь")
    if not path.is_file():
        raise HTTPException(404, "картинка слайда не найдена")
    return FileResponse(str(path), media_type="image/png")


@app.post("/decks/{deck_id}/{variant}/audit-contextual", response_model=AuditContextualResponse)
def audit_deck_variant(deck_id: str, variant: str,
                        client: LlmClient = Depends(get_llm_client)) -> AuditContextualResponse:
    try:
        new_findings = pipeline.run_contextual_audit(deck_id, variant, client=client)
    except ValueError:
        raise HTTPException(404, "колода не найдена")
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))
    finally:
        _close(client)
    return AuditContextualResponse(findings=new_findings)


@app.post("/decks/{deck_id}/{variant}/fix", response_model=DeckFixResponse)
def fix_deck_variant(deck_id: str, variant: str, payload: DeckFixRequest) -> DeckFixResponse:
    try:
        report, findings = pipeline.apply_fixes(deck_id, variant, payload.finding_ids)
    except ValueError:
        raise HTTPException(404, "колода не найдена")
    return DeckFixResponse(report=report, findings=findings)


# ---------- правка варианта: текст, образец, лента слайдов, агент, история ----------

_EDIT_NOT_FOUND = (edit.DeckNotFound, edit.SlideNotFound, edit.ElementNotFound,
                    edit.PatternNotFound, edit.FindingNotFound)


def _edit_error(exc: Exception) -> HTTPException:
    if isinstance(exc, _EDIT_NOT_FOUND):
        return HTTPException(404, str(exc))
    if isinstance(exc, edit.NoHistory):
        return HTTPException(409, str(exc))
    return HTTPException(400, str(exc))


@app.patch("/decks/{deck_id}/{variant}/slides/{number}/text", response_model=DeckVariantState)
def patch_slide_text(deck_id: str, variant: str, number: int, payload: SlideTextRequest) -> DeckVariantState:
    try:
        edit.set_slide_text(deck_id, variant, number, payload.element_id, payload.text)
    except (*_EDIT_NOT_FOUND, edit.NoHistory, ValueError) as exc:
        raise _edit_error(exc)
    return _variant_state(deck_id, variant)


@app.patch("/decks/{deck_id}/{variant}/slides/{number}/position", response_model=DeckVariantState)
def patch_element_position(deck_id: str, variant: str, number: int, payload: SlideMoveElementRequest) -> DeckVariantState:
    try:
        edit.move_element(deck_id, variant, number, payload.element_id, payload.dx, payload.dy, payload.align)
    except (*_EDIT_NOT_FOUND, edit.NoHistory, ValueError) as exc:
        raise _edit_error(exc)
    return _variant_state(deck_id, variant)


@app.post("/decks/{deck_id}/{variant}/slides/{number}/elements", response_model=DeckVariantState)
def post_element_action(deck_id: str, variant: str, number: int, payload: ElementActionRequest):
    try:
        edit.element_action(deck_id, variant, number, **payload.model_dump(exclude_unset=True))
    except _EDIT_NOT_FOUND as exc:
        raise _edit_error(exc)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _variant_state(deck_id, variant)


@app.post("/decks/{deck_id}/{variant}/slides/{number}/pattern", response_model=DeckVariantState)
def post_slide_pattern(deck_id: str, variant: str, number: int, payload: SlidePatternRequest) -> DeckVariantState:
    try:
        edit.set_slide_pattern(deck_id, variant, number, payload.pattern_id)
    except (*_EDIT_NOT_FOUND, edit.NoHistory, ValueError) as exc:
        raise _edit_error(exc)
    return _variant_state(deck_id, variant)


@app.get("/decks/{deck_id}/{variant}/slides/{number}/patterns", response_model=SlidePatternsResponse)
def get_slide_patterns(deck_id: str, variant: str, number: int) -> SlidePatternsResponse:
    try:
        items = edit.list_slide_patterns(deck_id, variant, number)
    except (*_EDIT_NOT_FOUND, edit.NoHistory, ValueError) as exc:
        raise _edit_error(exc)
    return SlidePatternsResponse(items=items)


@app.post("/decks/{deck_id}/{variant}/slides/{number}/ask", response_model=DeckVariantState)
def post_slide_ask(deck_id: str, variant: str, number: int, payload: SlideAskRequest) -> DeckVariantState:
    try:
        edit.ask_agent_rewrite(deck_id, variant, number, payload.instruction)
    except (*_EDIT_NOT_FOUND, edit.NoHistory, ValueError) as exc:
        raise _edit_error(exc)
    return _variant_state(deck_id, variant)


@app.post("/decks/{deck_id}/{variant}/slides", response_model=DeckVariantState)
def post_slide_action(deck_id: str, variant: str, payload: SlideActionRequest) -> DeckVariantState:
    try:
        with lock(deck_id, variant):
            if payload.expected_revision is not None or payload.target_slide_id is not None:
                current = store.load_deck_state(deck_id, variant)
                if (payload.expected_revision is not None
                        and (current.get('revision') or '') != payload.expected_revision):
                    raise HTTPException(409, 'Документ уже изменён. Подтвердите действие заново.')
                if payload.target_slide_id is not None:
                    scenes = current.get('scenes', [])
                    if (not 1 <= payload.index <= len(scenes)
                            or scenes[payload.index - 1].get('slide_id') != payload.target_slide_id):
                        raise HTTPException(409, 'Выбранный слайд уже изменился. Подтвердите действие заново.')
            edit.apply_slide_action(deck_id, variant, payload.action, payload.index, payload.to)
            return _variant_state(deck_id, variant)
    except (*_EDIT_NOT_FOUND, edit.NoHistory, ValueError) as exc:
        raise _edit_error(exc)


@app.patch("/decks/{deck_id}/{variant}/notes/{number}", response_model=DeckVariantState)
def patch_slide_notes(deck_id: str, variant: str, number: int, payload: SlideNotesRequest) -> DeckVariantState:
    try:
        edit.set_slide_notes(deck_id, variant, number, payload.notes)
    except (*_EDIT_NOT_FOUND, edit.NoHistory, ValueError) as exc:
        raise _edit_error(exc)
    return _variant_state(deck_id, variant)


@app.post("/decks/{deck_id}/cancel", status_code=202)
def post_deck_cancel(deck_id: str) -> dict:
    try:
        store.request_deck_cancel(deck_id)
    except (store.InvalidId, FileNotFoundError):
        raise _not_found()
    return {"status": "cancelling"}


@app.patch("/decks/{deck_id}/title")
def patch_deck_title(deck_id: str, payload: dict) -> dict:
    title = str(payload.get("title", "")).strip()
    if not title:
        raise HTTPException(400, "пустое название")
    try:
        store.rename_deck(deck_id, title)
    except (store.InvalidId, FileNotFoundError):
        raise _not_found()
    return {"title": title}


@app.post("/decks/{deck_id}/{variant}/revert", response_model=DeckVariantState)
def post_revert(deck_id: str, variant: str) -> DeckVariantState:
    try:
        edit.revert(deck_id, variant)
    except (*_EDIT_NOT_FOUND, edit.NoHistory, ValueError) as exc:
        raise _edit_error(exc)
    return _variant_state(deck_id, variant)


@app.post("/decks/{deck_id}/{variant}/recover", response_model=DeckVariantState)
def recover_voice_editor(deck_id: str, variant: str):
    try:
        edit.recover_editor(deck_id, variant)
    except (*_EDIT_NOT_FOUND, ValueError) as exc:
        raise _edit_error(exc)
    return _variant_state(deck_id, variant)


@app.post("/decks/{deck_id}/{variant}/rewrite", response_model=DeckVariantState)
def post_rewrite(deck_id: str, variant: str, payload: DeckRewriteRequest) -> DeckVariantState:
    try:
        edit.rewrite_from_finding(deck_id, variant, payload.finding_id)
    except (*_EDIT_NOT_FOUND, edit.NoHistory, ValueError) as exc:
        raise _edit_error(exc)
    return _variant_state(deck_id, variant)


# ---------- агенты и настройки (поток 2 наполняет designer.agents, здесь только вызов) ----------

@app.get("/agents")
def get_agents() -> dict:
    return agent_list()


@app.post("/agents/{agent_id}/check")
def post_agent_check(agent_id: str) -> dict:
    try:
        return agent_check(agent_id)
    except AgentCheckUnavailable:
        raise HTTPException(503, "мост агентов не запущен")


@app.get("/settings/agents")
def get_agent_settings() -> dict:
    return agent_load_assignments()


@app.put("/settings/agents")
def put_agent_settings(payload: AgentAssignmentsRequest) -> dict:
    return agent_save_assignments(payload.model_dump(exclude_none=True))


@app.get("/settings/models")
def get_model_settings() -> dict:
    return load_model_settings()


@app.put("/settings/models")
def put_model_settings(payload: ModelSettingsRequest) -> dict:
    try:
        return save_model_settings(payload.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


# ---------- живой режим ----------

@app.post("/live/slide")
def live_slide(payload: LiveSlideRequest, client: LlmClient = Depends(get_live_llm_client)):
    try:
        with _live_call() as busy:
            result = pipeline.live_slide(
                payload.design_system_id, payload.chunk_text, payload.used_pattern_ids, client=client,
            )
    except LookupError as exc:
        raise HTTPException(409, str(exc))
    except (store.InvalidId, FileNotFoundError):
        raise HTTPException(404, "дизайн-система не найдена")
    except ModelLoading as exc:
        print(f"живой слайд: {exc}", flush=True)
        raise HTTPException(503, "модель загружается в LM Studio: слайды появятся, когда она будет готова")
    finally:
        _close(client)
    if result is None:
        return Response(status_code=204)

    timings = {**result.timings, "busy": busy}
    print(f"живой слайд: модель {timings.get('model_ms')} мс, картинка {timings.get('image_ms')} мс, "
          f"всего {timings.get('total_ms')} мс, запросов Live к модели одновременно {busy}", flush=True)
    image = base64.b64encode(result.png).decode("ascii") if result.png else None
    return LiveSlideResponse(scene=result.scene, html=result.html, image_png_base64=image, timings=timings)


@app.post("/live/draft", response_model=LiveSlideResponse)
def live_draft(payload: LiveSlideRequest) -> LiveSlideResponse:
    """Черновик слайда сразу после фразы, без модели: слайд от /live/slide приходит следом и заменяет его."""
    try:
        result = pipeline.live_draft(payload.design_system_id, payload.chunk_text)
    except LookupError as exc:
        raise HTTPException(409, str(exc))
    except (store.InvalidId, FileNotFoundError):
        raise HTTPException(404, "дизайн-система не найдена")
    return LiveSlideResponse(scene=result.scene, html=result.html, image_png_base64=None)


@app.post("/live/warm", status_code=202)
def live_warm(payload: LiveWarmRequest, background_tasks: BackgroundTasks) -> dict:
    """Фон черновика готовится заранее, при выборе дизайн-системы в Live."""
    def _warm() -> None:
        try:
            pipeline.live_warm(payload.design_system_id)
        except Exception as exc:  # noqa: BLE001 - прогрев не должен ронять сервис
            print(f"прогрев черновика: {exc}", flush=True)
    background_tasks.add_task(_warm)
    return {"ok": True}


@app.post("/live/boundary", response_model=LiveBoundaryResponse)
def live_boundary(payload: LiveBoundaryRequest, client: LlmClient = Depends(get_live_llm_client)):
    """Начинает ли следующее предложение новую мысль: так Live делит речь на слайды."""
    started = time.monotonic()
    try:
        with _live_call() as busy:
            new_thought = speech_boundary(payload.thought, payload.next_sentence, client)
    except ModelLoading as exc:
        print(f"граница мысли: {exc}", flush=True)
        raise HTTPException(503, "модель загружается в LM Studio")
    finally:
        _close(client)
    timings = {"total_ms": int((time.monotonic() - started) * 1000), "busy": busy}
    print(f"граница мысли: {timings['total_ms']} мс, запросов Live к модели одновременно {busy}", flush=True)
    return LiveBoundaryResponse(new_thought=new_thought, timings=timings)


# ---------- здоровье ----------

@app.get("/health", response_model=HealthResponse)
def health(client: LlmClient = Depends(get_llm_client)) -> HealthResponse:
    try:
        model_ok = _model_available(client.base_url)
    finally:
        _close(client)
    return HealthResponse(model_ok=model_ok, converters=convert.available(), skills=_skill_refs())


def _model_available(base_url: str) -> bool:
    try:
        with httpx.Client(timeout=3.0, headers=auth_headers(base_url)) as probe:
            response = probe.get(f"{base_url}/models")
        return response.status_code < 500
    except httpx.HTTPError:
        return False


def _skill_refs() -> list:
    refs = []
    for name in _HEALTH_SKILLS:
        try:
            refs.append(load_skill(name).ref())
        except SkillError:
            continue
    return refs
