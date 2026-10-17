import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import HTTPException, FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from designer.meaning import MeaningDraft, MeaningRequest, expand_meaning, validate_evidence, local_configuration


DRAFT = {'main_idea': 'Рост', 'explanation': 'Объяснение',
         'details': [{'text': 'Проверьте результат 99%', 'role': 'пример', 'supports': 'Раскрывает рост'}],
         'evidence': [{'source_id': 'slide1', 'quote': 'Рост 5%'}], 'caveats': ['Нет доказательства причинности'],
         'recommendation': 'update_current', 'slide_draft': None}


class MeaningTests(unittest.IsolatedAsyncioTestCase):
    def payload(self):
        return MeaningRequest(instruction='Раскрой мысль', slide_id='slide1', version='abc',
                              context={'sources': {'slide1': 'Рост 5%'}})

    def test_contract_rejects_missing_malformed_or_executable_fields(self):
        for data in ({}, {**DRAFT, 'main_idea': ''}, {**DRAFT, 'operations': []}, {**DRAFT, 'recommendation': 'write'}):
            with self.assertRaises(ValidationError):
                MeaningDraft.model_validate(data)

    def test_evidence_must_be_exact_context_and_generated_claims_never_verified(self):
        draft = MeaningDraft.model_validate(DRAFT)
        self.assertEqual(validate_evidence(draft, {'slide1': 'Рост 5%'})['verification'], 'requires_confirmation')
        for sources in ({}, {'slide1': 'Рост 6%'}):
            with self.assertRaises(ValueError):
                validate_evidence(draft, sources)

    def test_remote_model_is_rejected(self):
        for url in ('https://api.example.com', 'https://8.8.8.8', 'http://user:pass@localhost'):
            with patch('designer.meaning.configuration', return_value=(url, 'model', False)):
                with self.assertRaises(HTTPException):
                    local_configuration()

    def test_editor_route_validates_request_and_exposes_preview_only(self):
        from designer.api.editor import router
        app = FastAPI()
        app.include_router(router)
        with TestClient(app) as client, patch('designer.api.editor.expand_meaning', new=AsyncMock(return_value={**DRAFT, 'verification': 'requires_confirmation'})) as expand:
            self.assertEqual(client.post('/editor/meaning/expand', json={}).status_code, 422)
            response = client.post('/editor/meaning/expand', json=self.payload().model_dump())
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['verification'], 'requires_confirmation')
            expand.assert_awaited_once()

    async def complete(self, content):
        response = httpx.Response(200, json={'message': {'content': content}}, request=httpx.Request('POST', 'http://localhost/api/chat'))
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post.return_value = response
        with patch('designer.meaning.configuration', return_value=('http://localhost:11434', 'local-model', True)), patch('designer.meaning.httpx.AsyncClient', return_value=client):
            result = await expand_meaning(self.payload())
        body = client.post.call_args.kwargs['json']
        self.assertEqual(body['model'], 'local-model')
        self.assertIn('Рост 5%', body['messages'][1]['content'])
        self.assertIn('main_idea', body['format']['properties'])
        return result

    async def test_local_model_receives_context_and_returns_bound_unverified_draft(self):
        result = await self.complete(json.dumps(DRAFT))
        self.assertEqual((result['slide_id'], result['version']), ('slide1', 'abc'))
        self.assertEqual(result['verification'], 'requires_confirmation')

    async def test_bad_model_responses_fail_without_a_document_write(self):
        for content in ('', '{}', 'not json', json.dumps({**DRAFT, 'evidence': [{'source_id': 'invented', 'quote': '99%'}]})):
            with self.assertRaises(HTTPException) as error:
                await self.complete(content)
            self.assertEqual(error.exception.status_code, 502)

    async def test_unavailable_model_and_timeout_are_human_readable(self):
        for failure, code in ((httpx.ConnectError('offline'), 502), (TimeoutError(), 504)):
            client = AsyncMock()
            client.__aenter__.return_value = client
            client.post.side_effect = failure
            with patch('designer.meaning.configuration', return_value=('http://localhost:11434', 'local', True)), patch('designer.meaning.httpx.AsyncClient', return_value=client):
                with self.assertRaises(HTTPException) as error:
                    await expand_meaning(self.payload())
                self.assertEqual(error.exception.status_code, code)
                self.assertIn('Правки сохранены', error.exception.detail)
