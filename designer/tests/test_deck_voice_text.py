from copy import deepcopy

import pytest

from designer import store
from designer.api.schemas import DeckVariantState
from test_voice_elements_v2 import deck, saved  # noqa: F401


def payload(raw, **changes):
    return {'element_id': 'title', 'text': 'The words finish and cancel are literal text.',
            'expected_revision': raw.get('revision') or '',
            'target_slide_id': raw['scenes'][0]['slide_id'], **changes}


def url(deck, number=1):
    return f'/decks/{deck.id}/a/slides/{number}/voice-text'


def test_dictation_commits_literal_text_once_and_can_be_undone(deck):
    before = saved(deck)
    request = payload(before)
    response = deck.client.post(url(deck), json=request)
    assert response.status_code == 200, response.text
    assert response.json()['scenes'][0]['elements'][0]['text'] == request['text']
    assert response.json() == DeckVariantState(**saved(deck)).model_dump(mode='json')
    history = list(store.deck_variant_history_dir(deck.id, 'a').glob('*.json'))
    assert len(history) == 1
    assert len(deck.scheduled) == 1
    replay = deck.client.post(url(deck), json=request)
    assert replay.status_code == 409
    assert len(deck.scheduled) == 1
    from designer import edit
    edit.revert(deck.id, 'a')
    assert saved(deck)['scenes'][0]['elements'][0]['text'] == before['scenes'][0]['elements'][0]['text']


@pytest.mark.parametrize(('number', 'changes'), [
    (1, {'expected_revision': 'stale'}), (1, {'target_slide_id': 'another-slide'}),
    (0, {}), (2, {}),
])
def test_stale_or_missing_slide_cannot_persist_dictation(deck, number, changes):
    before = deepcopy(saved(deck))
    response = deck.client.post(url(deck, number), json=payload(before, **changes))
    assert response.status_code == 409, response.text
    assert saved(deck) == before
    assert not list(store.deck_variant_history_dir(deck.id, 'a').glob('*.json'))
    assert not deck.scheduled


def test_moved_slide_identity_is_checked_even_with_current_revision(deck):
    original = payload(saved(deck))
    slides_url = f'/decks/{deck.id}/a/slides'
    assert deck.client.post(slides_url, json={'action': 'copy', 'index': 1}).status_code == 200
    assert deck.client.post(slides_url, json={'action': 'move', 'index': 1, 'to': 2}).status_code == 200
    before = deepcopy(saved(deck))
    original['expected_revision'] = before['revision']
    scheduled = list(deck.scheduled)
    history = list(store.deck_variant_history_dir(deck.id, 'a').glob('*.json'))
    response = deck.client.post(url(deck), json=original)
    assert response.status_code == 409, response.text
    assert saved(deck) == before
    assert deck.scheduled == scheduled
    assert list(store.deck_variant_history_dir(deck.id, 'a').glob('*.json')) == history


@pytest.mark.parametrize('legacy_revision', ['missing', None, ''])
def test_dictation_accepts_empty_revision_only_for_unversioned_decks(deck, legacy_revision):
    raw = saved(deck)
    if legacy_revision == 'missing':
        raw.pop('revision', None)
    else:
        raw['revision'] = legacy_revision
    store._write_json(store.deck_variant_state_path(deck.id, 'a'), raw)
    response = deck.client.post(url(deck), json=payload(raw))
    assert response.status_code == 200, response.text
    assert response.json()['revision']
    stale = deck.client.post(url(deck), json=payload(raw))
    assert stale.status_code == 409


@pytest.mark.parametrize('changes', [
    {'element_id': 'missing'}, {'element_id': 'shape'}, {'element_id': 1},
    {'text': None}, {'text': 123}, {'text': 'x' * 12001},
    {'expected_revision': None}, {'expected_revision': 123},
    {'target_slide_id': None}, {'target_slide_id': ''}, {'unknown': True},
])
def test_invalid_dictation_payload_or_target_never_mutates(deck, changes):
    before = saved(deck)
    response = deck.client.post(url(deck), json=payload(before, **changes))
    assert response.status_code == 422, response.text
    assert saved(deck) == before
    assert not deck.scheduled


@pytest.mark.parametrize('missing', ['expected_revision', 'target_slide_id', 'element_id', 'text'])
def test_all_dictation_fields_are_required(deck, missing):
    before = saved(deck)
    request = payload(before)
    del request[missing]
    response = deck.client.post(url(deck), json=request)
    assert response.status_code == 422, response.text
    assert saved(deck) == before


def test_legacy_text_patch_remains_available(deck):
    response = deck.client.patch(f'/decks/{deck.id}/a/slides/1/text',
                                 json={'element_id': 'title', 'text': 'Manual edit'})
    assert response.status_code == 200, response.text
    assert response.json()['scenes'][0]['elements'][0]['text'] == 'Manual edit'
