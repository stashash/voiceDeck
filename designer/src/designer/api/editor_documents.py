import hashlib
import io
import re
import httpx
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError
from PIL import Image

from designer import editor_documents as documents, store
from designer.export.editor_pptx import export_document

router = APIRouter(prefix='/editor')


class SaveRequest(BaseModel):
    request_id: str = Field(pattern=documents.ID)
    base_revision: int = Field(ge=0)
    title: str = Field(default='Презентация', max_length=200)
    document: documents.Document


@router.get('/documents')
def list_documents():
    with documents.database() as db:
        rows = db.execute('SELECT id, revision, title, modified FROM documents ORDER BY modified DESC LIMIT 200').fetchall()
    return {'items': [dict(r) for r in rows]}


@router.get('/documents/{document_id}')
def get_document(document_id: str):
    return documents.load(document_id)


@router.post('/documents/validate')
def validate_document(document: documents.Document):
    return document.model_dump(exclude_none=True)


@router.put('/documents/{document_id}')
def save_document(document_id: str, payload: SaveRequest):
    return documents.save(document_id, payload.request_id, payload.base_revision, payload.document, payload.title)


@router.post('/documents/from-deck/{deck_id}/{variant}')
def import_deck(deck_id: str, variant: str):
    try:
        return documents.from_deck(deck_id, variant)
    except (ValidationError, store.InvalidId) as exc:
        raise HTTPException(422, 'Эта презентация не может быть импортирована без потерь. Исходный редактор и файлы сохранены.') from exc


@router.post('/export/pptx')
def pptx(document: documents.Document):
    try:
        data = export_document(document)
    except (ValueError, OSError, httpx.HTTPError) as exc:
        raise HTTPException(422, 'Экспорт прерван: проверьте формат и доступность изображений. Документ сохранён.') from exc
    return Response(data, media_type='application/vnd.openxmlformats-officedocument.presentationml.presentation',
                    headers={'Content-Disposition': 'attachment; filename="presentation.pptx"'})


@router.post('/assets')
async def upload_asset(request: Request):
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > 8*1024*1024:
            raise HTTPException(413, 'Изображение больше 8 МБ')
        chunks.append(chunk)
    data = b''.join(chunks)
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in ('PNG', 'JPEG', 'WEBP') or image.width*image.height > 24_000_000:
                raise ValueError()
            image.verify()
    except (ValueError, OSError) as exc:
        raise HTTPException(422, 'Нужен PNG, JPEG или WebP до 24 мегапикселей') from exc
    digest = hashlib.sha256(data).hexdigest()
    root = store.data_dir() / 'editor-assets'
    root.mkdir(parents=True, exist_ok=True)
    path = root / digest
    if not path.exists():
        temporary = root / (uuid4().hex + '.tmp')
        try:
            temporary.write_bytes(data)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    return {'url': '/editor/assets/' + digest}


@router.get('/assets/{digest}')
def get_asset(digest: str):
    if not re.fullmatch(r'[a-f0-9]{64}', digest):
        raise HTTPException(404)
    path = store.data_dir() / 'editor-assets' / digest
    if not path.is_file():
        raise HTTPException(404)
    with Image.open(path) as image:
        mime = Image.MIME.get(image.format, 'application/octet-stream')
    return FileResponse(path, media_type=mime, headers={'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'public, max-age=31536000, immutable'})
