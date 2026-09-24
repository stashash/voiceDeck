"""FastAPI-сервис: пакеты дизайн-систем, генерация колоды, живой режим. Владелец: задача T-13, варианты — T-12."""
from __future__ import annotations

import base64
import json
import os
from collections.abc import Iterator

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from designer import edit, pipeline, store
from designer.agent_hook import AgentCheckUnavailable, _client_for
from designer.agent_hook import check_agent as agent_check
from designer.agent_hook import list_agents as agent_list
from designer.agent_hook import load_assignments as agent_load_assignments
from designer.agent_hook import save_assignments as agent_save_assignments
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
    DesignSystemListResponse,
    DesignSystemPatchRequest,
    HealthResponse,
    LiveSlideRequest,
    LiveSlideResponse,
    SlideActionRequest,
    SlideAskRequest,
    SlideNotesRequest,
    SlidePatternRequest,
    SlidePatternsResponse,
    SlideTextRequest,
)
from designer.contracts import DesignSystem, RunManifest
from designer.export import convert
from designer.llm.client import LlmClient, ModelLoading
from designer.llm.skills import SkillError, load_skill
from designer.parse.package import load_package

_ORIGINS_ENV = "DESIGNER_ALLOWED_ORIGINS"
_HEALTH_SKILLS = ("plan-deck", "fill-slots", "speech-to-slide", "audit-slide", "audit-deck")

app = FastAPI(title="Цифровой дизайнер презентаций")

_origins = [origin.strip() for origin in os.environ.get(_ORIGINS_ENV, "").split(",") if origin.strip()]
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


def _not_found(ds_id_error: bool = False):
    return HTTPException(404, "дизайн-система не найдена" if ds_id_error else "не найдено")


# ---------- дизайн-системы ----------

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
    return DeckListResponse(items=pipeline.list_decks())


@app.post("/decks", response_model=DeckCreateResponse)
def create_deck(payload: DeckCreateRequest, background_tasks: BackgroundTasks,
                 client: LlmClient = Depends(get_llm_client)) -> DeckCreateResponse:
    deck_id = store.new_deck_id()
    variant_codes = payload.variants or ["a"]

    def _on_event(event: pipeline.PipelineEvent) -> None:
        store.append_event(deck_id, {"step": event.step, "slide_index": event.slide_index,
                                      "variant": event.variant, "at": event.at})

    def _run() -> None:
        try:
            pipeline.generate_deck(
                payload.design_system_id, payload.brief, payload.purpose, payload.audience,
                payload.slide_count, _on_event, deck_id=deck_id, client=client,
                variants=variant_codes,
            )
        except Exception:
            pass  # состояние ошибки уже записано pipeline.generate_deck в store.mark_deck_failed

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
        slide_images=primary.slide_images, variants=variant_states,
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
    if not path.is_file():
        raise HTTPException(404, "файл не найден")
    return FileResponse(str(path))


@app.get("/decks/{deck_id}/{variant}/files/{name}")
def get_deck_variant_file(deck_id: str, variant: str, name: str) -> FileResponse:
    try:
        path = store.deck_variant_file_path(deck_id, variant, name)
    except store.InvalidId:
        raise HTTPException(400, "недопустимое имя файла")
    if path is None:
        raise HTTPException(400, "недопустимое имя файла")
    if not path.is_file():
        raise HTTPException(404, "файл не найден")
    return FileResponse(str(path))


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
        edit.apply_slide_action(deck_id, variant, payload.action, payload.index, payload.to)
    except (*_EDIT_NOT_FOUND, edit.NoHistory, ValueError) as exc:
        raise _edit_error(exc)
    return _variant_state(deck_id, variant)


@app.patch("/decks/{deck_id}/{variant}/notes/{number}", response_model=DeckVariantState)
def patch_slide_notes(deck_id: str, variant: str, number: int, payload: SlideNotesRequest) -> DeckVariantState:
    try:
        edit.set_slide_notes(deck_id, variant, number, payload.notes)
    except (*_EDIT_NOT_FOUND, edit.NoHistory, ValueError) as exc:
        raise _edit_error(exc)
    return _variant_state(deck_id, variant)


@app.post("/decks/{deck_id}/{variant}/revert", response_model=DeckVariantState)
def post_revert(deck_id: str, variant: str) -> DeckVariantState:
    try:
        edit.revert(deck_id, variant)
    except (*_EDIT_NOT_FOUND, edit.NoHistory, ValueError) as exc:
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


# ---------- живой режим ----------

@app.post("/live/slide")
def live_slide(payload: LiveSlideRequest, client: LlmClient = Depends(get_live_llm_client)):
    try:
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
    if result is None:
        return Response(status_code=204)

    image = base64.b64encode(result.png).decode("ascii") if result.png else None
    return LiveSlideResponse(scene=result.scene, html=result.html, image_png_base64=image)


# ---------- здоровье ----------

@app.get("/health", response_model=HealthResponse)
def health(client: LlmClient = Depends(get_llm_client)) -> HealthResponse:
    return HealthResponse(model_ok=_model_available(client.base_url), converters=convert.available(),
                           skills=_skill_refs())


def _model_available(base_url: str) -> bool:
    try:
        with httpx.Client(timeout=3.0) as probe:
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
