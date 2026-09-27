"""Bounded local-model text edits, isolated from full-slide generation."""
import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from designer import edit, store
from designer.api.schemas import DeckVariantState
from designer.edit_runtime import lock
from designer.editor_model import editor_model
from designer.editor_planner import planner

router = APIRouter()


class VoiceRewrite(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    element_id: str = Field(min_length=1, max_length=200)
    instruction: str = Field(min_length=1, max_length=3000)


def rewrite_text(plan, element_id):
    """Reject any attempted layout, deletion, or unrelated-object operation."""
    operations = plan.get('operations', [])
    if len(operations) != 1:
        raise HTTPException(422, 'Нужна одна правка выбранного текста. Документ не изменён.')
    op = operations[0]
    props = op.get('props', {})
    if (op.get('op') != 'update' or op.get('targets') not in ([element_id], ['selected'])
            or set(props) != {'text'} or not isinstance(props['text'], str) or len(props['text']) > 12000):
        raise HTTPException(422, 'Ответ модели выходит за границы выбранного текста. Документ не изменён.')
    return props['text']


@router.post('/decks/{deck_id}/{variant}/slides/{number}/voice-rewrite')
async def voice_rewrite(deck_id: str, variant: str, number: int, payload: VoiceRewrite, request: Request):
    try:
        with lock(deck_id, variant):
            state = edit._load(deck_id, variant)
            index = edit._slide_index(state, number)
            element = next((e for e in state.scenes[index].elements if e.id == payload.element_id), None)
            if element is None or element.type != 'text':
                raise HTTPException(422, 'Выберите текстовый элемент')
    except (ValueError, FileNotFoundError, edit.SlideNotFound) as exc:
        raise HTTPException(404, str(exc)) from exc
    status = await editor_model.status(prepare=True)
    if status['state'] != 'ready':
        raise HTTPException(503, status.get('message', 'Локальная модель ещё не готова'))
    context = json.dumps({
        'selected': [element.id], 'scope': 'Only rewrite this text. Return one update with props.text only.',
        'document': {'pages': [{'id': state.scenes[index].slide_id, 'components': [
            {'id': element.id, 'kind': 'text', 'text': element.text}]}], 'index': 0, 'selected': element.id},
    }, ensure_ascii=False)

    async def disconnect():
        while True:
            await asyncio.sleep(.1)
            if await request.is_disconnected():
                planner.cancel(payload.request_id)
                return
    watcher = asyncio.create_task(disconnect())
    try:
        plan = await planner.run(payload.request_id, payload.instruction, context)
        if plan.get('clarification'):
            return {'notice': plan['clarification'], 'elapsed_ms': plan.get('elapsed_ms')}
        text = rewrite_text(plan, element.id)
        if await request.is_disconnected():
            raise HTTPException(409, 'Запрос отменён')
        with lock(deck_id, variant):
            if store.load_deck_state(deck_id, variant) != state.raw:
                raise HTTPException(409, 'Документ уже изменён. Устаревший ответ модели не применён.')
            edit.set_slide_text(deck_id, variant, number, element.id, text)
            updated = DeckVariantState(**store.load_deck_state(deck_id, variant))
        return {'state': updated, 'notice': 'Текст сохранён', 'elapsed_ms': plan.get('elapsed_ms')}
    finally:
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)
