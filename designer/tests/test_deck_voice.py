import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from designer.api import deck_voice
from designer.api.deck_voice import VoiceRewrite, VoiceRewriteConstraints, rewrite_text
from designer.editor_planner import Planner


def plan(text='Short text', target='e1'):
    return {'operations': [{'op': 'update', 'targets': [target], 'props': {'text': text}}], 'clarification': ''}


@pytest.mark.parametrize('operation', [
    {'op': 'delete', 'targets': ['e1']},
    {'op': 'update', 'targets': ['e2'], 'props': {'text': 'wrong'}},
    {'op': 'update', 'targets': ['e1'], 'props': {'text': 'right', 'width': 30}},
    {'op': 'update', 'targets': ['e1'], 'props': {'text': None}},
])
def test_rewrite_rejects_out_of_scope_plan(operation):
    with pytest.raises(HTTPException) as error:
        rewrite_text({'operations': [operation]}, 'e1')
    assert error.value.status_code == 422


def test_rewrite_preserves_literal_text():
    assert rewrite_text(plan('API v2: 20%.'), 'e1') == 'API v2: 20%.'


@pytest.fixture
def environment(monkeypatch, tmp_path):
    monkeypatch.setenv('DESIGNER_DATA_DIR', str(tmp_path))
    raw = {'revision': 'before'}
    state = SimpleNamespace(raw=raw, scenes=[SimpleNamespace(slide_id='s1', elements=[SimpleNamespace(id='e1', type='text', text='Original text')])])
    monkeypatch.setattr(deck_voice.edit, '_load', lambda *_: state)
    monkeypatch.setattr(deck_voice.edit, '_slide_index', lambda *_: 0)
    monkeypatch.setattr(deck_voice.store, 'load_deck_state', Mock(return_value=dict(raw)))
    monkeypatch.setattr(deck_voice.edit, 'set_slide_text', Mock())
    monkeypatch.setattr(deck_voice, 'DeckVariantState', lambda **kw: kw)
    monkeypatch.setattr(deck_voice.editor_model, 'status', AsyncMock(return_value={'state': 'ready'}))
    monkeypatch.setattr(deck_voice.planner, 'run', AsyncMock(return_value=plan()))
    request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))
    payload = VoiceRewrite(request_id='test-request', element_id='e1', instruction='Shorten selected text')
    return request, payload


def test_voice_rewrite_persists_selected_text(environment):
    request, payload = environment
    result = asyncio.run(deck_voice.voice_rewrite('deck', 'a', 1, payload, request))
    deck_voice.edit.set_slide_text.assert_called_once_with('deck', 'a', 1, 'e1', 'Short text')
    assert result['state']['revision'] == 'before'


@pytest.mark.parametrize('constrained', [False, True])
def test_concurrent_edit_wins_over_model(environment, constrained):
    request, payload = environment
    if constrained:
        payload.constraints = VoiceRewriteConstraints(preserve_numbers=True, preserve_dates=True)
    deck_voice.store.load_deck_state.return_value = {'revision': 'newer'}
    with pytest.raises(HTTPException) as error:
        asyncio.run(deck_voice.voice_rewrite('deck', 'a', 1, payload, request))
    assert error.value.status_code == 409
    deck_voice.edit.set_slide_text.assert_not_called()


@pytest.mark.parametrize('constrained', [False, True])
def test_disconnect_prevents_commit(environment, constrained):
    request, payload = environment
    if constrained:
        payload.constraints = VoiceRewriteConstraints(preserve_numbers=True, preserve_dates=True)
    request.is_disconnected.return_value = True
    with pytest.raises(HTTPException) as error:
        asyncio.run(deck_voice.voice_rewrite('deck', 'a', 1, payload, request))
    assert error.value.status_code == 409
    deck_voice.edit.set_slide_text.assert_not_called()


def test_clarification_never_saves(environment):
    request, payload = environment
    deck_voice.planner.run.return_value = {'operations': [], 'clarification': 'Which text?'}
    result = asyncio.run(deck_voice.voice_rewrite('deck', 'a', 1, payload, request))
    assert result['notice'] == 'Which text?'
    deck_voice.edit.set_slide_text.assert_not_called()


def test_cold_model_does_not_block_document(environment):
    request, payload = environment
    deck_voice.editor_model.status.return_value = {'state': 'loading'}
    with pytest.raises(HTTPException) as error:
        asyncio.run(deck_voice.voice_rewrite('deck', 'a', 1, payload, request))
    assert error.value.status_code == 503
    deck_voice.edit.set_slide_text.assert_not_called()
    deck_voice.planner.run.assert_not_called()


