import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from designer.editor_planner import Planner, validate_table_writes, validate_explicit_properties
from designer.api.editor_plan import Plan
from pydantic import ValidationError

PLAN = {'operations': [], 'clarification': 'Which object?', 'summary': ''}


class PlannerTests(unittest.IsolatedAsyncioTestCase):
    def test_explicit_dimensions_must_be_executable_not_only_in_summary(self):
        plan = Plan.model_validate({'operations': [{'op': 'update', 'props': {'kind': 'text', 'size': 32}}],
                                    'clarification': '', 'summary': 'x=100 width=400 height=150'})
        with self.assertRaisesRegex(ValueError, 'x=100, width=400, height=150'):
            validate_explicit_properties(plan, 'Преврати карточку в текст. Размер текста 32, слева 100, ширина 400, высота 150.')
        validate_explicit_properties(plan, 'Добавь текст «ширина 400, высота 150». Размер текста 32.')
        plan.operations[0].props.x = 100
        plan.operations[0].props.width = 400
        plan.operations[0].props.height = 150
        validate_explicit_properties(plan, 'Размер текста 32, слева 100, ширина 400, высота 150.')

    def test_table_replacement_must_not_silently_erase_data(self):
        with self.assertRaises(ValidationError):
            Plan.model_validate({'operations': [{'op': 'table_cell', 'row': 2, 'column': 2}],
                                 'clarification': '', 'summary': 'Price changed to 900'})
        plan = Plan.model_validate({'operations': [{'op': 'table_cell', 'row': 2, 'column': 2, 'value': ''}],
                                    'clarification': '', 'summary': 'Price changed to 900'})
        with self.assertRaisesRegex(ValueError, 'table_cell.value is empty'):
            validate_table_writes(plan, 'Измени цену книги на 900, остальные ячейки сохрани')
        validate_table_writes(plan, 'Очисти ячейку 2, 2')

    def test_clarification_must_not_mix_with_executable_operations(self):
        with self.assertRaises(ValidationError):
            Plan.model_validate({'operations': [{'op': 'table_cell', 'targets': ['e1'], 'row': 2, 'column': 2, 'value': ''}],
                                 'clarification': 'What price?', 'summary': ''})
        plan = Plan.model_validate({'operations': [{'op': 'table_cell', 'targets': ['e1'], 'row': 2, 'column': 2, 'value': '900'}],
                                    'clarification': '', 'summary': 'Updated'})
        self.assertEqual(plan.operations[0].value, '900')

    async def test_deadline_releases_slot_and_next_request_works(self):
        planner = Planner()
        async def hang(*args):
            await asyncio.sleep(30)
        with patch.dict(os.environ, {'DESIGNER_EDITOR_DEADLINE_S': '.05'}), patch('designer.editor_planner.complete_plan', side_effect=hang):
            with self.assertRaises(HTTPException) as error:
                await planner.run('slow', 'test', '{}')
            self.assertEqual(error.exception.status_code, 504)
        self.assertEqual(planner.timeouts, 1)
        with patch('designer.editor_planner.complete_plan', new=AsyncMock(return_value=PLAN)):
            self.assertEqual((await planner.run('next', 'test', '{}'))['operations'], [])

    async def test_busy_cancellation_and_tombstone(self):
        planner = Planner()
        started = asyncio.Event()
        async def hang(*args):
            started.set()
            await asyncio.sleep(30)
        with patch('designer.editor_planner.complete_plan', side_effect=hang):
            task = asyncio.create_task(planner.run('one', 'test', '{}'))
            await started.wait()
            with self.assertRaises(HTTPException) as error:
                await planner.run('two', 'test', '{}')
            self.assertEqual(error.exception.status_code, 429)
            planner.cancel('one')
            with self.assertRaises(HTTPException) as error:
                await task
            self.assertEqual(error.exception.status_code, 409)
        planner.cancel('overtaken')
        with self.assertRaises(HTTPException):
            await planner.run('overtaken', 'test', '{}')

    async def test_retry_is_deduplicated_and_id_cannot_be_reused(self):
        planner = Planner()
        with patch('designer.editor_planner.complete_plan', new=AsyncMock(return_value=PLAN)) as completion:
            first = await planner.run('same', 'test', '{}')
            self.assertEqual(await planner.run('same', 'test', '{}'), first)
            completion.assert_awaited_once()
            with self.assertRaises(HTTPException) as error:
                await planner.run('same', 'different', '{}')
            self.assertEqual(error.exception.status_code, 409)
