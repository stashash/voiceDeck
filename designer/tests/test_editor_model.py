import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from designer.editor_model import EditorModel


class EditorModelTests(unittest.IsolatedAsyncioTestCase):
    async def test_cold_load_is_shared_and_does_not_block_status(self):
        runtime = EditorModel()
        client = MagicMock()
        client.get = AsyncMock(return_value=MagicMock(json=lambda: {'models': []}))
        started, finish = asyncio.Event(), asyncio.Event()

        async def load(*args, **kwargs):
            self.assertEqual(kwargs['json']['options']['num_ctx'], 8192)
            self.assertEqual(kwargs['json']['keep_alive'], '30m')
            started.set()
            await finish.wait()
            return MagicMock(json=lambda: {'done': True})

        client.post = AsyncMock(side_effect=load)
        with patch('designer.editor_model.configuration', return_value=('http://ollama', 'model', True)), \
             patch('designer.editor_model.model_options', return_value={'num_ctx': 8192}), \
             patch('designer.editor_model.httpx.AsyncClient') as factory:
            factory.return_value.__aenter__.return_value = client
            self.assertEqual((await runtime.status(True))['state'], 'loading')
            await started.wait()
            self.assertEqual((await runtime.status(True))['state'], 'loading')
            client.post.assert_awaited_once()
            finish.set()
            await runtime.task
            client.get.return_value.json = lambda: {'models': [{'name': 'model', 'context_length': 8192}]}
            self.assertEqual((await runtime.status())['state'], 'ready')

    async def test_failed_load_is_visible_and_not_retried_in_a_loop(self):
        runtime = EditorModel()
        client = MagicMock()
        client.get = AsyncMock(return_value=MagicMock(json=lambda: {'models': []}))
        client.post = AsyncMock(side_effect=TimeoutError)
        with patch('designer.editor_model.configuration', return_value=('http://ollama', 'model', True)), \
             patch('designer.editor_model.httpx.AsyncClient') as factory:
            factory.return_value.__aenter__.return_value = client
            await runtime.status(True)
            await runtime.task
            result = await runtime.status(True)
            self.assertEqual(result['state'], 'error')
            self.assertIn('загрузить', result['message'])
            client.post.assert_awaited_once()

    async def test_insufficient_loaded_context_requires_preparation(self):
        runtime = EditorModel()
        client = MagicMock()
        client.get = AsyncMock(return_value=MagicMock(json=lambda: {'models': [{'name': 'model', 'context_length': 4096}]}))
        with patch('designer.editor_model.configuration', return_value=('http://ollama', 'model', True)), \
             patch('designer.editor_model.model_options', return_value={'num_ctx': 8192}), \
             patch('designer.editor_model.httpx.AsyncClient') as factory:
            factory.return_value.__aenter__.return_value = client
            self.assertEqual((await runtime.status())['state'], 'cold')
            self.assertIsNone(runtime.task)
