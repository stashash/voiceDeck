"""Versioned editor documents. SQLite serializes writes across API workers."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from designer import store
from designer.api.editor_plan import Properties

ID = r'^[A-Za-z0-9_-]{1,128}$'
COLOR = r'^#[0-9a-fA-F]{6}$'


class Component(Properties):
    id: str = Field(pattern=ID)
    kind: Literal['title', 'text', 'card', 'image', 'shape', 'table', 'chart']
    text: str = Field(default='', max_length=12000)
    x: float = Field(ge=0, le=1280)
    y: float = Field(ge=0, le=720)
    width: float = Field(ge=1, le=1280)
    height: float = Field(ge=1, le=720)
    size: float = Field(default=26, ge=1, le=200)
    color: str = Field(default='#17141f', pattern=COLOR)
    fill: str = Field(default='transparent', pattern=r'^(#[0-9a-fA-F]{6}|transparent)$')
    side: Literal['left', 'right'] = 'left'
    voiceNumber: int | None = Field(default=None, ge=1)
    url: str | None = Field(default=None, max_length=12_000_000)
    group: str | None = Field(default=None, pattern=ID)
    attribution: str | None = Field(default=None, max_length=4000)
    sourceShapeId: int | None = None

    @model_validator(mode='after')
    def content(self):
        if self.rows is not None and (not self.rows or not self.rows[0] or len(self.rows[0]) > 12 or
                any(len(r) != len(self.rows[0]) or any(len(v) > 1000 for v in r) for r in self.rows)):
            raise ValueError('Table must be rectangular, 1-20 rows and 1-12 columns')
        if self.kind == 'chart' and (len(self.values or []) != len(self.labels or []) or any(v < 0 for v in self.values or [])):
            raise ValueError('Chart requires equal-length labels and nonnegative values')
        if self.url and not safe_image_url(self.url):
            raise ValueError('Unsupported image URL')
        return self


def safe_image_url(url: str) -> bool:
    import re
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return (url.startswith(('data:image/png;base64,', 'data:image/jpeg;base64,', 'data:image/webp;base64,')) or
            bool(re.fullmatch(r'/editor/assets/[a-f0-9]{64}', url)) or
            bool(re.fullmatch(r'/design-systems/[A-Za-z0-9_-]+/assets/[A-Za-z0-9_./-]+', url)) and '..' not in url or
            parsed.scheme == 'https' and parsed.hostname in ('upload.wikimedia.org', 'thumb.wikimedia.org') and not parsed.username)


class Page(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    id: str = Field(pattern=ID)
    components: list[Component] = Field(default_factory=list, max_length=100)
    background: str = Field(default='#ffffff', pattern=COLOR)
    backgroundUrl: str | None = None
    notes: str = Field(default='', max_length=12000)
    nextVoiceNumber: int = Field(default=1, ge=1)

    @model_validator(mode='after')
    def background_image(self):
        if self.backgroundUrl and not safe_image_url(self.backgroundUrl):
            raise ValueError('Unsupported background image')
        return self


class Document(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    schemaVersion: Literal[1] = 1
    pages: list[Page] = Field(min_length=1, max_length=100)
    index: int = Field(default=0, ge=0)
    selected: str | None = None
    selectedIds: list[str] = Field(default_factory=list, max_length=100)
    designId: str | None = Field(default=None, pattern=ID)

    @model_validator(mode='after')
    def identities(self):
        if self.index >= len(self.pages):
            raise ValueError('Selected slide does not exist')
        ids = [p.id for p in self.pages] + [c.id for p in self.pages for c in p.components]
        if len(ids) != len(set(ids)):
            raise ValueError('Document IDs must be unique')
        return self


@contextmanager
def database():
    root = store.data_dir()
    root.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(root / 'editor.sqlite3', timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute('CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, title TEXT NOT NULL, data TEXT NOT NULL, modified REAL NOT NULL)')
        connection.execute('CREATE TABLE IF NOT EXISTS commands (document_id TEXT, request_id TEXT, fingerprint TEXT, revision INTEGER, PRIMARY KEY(document_id, request_id))')
        yield connection
    finally:
        connection.close()


def load(document_id: str) -> dict:
    store._check_id(document_id)
    with database() as db:
        row = db.execute('SELECT * FROM documents WHERE id=?', (document_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Документ не найден')
    return {'id': row['id'], 'revision': row['revision'], 'title': row['title'], 'document': json.loads(row['data'])}


def save(document_id: str, request_id: str, revision: int, document: Document, title: str) -> dict:
    store._check_id(document_id)
    data = document.model_dump_json(exclude_none=True)
    if len(data.encode()) > 16_000_000:
        raise HTTPException(413, 'Документ слишком велик. Загрузите изображения как файлы.')
    fingerprint = hashlib.sha256((data + title + str(revision)).encode()).hexdigest()
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        previous = db.execute('SELECT fingerprint, revision FROM commands WHERE document_id=? AND request_id=?', (document_id, request_id)).fetchone()
        if previous:
            if previous['fingerprint'] != fingerprint:
                raise HTTPException(409, 'Повторный запрос содержит другие данные')
            return {'id': document_id, 'revision': previous['revision']}
        row = db.execute('SELECT revision FROM documents WHERE id=?', (document_id,)).fetchone()
        current = row['revision'] if row else 0
        if current != revision:
            raise HTTPException(409, 'Документ изменён в другой вкладке. Сохраните локальную копию и откройте актуальную версию.')
        db.execute('INSERT OR REPLACE INTO documents VALUES(?,?,?,?,?)', (document_id, current+1, title, data, time.time()))
        db.execute('INSERT INTO commands VALUES(?,?,?,?)', (document_id, request_id, fingerprint, current+1))
        db.execute('DELETE FROM commands WHERE document_id=? AND revision<?', (document_id, current-100))
        db.commit()
    return {'id': document_id, 'revision': current+1}


def from_deck(deck_id: str, variant: str) -> dict:
    import uuid
    raw = store.load_deck_state(deck_id, variant)
    if not raw or not raw.get('scenes'):
        raise HTTPException(404, 'Готовые слайды не найдены')
    doc_id = 'deck-' + hashlib.sha256((deck_id + '/' + variant).encode()).hexdigest()[:32]
    try:
        return load(doc_id)
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
    ds = raw['design_system_id']
    def color(value, fallback):
        return '#' + value.lstrip('#') if value and value != 'transparent' else fallback
    def asset(path):
        return f'/design-systems/{ds}/{path}' if path else None
    pages = []
    for scene in raw['scenes']:
        components = []
        for el in sorted(scene.get('elements', []), key=lambda e: e.get('z', 0)):
            style = el.get('style') or {}
            x, y, w, h = el['box']
            kind = 'image' if el['type'] == 'icon' else 'title' if el.get('role') == 'title' else el['type']
            c = dict(id=uuid.uuid4().hex, kind=kind, text=el.get('text', ''),
                     x=max(0, min(1279, x*1280)), y=max(0, min(719, y*720)),
                     width=max(1, min(1280, w*1280)), height=max(1, min(720, h*720)),
                     size=min(160, (style.get('size_pt') or 20)*4/3),
                     font=style.get('family') or 'Arial', color=color(style.get('color'), '#17141f'),
                     fill=color(el.get('fill'), 'transparent'), bold=style.get('bold', False),
                     italic=style.get('italic', False), align=style.get('align') or 'left',
                     sourceShapeId=el.get('source_shape_id'), url=asset(el.get('asset')))
            if el.get('table'):
                c['rows'] = [el['table']['columns'], *el['table']['rows']]
            if el.get('chart'):
                chart = el['chart']
                if chart['type'] != 'column' or len(chart['series']) != 1 or any(v < 0 for v in chart['series'][0]['values']):
                    raise HTTPException(422, 'В презентации сложная диаграмма. Откройте исходный редактор: импорт без потери данных пока невозможен.')
                c.update(labels=chart['categories'], values=chart['series'][0]['values'])
            components.append(c)
        pages.append({'id': uuid.uuid4().hex, 'components': components,
                      'background': color(scene.get('background_color'), '#ffffff'),
                      'backgroundUrl': asset(scene.get('background_asset')),
                      'notes': next((s.get('notes', '') for s in raw.get('specs', []) if s.get('slide_id') == scene['slide_id']), '')})
    document = Document.model_validate({'pages': pages, 'designId': ds})
    title = (raw.get('plan') or {}).get('title') or 'Презентация'
    try:
        save(doc_id, uuid.uuid4().hex, 0, document, title)
    except HTTPException as exc:
        if exc.status_code != 409:
            raise
    return load(doc_id)
