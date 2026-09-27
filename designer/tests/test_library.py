from fastapi.testclient import TestClient
from designer.api.app import app
from designer import store

def test_archive_restore_copy(tmp_path, monkeypatch):
    monkeypatch.setenv('DESIGNER_DATA_DIR', str(tmp_path))
    store.init_deck('original','theme')
    store._write_json(store.deck_variant_state_path('original','a'), {'status':'done','design_system_id':'theme','plan':{'title':'Original','slides':[]},'scenes':[],'specs':[],'findings':[]})
    client=TestClient(app)
    assert client.post('/library/original/delete').status_code==200
    assert client.get('/decks').json()['items']==[]
    assert client.get('/library/trash').json()['items'][0]['id']=='original'
    assert client.post('/library/original/restore').status_code==200
    assert client.get('/decks').json()['items'][0]['id']=='original'
    response=client.post('/library/original/copy')
    assert response.status_code==200
    copied=response.json()['deck_id']
    assert copied!='original'
    assert store.load_deck_state('original')['plan']['title']=='Original'
    assert store.load_deck_state(copied)['plan']['title']=='Original — копия'

def test_running_and_missing(tmp_path, monkeypatch):
    monkeypatch.setenv('DESIGNER_DATA_DIR',str(tmp_path))
    store.init_deck('running','theme')
    client=TestClient(app)
    assert client.post('/library/running/delete').status_code==409
    assert client.post('/library/running/copy').status_code==409
    assert client.post('/library/missing/delete').status_code==404
