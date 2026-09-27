from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from importlib import import_module

import pytest

from designer import store
from designer.api.schemas import DeckVariantState
from designer.edit_runtime import lock
from test_voice_elements_v2 import deck, saved  # noqa: F401


@pytest.fixture
def slides(deck):
    url = f'/decks/{deck.id}/a/slides'
    response = deck.client.post(url, json={'action': 'copy', 'index': 1})
    assert response.status_code == 200, response.text
    return deck, url


def guarded_delete(raw, **changes):
    return {'action': 'delete', 'index': 1, 'expected_revision': raw.get('revision') or '',
            'target_slide_id': raw['scenes'][0]['slide_id'], **changes}


def assert_no_persistence(deck, before, history, scheduled):
    assert saved(deck) == before
    assert list(store.deck_variant_history_dir(deck.id, 'a').glob('*.json')) == history
    assert deck.scheduled == scheduled


@pytest.mark.parametrize('changes', [
    {'expected_revision': 'stale'}, {'expected_revision': ''},
    {'target_slide_id': 'another-slide'}, {'index': 2}, {'index': 0},
    {'index': -1}, {'index': 999},
])
def test_stale_or_retargeted_delete_returns_409_without_persistence(slides, changes):
    deck, url = slides
    before = deepcopy(saved(deck))
    history = list(store.deck_variant_history_dir(deck.id, 'a').glob('*.json'))
    scheduled = list(deck.scheduled)
    response = deck.client.post(url, json=guarded_delete(before, **changes))
    assert response.status_code == 409, response.text
    assert_no_persistence(deck, before, history, scheduled)


def test_matching_preconditions_delete_only_selected_slide(slides):
    deck, url = slides
    before = saved(deck)
    remaining_id = before['scenes'][1]['slide_id']
    response = deck.client.post(url, json=guarded_delete(before))
    assert response.status_code == 200, response.text
    assert [scene['slide_id'] for scene in response.json()['scenes']] == [remaining_id]
    assert response.json() == DeckVariantState(**saved(deck)).model_dump(mode='json')
    assert response.json()['revision'] != before['revision']


@pytest.mark.parametrize('legacy_revision', ['missing', None, ''])
def test_empty_expected_revision_matches_unversioned_deck(slides, legacy_revision):
    deck, url = slides
    raw = saved(deck)
    if legacy_revision == 'missing':
        raw.pop('revision', None)
    else:
        raw['revision'] = legacy_revision
    store._write_json(store.deck_variant_state_path(deck.id, 'a'), raw)
    payload = guarded_delete(raw)
    assert payload['expected_revision'] == ''
    response = deck.client.post(url, json=payload)
    assert response.status_code == 200, response.text
    assert len(response.json()['scenes']) == 1
    assert response.json()['revision']


def test_legacy_manual_call_without_preconditions_still_works(slides):
    deck, url = slides
    response = deck.client.post(url, json={'action': 'delete', 'index': 1})
    assert response.status_code == 200, response.text
    assert len(response.json()['scenes']) == 1


@pytest.mark.parametrize('preconditions', [
    {'expected_revision': 'before'}, {'target_slide_id': 's1'},
    {'expected_revision': ''}, {'expected_revision': None}, {'target_slide_id': None},
    {'expected_revision': None, 'target_slide_id': 's1'},
    {'expected_revision': '', 'target_slide_id': None},
    {'expected_revision': '', 'target_slide_id': ''},
    {'expected_revision': 1, 'target_slide_id': 's1'},
])
def test_partial_or_invalid_preconditions_are_422(slides, preconditions):
    deck, url = slides
    before = saved(deck)
    response = deck.client.post(url, json={'action': 'delete', 'index': 1, **preconditions})
    assert response.status_code == 422, response.text
    assert saved(deck) == before


def test_checks_mutation_and_response_share_the_lock(slides, monkeypatch):
    deck, url = slides
    api = import_module('designer.api.app')
    original_load = api.store.load_deck_state
    original_apply = api.edit.apply_slide_action
    original_response = api._variant_state
    checked = set()

    def guarded(name, function):
        def wrapped(*args, **kwargs):
            def competing_thread():
                acquired = lock(deck.id, 'a').acquire(blocking=False)
                if acquired:
                    lock(deck.id, 'a').release()
                return acquired

            with ThreadPoolExecutor(max_workers=1) as pool:
                assert pool.submit(competing_thread).result(timeout=2) is False
            checked.add(name)
            return function(*args, **kwargs)
        return wrapped

    payload = guarded_delete(saved(deck))
    monkeypatch.setattr(api.store, 'load_deck_state', guarded('check', original_load))
    monkeypatch.setattr(api.edit, 'apply_slide_action', guarded('mutation', original_apply))
    monkeypatch.setattr(api, '_variant_state', guarded('response', original_response))
    response = deck.client.post(url, json=payload)
    assert response.status_code == 200, response.text
    assert checked == {'check', 'mutation', 'response'}


def test_competing_confirmations_cannot_delete_two_slides(slides):
    deck, url = slides
    assert deck.client.post(url, json={'action': 'copy', 'index': 1}).status_code == 200
    payload = guarded_delete(saved(deck))
    with ThreadPoolExecutor(max_workers=2) as pool:
        requests = [pool.submit(deck.client.post, url, json=payload) for _ in range(2)]
        responses = [request.result(timeout=10) for request in requests]
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert len(saved(deck)['scenes']) == 2