@pytest.mark.parametrize(('original', 'rewritten', 'constraint'), [
    ('Launch in 2024.', 'Launch soon.', 'preserve_dates'),
    ('Launch in 2024.', 'Launch soon.', 'preserve_numbers'),
    ('Margin: 20%.', 'Margin: 20.', 'preserve_numbers'),
    ('Margin: +20%.', 'Margin: -20%.', 'preserve_numbers'),
    ('Margin: -20%.', 'Margin: 20%.', 'preserve_numbers'),
    ('Weight: 20 kg.', 'Weight: 20 g.', 'preserve_numbers'),
    ('Cost: $20.', 'Cost: \u20ac20.', 'preserve_numbers'),
    ('Cost: 20 USD.', 'Cost: 20 EUR.', 'preserve_numbers'),
    ('Cost: 20 million USD.', 'Cost: 20 million EUR.', 'preserve_numbers'),
    ('Revenue: 20%; costs: 10%.', 'Revenue: 10%; costs: 20%.', 'preserve_numbers'),
    ('Revenue: 20%; costs: 20%.', 'Revenue: 20%.', 'preserve_numbers'),
    ('Launch on 2024-05-12.', 'Launch on 2024-12-05.', 'preserve_dates'),
    ('Launch on September 12, 2024.', 'Launch on September 12.', 'preserve_dates'),
    ('Launch in September.', 'Launch in October.', 'preserve_dates'),
    ('Launch in 2024.', 'Launch in 2024; closure in 2025.', 'preserve_dates'),
])
def test_constraint_violation_returns_422_without_mutation(environment, original, rewritten, constraint):
    request, payload = environment
    deck_voice.edit._load('deck', 'a').scenes[0].elements[0].text = original
    deck_voice.planner.run.return_value = plan(rewritten)
    payload.constraints = VoiceRewriteConstraints(**{constraint: True})
    with pytest.raises(HTTPException) as error:
        asyncio.run(deck_voice.voice_rewrite('deck', 'a', 1, payload, request))
    assert error.value.status_code == 422
    assert constraint in error.value.detail
    deck_voice.edit.set_slide_text.assert_not_called()
    deck_voice.planner.run.assert_awaited_once()


def test_unchanged_facts_can_be_shortened_and_constraints_reach_model(environment):
    request, payload = environment
    original = 'Revenue was +20% in 2024. This was an exciting outcome.'
    rewritten = 'Revenue: +20% in 2024.'
    deck_voice.edit._load('deck', 'a').scenes[0].elements[0].text = original
    deck_voice.planner.run.return_value = plan(rewritten)
    payload.constraints = VoiceRewriteConstraints(preserve_numbers=True, preserve_dates=True)
    asyncio.run(deck_voice.voice_rewrite('deck', 'a', 1, payload, request))
    deck_voice.edit.set_slide_text.assert_called_once_with('deck', 'a', 1, 'e1', rewritten)
    args = deck_voice.planner.run.await_args.args
    context = json.loads(args[2])
    assert context['constraints'] == {'preserve_numbers': True, 'preserve_dates': True}
    assert context['document']['pages'][0]['components'][0]['text'] == original


@pytest.mark.parametrize('constraints', [None, VoiceRewriteConstraints()])
def test_ordinary_requests_do_not_implicitly_protect_facts(environment, constraints):
    request, payload = environment
    payload.constraints = constraints
    deck_voice.edit._load('deck', 'a').scenes[0].elements[0].text = 'Revenue: +20% in 2024.'
    asyncio.run(deck_voice.voice_rewrite('deck', 'a', 1, payload, request))
    deck_voice.edit.set_slide_text.assert_called_once_with('deck', 'a', 1, 'e1', 'Short text')


@pytest.mark.parametrize('constraints', [
    {'preserve_numbers': 'true'}, {'preserve_dates': 1}, {'preserve_dates': None},
    {'preserve_currency': True}, [], 'preserve numbers',
])
def test_api_rejects_invalid_constraints_before_planning(environment, constraints):
    app = FastAPI()
    app.include_router(deck_voice.router)
    payload = environment[1].model_dump()
    payload['constraints'] = constraints
    response = TestClient(app).post('/decks/deck/a/slides/1/voice-rewrite', json=payload)
    assert response.status_code == 422
    deck_voice.edit.set_slide_text.assert_not_called()
    deck_voice.planner.run.assert_not_called()


def test_api_constraint_failure_is_422(environment):
    app = FastAPI()
    app.include_router(deck_voice.router)
    deck_voice.edit._load('deck', 'a').scenes[0].elements[0].text = 'Launch: 2024.'
    payload = environment[1].model_dump()
    payload['constraints'] = {'preserve_dates': True}
    response = TestClient(app).post('/decks/deck/a/slides/1/voice-rewrite', json=payload)
    assert response.status_code == 422
    deck_voice.edit.set_slide_text.assert_not_called()


@pytest.mark.parametrize('cancel_before_start', [False, True])
def test_constrained_rewrite_retains_real_planner_cancellation(environment, monkeypatch, cancel_before_start):
    request, payload = environment
    payload.constraints = VoiceRewriteConstraints(preserve_numbers=True, preserve_dates=True)
    planner = Planner()
    monkeypatch.setattr(deck_voice, 'planner', planner)

    async def run():
        started = asyncio.Event()

        async def completion(*_):
            started.set()
            await asyncio.Event().wait()

        monkeypatch.setattr('designer.editor_planner.complete_plan', completion)
        if cancel_before_start:
            planner.cancel(payload.request_id)
        task = asyncio.create_task(deck_voice.voice_rewrite('deck', 'a', 1, payload, request))
        if not cancel_before_start:
            await asyncio.wait_for(started.wait(), 1)
            request.is_disconnected.return_value = True
        with pytest.raises(HTTPException) as error:
            await asyncio.wait_for(task, 2)
        assert error.value.status_code == 409
        assert planner.jobs[payload.request_id].task is None

    asyncio.run(run())
    deck_voice.edit.set_slide_text.assert_not_called()
