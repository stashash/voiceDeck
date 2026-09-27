import os
import unittest
from unittest.mock import Mock, AsyncMock, patch
import asyncio
import json
from fastapi import HTTPException
from designer.api.editor import ImageRequest, IntentRequest, generate, intent, public_image
from designer.api.editor_plan import Operation
from designer.editor_planner import complete_plan

class EditorApiTests(unittest.TestCase):
    def test_normalizes_slide_number_and_requires_destination(self):
        self.assertEqual(Operation.model_validate({'op':'slide_select','value':'2'}).index,2)
        with self.assertRaises(ValueError):
            Operation.model_validate({'op':'slide_select'})
    def test_hosts(self):
        self.assertTrue(public_image('https://upload.wikimedia.org/a.png'))
        self.assertTrue(public_image('https://thumb.wikimedia.org/a.png'))
        self.assertFalse(public_image('http://127.0.0.1/a.png'))
        self.assertFalse(public_image('https://upload.wikimedia.org.attacker/a.png'))

    def test_generator_missing(self):
        with patch.dict(os.environ,{'DESIGNER_IMAGE_URL':''}):
            with self.assertRaises(HTTPException) as raised:
                generate(ImageRequest(prompt='A courier'))
        self.assertEqual(raised.exception.status_code,503)

    def test_validated_plan(self):
        client=AsyncMock()
        response=Mock();response.json.return_value={'choices':[{'message':{'content':json.dumps({'operations':[{'op':'add','props':{'kind':'title','text':'Delivery'}}],'clarification':'','summary':'Created'})}}]}
        client.post.return_value=response
        with patch('designer.editor_planner.configuration',return_value=('http://local','model',False)),patch('designer.editor_planner.httpx.AsyncClient') as factory:
            factory.return_value.__aenter__.return_value=client
            plan=asyncio.run(complete_plan('Create a delivery slide','{}'))
        self.assertEqual(plan['operations'][0]['props']['text'],'Delivery')
        factory.return_value.__aexit__.assert_awaited_once()

    def test_rejects_unknown_operation(self):
        client=AsyncMock()
        response=Mock();response.json.return_value={'message':{'content':json.dumps({'operations':[{'op':'execute_script'}],'clarification':'','summary':''})}}
        client.post.return_value=response
        with patch('designer.editor_planner.configuration',return_value=('http://local','model',True)),patch('designer.editor_planner.httpx.AsyncClient') as factory:
            factory.return_value.__aenter__.return_value=client
            with self.assertRaises(HTTPException):
                asyncio.run(complete_plan('Test','{}'))

    def test_retries_invalid_native_plan(self):
        import json
        client=AsyncMock()
        first=Mock();first.json.return_value={'message':{'content':json.dumps({'operations':[{'op':'add','props':{'text':'Missing kind'}}],'clarification':'','summary':''})}}
        second=Mock();second.json.return_value={'message':{'content':json.dumps({'operations':[{'op':'add','props':{'kind':'title','text':'Fixed'}}],'clarification':'','summary':'Created'})}}
        client.post.side_effect=[first,second]
        with patch.dict(os.environ,{'DESIGNER_EDITOR_LLM_URL':'http://localhost:11434/v1'}),patch('designer.editor_planner.httpx.AsyncClient') as factory:
            factory.return_value.__aenter__.return_value=client
            plan=asyncio.run(complete_plan('Create title','{}'))
        self.assertEqual(plan['operations'][0]['props']['kind'],'title')
        self.assertEqual(client.post.call_count,2)

if __name__=='__main__':
    unittest.main()
