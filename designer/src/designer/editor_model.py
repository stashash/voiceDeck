"""Load a cold local model separately from the interactive inference deadline."""
from __future__ import annotations

import asyncio
import os
import time

import httpx

from designer.editor_planner import configuration
from designer.llm.client import auth_headers


def model_options():
    return {'num_ctx': int(os.environ.get('DESIGNER_EDITOR_NUM_CTX', '8192'))}


class EditorModel:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.task: asyncio.Task | None = None
        self.key: tuple | None = None
        self.error = ''
        self.retry_after = 0.0

    async def status(self, prepare=False):
        base, model, native = configuration()
        if not native:
            return {'state': 'ready', 'model': model}
        async with self.lock:
            key = (base, model, model_options()['num_ctx'])
            if self.key != key:
                if self.task:
                    self.task.cancel()
                self.key, self.task, self.error = key, None, ''
            if self.task and not self.task.done():
                return {'state': 'loading', 'model': model}
            if self.error and time.monotonic() < self.retry_after:
                return {'state': 'error', 'model': model, 'message': self.error}
            try:
                async with httpx.AsyncClient(timeout=2, headers=auth_headers()) as client:
                    response = await client.get(base + '/api/ps')
                    response.raise_for_status()
                    loaded = response.json().get('models', [])
                if any(m.get('name', m.get('model')) in (model, model + ':latest')
                       and m.get('context_length', 0) >= key[2] for m in loaded):
                    self.error = ''
                    return {'state': 'ready', 'model': model}
            except (httpx.HTTPError, ValueError, TypeError):
                return {'state': 'error', 'model': model, 'message': 'Нет связи с Ollama. Проверьте, что сервер моделей запущен.'}
            if prepare:
                self.error = ''
                self.task = asyncio.create_task(self._load(base, model, key))
            return {'state': 'loading' if prepare else 'cold', 'model': model}

    async def _load(self, base, model, key):
        try:
            async with asyncio.timeout(60):
                async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=2), headers=auth_headers()) as client:
                    response = await client.post(base + '/api/generate', json={
                        'model': model, 'prompt': '', 'stream': False,
                        'keep_alive': os.environ.get('DESIGNER_EDITOR_KEEP_ALIVE', '30m'),
                        'options': {'num_ctx': key[2]},
                    })
                    response.raise_for_status()
                    if not response.json().get('done'):
                        raise ValueError('Incomplete model load')
        except asyncio.CancelledError:
            raise
        except (TimeoutError, httpx.HTTPError, ValueError):
            if self.key == key:
                self.error = 'Не удалось загрузить модель за 60 секунд. Проверьте Ollama и свободную память; локальные команды доступны.'
                self.retry_after = time.monotonic() + 10


editor_model = EditorModel()
