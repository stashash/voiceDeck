"""Bounded interactive planning, separate from long-running deck generation."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
from collections import OrderedDict
from dataclasses import dataclass

import httpx
from fastapi import HTTPException
from pydantic import ValidationError

from designer.agents import load_assignments
from designer.api.editor_plan import Plan, SYSTEM
from designer.llm.client import auth_headers
from designer.settings import load_settings


def validate_table_writes(plan: Plan, instruction: str):
    if any(op.op == 'table_cell' and not op.value for op in plan.operations):
        if not re.search(r'\b(?:очист\w*|опустош\w*|пуст\w*|clear|empty)\b|удали\w* содержимое', instruction, re.I):
            raise ValueError('table_cell.value is empty, but the user did not request clearing a cell. Copy the requested new value from instruction into value as a string. Do not put it only in summary.')


def validate_explicit_properties(plan: Plan, instruction: str):
    if not plan.operations:
        return
    # Check literal property specifications, not numbers embedded in quoted slide copy.
    command = re.sub(r'«[^»]*»|"[^"]*"', '', instruction)
    fields = {'слева': 'x', 'сверху': 'y', 'ширина': 'width', 'высота': 'height',
              'размер текста': 'size', 'размер шрифта': 'size'}
    missing = []
    for match in re.finditer(r'(?:^|[,.!?;]\s*)(слева|сверху|ширина|высота|размер текста|размер шрифта)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?=[,.;!?]|$)', command, re.I):
        key, value = fields[match[1].lower()], float(match[2])
        if not any(op.op in ('add', 'update') and getattr(op.props, key) == value for op in plan.operations):
            missing.append(f'{key}={value:g}')
    if missing:
        raise ValueError('Requested properties missing from executable props: ' + ', '.join(missing) +
                         '. Include them in add/update props, before size/color in JSON schema order; summary is not an edit.')


def configuration() -> tuple[str, str, bool]:
    explicit = os.environ.get('DESIGNER_EDITOR_LLM_URL', '').strip()
    if explicit:
        return (explicit.rstrip('/').removesuffix('/v1'),
                os.environ.get('DESIGNER_EDITOR_LLM_MODEL') or 'qwen3:8b',
                os.environ.get('DESIGNER_EDITOR_LLM_PROTOCOL', 'ollama') == 'ollama')
    settings = load_settings()
    assignment = load_assignments()['live']
    if assignment.startswith('cli:') and not settings.live_llm_url:
        raise HTTPException(503, 'Для голосовых правок выберите локальную модель или DESIGNER_EDITOR_LLM_URL. CLI предназначен для фоновых задач.')
    return ((settings.live_llm_url or settings.llm_url).rstrip('/').removesuffix('/v1'),
            settings.live_llm_model or assignment.removeprefix('local:') or settings.llm_model, False)


async def complete_plan(instruction: str, context: str) -> dict:
    base, model, native = configuration()
    try:
        document = json.loads(context) if context else {}
    except ValueError as exc:
        raise HTTPException(422, 'Некорректный контекст документа') from exc
    messages = [{'role': 'system', 'content': SYSTEM},
                {'role': 'user', 'content': json.dumps({'instruction': instruction, 'context': document}, ensure_ascii=False)}]
    # The outer task owns the total deadline, including connection, body and repair.
    async with httpx.AsyncClient(timeout=httpx.Timeout(30, connect=2), headers=auth_headers()) as client:
        for attempt in range(2):
            if native:
                url = base + '/api/chat'
                body = {'model': model, 'messages': messages, 'stream': False, 'think': False,
                        'keep_alive': os.environ.get('DESIGNER_EDITOR_KEEP_ALIVE', '30m'),
                        'format': Plan.model_json_schema(),
                        'options': {'temperature': 0, 'num_predict': 1800, 'num_ctx': int(os.environ.get('DESIGNER_EDITOR_NUM_CTX', '8192'))}}
            else:
                url = base + '/v1/chat/completions'
                # Без reasoning_effort Qwen3.8-27B в LM Studio думает 600+ токенов: план идёт 20 с вместо 8.
                body = {'model': model, 'messages': messages, 'stream': False,
                        'temperature': 0, 'max_tokens': 1800, 'reasoning_effort': 'none',
                        'response_format': {'type': 'json_schema', 'json_schema': {
                            'name': 'editor_plan', 'strict': True, 'schema': Plan.model_json_schema()}}}
            response = await client.post(url, json=body)
            if response.status_code == 400 and 'reasoning' in response.text.lower() and 'reasoning_effort' in body:
                # Сервер не знает параметра: модель думает по своему умолчанию, но отвечает.
                body.pop('reasoning_effort')
                response = await client.post(url, json=body)
            response.raise_for_status()
            raw = response.json()
            content = raw['message']['content'] if native else raw['choices'][0]['message']['content']
            try:
                plan = Plan.model_validate_json(content)
                validate_table_writes(plan, instruction)
                validate_explicit_properties(plan, instruction)
                return plan.model_dump(exclude_none=True)
            except (ValidationError, ValueError) as exc:
                if attempt:
                    raise HTTPException(502, 'Модель вернула некорректный план. Документ не изменён.')
                messages.extend([{'role': 'assistant', 'content': content[:16000]},
                                 {'role': 'user', 'content': f'Исправь JSON. Ошибка проверки: {str(exc)[:1800]}. Выполни исходную просьбу полностью; не добавляй свойства вне схемы.'}])
    raise HTTPException(502, 'Пустой ответ модели')


@dataclass
class Job:
    fingerprint: str
    task: asyncio.Task | None
    expires: float
    result: dict | None = None
    error: tuple[int, str] | None = None


class Planner:
    def __init__(self):
        self.jobs: OrderedDict[str, Job] = OrderedDict()
        self.completed = 0
        self.timeouts = 0

    def prune(self):
        now = time.monotonic()
        for key, job in list(self.jobs.items()):
            if job.task is None and (job.expires < now or len(self.jobs) > 128):
                del self.jobs[key]

    def cancel(self, request_id: str):
        self.prune()
        job = self.jobs.get(request_id)
        if job and job.task:
            job.error = (409, 'Запрос отменён. Документ не изменён.')
            job.task.cancel()
        elif job is None:
            # A stop can overtake its POST on another HTTP connection.
            self.jobs[request_id] = Job('', None, time.monotonic() + 60, error=(409, 'Запрос отменён'))

    async def run(self, request_id: str, instruction: str, context: str) -> dict:
        self.prune()
        fingerprint = hashlib.sha256((instruction + '\0' + context).encode()).hexdigest()
        job = self.jobs.get(request_id)
        if job:
            if job.fingerprint and job.fingerprint != fingerprint:
                raise HTTPException(409, 'Идентификатор запроса уже использован для другой команды')
            if job.error:
                raise HTTPException(*job.error)
            if job.result is not None:
                return job.result
            raise HTTPException(409, 'Этот запрос уже выполняется')
        if any(j.task is not None for j in self.jobs.values()):
            raise HTTPException(429, 'Модель занята другим запросом. Быстрые команды доступны.')
        budget = max(.05, min(30, float(os.environ.get('DESIGNER_EDITOR_DEADLINE_S', '20'))))
        task = asyncio.create_task(complete_plan(instruction, context))
        job = Job(fingerprint, task, time.monotonic() + 60)
        self.jobs[request_id] = job
        started = time.monotonic()
        try:
            result = await asyncio.wait_for(task, budget)
            job.result = {**result, 'request_id': request_id, 'elapsed_ms': round((time.monotonic() - started) * 1000)}
            self.completed += 1
            return job.result
        except TimeoutError:
            self.timeouts += 1
            job.error = (504, 'Модель не уложилась в срок. Документ не изменён; быстрые команды доступны.')
        except asyncio.CancelledError:
            task.cancel()
            job.error = (409, 'Запрос отменён. Документ не изменён.')
        except HTTPException as exc:
            job.error = (exc.status_code, str(exc.detail))
        except (httpx.HTTPError, ValueError, KeyError, IndexError):
            job.error = (503, 'Модель недоступна или вернула неверный ответ. Документ не изменён.')
        finally:
            job.task = None
            job.expires = time.monotonic() + 60
        raise HTTPException(*(job.error or (503, 'Ошибка планирования')))


planner = Planner()
