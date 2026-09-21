"""FastAPI-сервис: пакеты дизайн-систем, генерация колоды, живой режим. Владелец: задача T-13."""
from __future__ import annotations

import json
import os
from collections.abc import Iterator

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from designer import pipeline, store
from designer.api.schemas import (
    DeckCreateRequest,
    DeckCreateResponse,
    DeckStateResponse,
    DesignSystemListResponse,
    HealthResponse,
    LiveSlideRequest,
    LiveSlideResponse,
)
from designer.contracts import Deck, DeckPlan, DesignSystem, RunManifest
from designer.export import convert
from designer.export.html import render_deck
from designer.llm.client import LlmClient
from designer.llm.skills import SkillError, load_skill
from designer.parse.package import load_package

_ORIGINS_ENV = "DESIGNER_ALLOWED_ORIGINS"
_HEALTH_SKILLS = ("plan-deck", "fill-slots", "speech-to-slide", "audit-slide", "audit-deck")

app = FastAPI(title="Цифровой дизайнер презентаций")

_origins = [origin.strip() for origin in os.environ.get(_ORIGINS_ENV, "").split(",") if origin.strip()]
if _origins:
    app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_methods=["*"], allow_headers=["*"])


def get_llm_client() -> LlmClient:
    """Клиент модели на запрос. Переопределяется в тестах через app.dependency_overrides."""
    return LlmClient.from_env()


def _not_found(ds_id_error: bool = False):
    return HTTPException(404, "дизайн-система не найдена" if ds_id_error else "не найдено")


# ---------- дизайн-системы ----------

@app.post("/design-systems", response_model=DesignSystem)
async def upload_design_system(file: UploadFile = File(...)) -> DesignSystem:
    data = await file.read()
    if not data:
        raise HTTPException(400, "пустой файл")
    return pipeline.import_template(data, file.filename or "template.pptx")


@app.get("/design-systems", response_model=DesignSystemListResponse)
def list_design_systems() -> DesignSystemListResponse:
    return DesignSystemListResponse(ids=store.list_design_system_ids())


@app.get("/design-systems/{ds_id}", response_model=DesignSystem)
def get_design_system(ds_id: str) -> DesignSystem:
    try:
        return load_package(store.design_system_dir(ds_id))
    except (store.InvalidId, FileNotFoundError):
        raise _not_found(True)


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

@app.post("/decks", response_model=DeckCreateResponse)
def create_deck(payload: DeckCreateRequest, background_tasks: BackgroundTasks,
                 client: LlmClient = Depends(get_llm_client)) -> DeckCreateResponse:
    deck_id = store.new_deck_id()

    def _on_event(event: pipeline.PipelineEvent) -> None:
        store.append_event(deck_id, {"step": event.step, "slide_index": event.slide_index, "at": event.at})

    def _run() -> None:
        try:
            pipeline.generate_deck(
                payload.design_system_id, payload.brief, payload.purpose, payload.audience,
                payload.slide_count, _on_event, deck_id=deck_id, client=client,
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
    state = store.load_deck_state(deck_id)
    if state is None:
        raise HTTPException(404, "колода не найдена")
    return DeckStateResponse(**state)


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


# ---------- живой режим ----------

@app.post("/live/slide")
def live_slide(payload: LiveSlideRequest, client: LlmClient = Depends(get_llm_client)):
    scene = pipeline.live_slide(
        payload.design_system_id, payload.chunk_text, payload.used_pattern_ids, client=client,
    )
    if scene is None:
        return Response(status_code=204)

    package_dir = store.design_system_dir(payload.design_system_id)
    ds = load_package(package_dir)
    solo_deck = Deck(
        id="live", design_system_id=payload.design_system_id, variant="a",
        plan=DeckPlan(title="", purpose="", slides=[]), specs=[], scenes=[scene],
    )
    html_text = render_deck(solo_deck, ds, package_dir)
    return LiveSlideResponse(scene=scene, html=html_text)


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
