import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from designer.api import deck_voice
from designer.api.deck_voice import VoiceRewrite, rewrite_text


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


def test_concurrent_edit_wins_over_model(environment):
    request, payload = environment
    deck_voice.store.load_deck_state.return_value = {'revision': 'newer'}
    with pytest.raises(HTTPException) as error:
        asyncio.run(deck_voice.voice_rewrite('deck', 'a', 1, payload, request))
    assert error.value.status_code == 409
    deck_voice.edit.set_slide_text.assert_not_called()


def test_disconnect_prevents_commit(environment):
    request, payload = environment
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
