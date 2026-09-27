"""Voice intent planning and image providers for the component editor."""
import base64
import asyncio
import os
import re
from typing import Literal
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from uuid import uuid4
from designer.editor_planner import planner
from designer.editor_model import editor_model

router = APIRouter(prefix='/editor')

class IntentRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid4()), pattern=r'^[A-Za-z0-9_-]{1,80}$')
    instruction: str = Field(min_length=1, max_length=3000)
    context: str = Field(default='', max_length=24000)

@router.post('/intent')
async def intent(payload: IntentRequest, request: Request):
    status = await editor_model.status(prepare=True)
    if status['state'] != 'ready':
        raise HTTPException(503, {'code': 'model_loading' if status['state'] == 'loading' else 'model_unavailable',
                                 'message': status.get('message', 'Загружается модель для сложных команд'),
                                 'model': status['model']})
    async def disconnect():
        while True:
            await asyncio.sleep(.1)
            if await request.is_disconnected():
                planner.cancel(payload.request_id)
                return
    watcher = asyncio.create_task(disconnect())
    try:
        return await planner.run(payload.request_id, payload.instruction, payload.context)
    finally:
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)

@router.post('/intent/prepare')
async def prepare_intent_model():
    return await editor_model.status(prepare=True)

@router.get('/intent/model')
async def intent_model_status():
    return await editor_model.status()

@router.post('/intent/{request_id}/cancel')
async def cancel_intent(request_id: str):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', request_id):
        raise HTTPException(422, 'Некорректный идентификатор')
    planner.cancel(request_id)
    return {'status': 'cancelled'}

@router.get('/intent/status')
async def intent_status():
    return {'active': sum(j.task is not None for j in planner.jobs.values()),
            'completed': planner.completed, 'timeouts': planner.timeouts,
            'deadline_seconds': float(os.environ.get('DESIGNER_EDITOR_DEADLINE_S', '8'))}

class ImageRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    style: str = Field(default='', max_length=1000)
    offset: int = Field(default=0, ge=0, le=120)
    landscape: bool = True

def clean(value):
    return re.sub('<[^>]+>', '', value or '')[:700]

def public_image(url):
    parsed = urlparse(url)
    return parsed.scheme == 'https' and parsed.hostname in ('upload.wikimedia.org','thumb.wikimedia.org')

@router.post('/images/search')
def search(payload: ImageRequest):
    try:
        with httpx.Client(timeout=25, headers={'User-Agent':'VoiceDeck/1.0 (local presentation editor)'}) as client:
            r = client.get('https://commons.wikimedia.org/w/api.php', params={
                'action':'query','format':'json','generator':'search','gsrsearch':payload.prompt,
                'gsrnamespace':6,'gsrlimit':6,'gsroffset':payload.offset,'prop':'imageinfo',
                'iiprop':'url|extmetadata|mime','iiurlwidth':1000})
            r.raise_for_status()
        items=[]
        for p in sorted(r.json().get('query',{}).get('pages',{}).values(), key=lambda p:p.get('index',0)):
            info=p.get('imageinfo',[{}])[0]
            url=info.get('thumburl') or info.get('url','')
            if not public_image(url) or info.get('mime') not in ('image/jpeg','image/png','image/webp'):
                continue
            meta=info.get('extmetadata',{})
            items.append({'url':url,'title':p.get('title','').removeprefix('File:'),
                'source':info.get('descriptionurl',''),'author':clean(meta.get('Artist',{}).get('value')),
                'license':clean(meta.get('LicenseShortName',{}).get('value')) or 'Проверьте условия на странице источника'})
        return {'items':items}
    except Exception as exc:
        raise HTTPException(502,'Поиск Wikimedia Commons недоступен. Попробуйте позже или измените запрос.') from exc

@router.get('/images/status')
def image_status():
    return {'generation_configured':bool(os.environ.get('DESIGNER_IMAGE_URL')),'provider':'automatic1111'}

@router.post('/images/generate')
def generate(payload: ImageRequest):
    url=os.environ.get('DESIGNER_IMAGE_URL','').rstrip('/')
    if not url:
        raise HTTPException(503,'Генератор не настроен. Укажите DESIGNER_IMAGE_URL для сервера Automatic1111 с включённым API.')
    try:
        with httpx.Client(timeout=180) as client:
            response=client.post(url+'/sdapi/v1/txt2img',json={
                'prompt':payload.prompt+'. '+payload.style,'steps':20,'batch_size':1,
                'width':768 if payload.landscape else 512,'height':512 if payload.landscape else 768})
            response.raise_for_status()
        encoded=response.json()['images'][0].split(',')[-1]
        data=base64.b64decode(encoded,validate=True)
        if len(data)>8*1024*1024 or not data.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError('Invalid generated image')
        return {'items':[{'url':'data:image/png;base64,'+encoded,'title':payload.prompt,
            'source':'','author':'','license':'Сгенерировано'}]}
    except Exception as exc:
        raise HTTPException(502,'Генератор не ответил или вернул неподдерживаемое изображение.') from exc

