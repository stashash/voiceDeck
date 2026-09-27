"""Recoverable deletion and copying of generated decks."""
import shutil
from fastapi import APIRouter, HTTPException
from designer import store, pipeline

router = APIRouter(prefix='/library')

def existing(deck_id):
    try:
        path = store.decks_root() / store._check_id(deck_id)
    except ValueError as error:
        raise HTTPException(400, 'Некорректный идентификатор') from error
    if not path.is_dir():
        raise HTTPException(404, 'Презентация не найдена')
    return path

@router.get('/trash')
def trash():
    return {'items': [d for d in pipeline.list_decks() if (existing(d['id']) / '.deleted').exists()]}

@router.post('/{deck_id}/delete')
def delete(deck_id: str):
    path = existing(deck_id)
    if any((store.load_deck_state(deck_id, v) or {}).get('status') == 'running' for v in store.deck_variants(deck_id)):
        raise HTTPException(409, 'Дождитесь завершения генерации или остановите её')
    store.write_text_atomic(path / '.deleted', 'deleted')
    return {'status': 'deleted'}

@router.post('/{deck_id}/restore')
def restore(deck_id: str):
    (existing(deck_id) / '.deleted').unlink(missing_ok=True)
    return {'status': 'restored'}

@router.post('/{deck_id}/copy')
def copy(deck_id: str):
    path = existing(deck_id)
    if any((store.load_deck_state(deck_id, v) or {}).get('status') == 'running' for v in store.deck_variants(deck_id)):
        raise HTTPException(409, 'Дождитесь завершения генерации')
    new_id = store.new_deck_id()
    shutil.copytree(path, store.decks_root() / new_id)
    (store.decks_root() / new_id / '.deleted').unlink(missing_ok=True)
    state = store.load_deck_state(new_id) or {}
    title = (state.get('plan') or {}).get('title', 'Презентация')
    store.rename_deck(new_id, title + ' — копия')
    return {'deck_id': new_id}
