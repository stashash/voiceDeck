"""Тесты плана презентации: число слайдов по запросу, числа только из брифа."""
import json

import httpx

from designer.llm.client import LlmClient
from designer.plan.planner import make_plan

BRIEF = (
    "Сервис записи к врачу для клиники. За квартал конверсия записи выросла до 20 процентов. "
    "Аудитория — администраторы регистратуры, назначение — показать эффект пилота."
)


def _plan_json(n: int, extra_number: str | None = None) -> dict:
    slides = [{"id": "s1", "kind": "title", "title": "Сервис записи к врачу", "items": []}]
    for i in range(1, n - 1):
        body = "Конверсия записи выросла до 20 процентов."
        if extra_number is not None and i == 1:
            body = f"Показатель вырос ещё на {extra_number} процентов."
        slides.append({
            "id": f"s{i + 1}", "kind": "bullets", "title": "Итог этапа",
            "items": [{"heading": "Пункт", "body": body}],
        })
    slides.append({"id": f"s{n}", "kind": "thanks", "title": "Спасибо"})
    return {"title": "План", "purpose": "показать эффект пилота", "audience": "регистратура", "slides": slides}


def _client_returning(*responses: dict) -> LlmClient:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        index = min(calls["n"], len(responses) - 1)
        calls["n"] += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(responses[index])}}]})

    return LlmClient("http://test/v1", "model", transport=httpx.MockTransport(handler))


def test_plan_has_requested_slide_count():
    client = _client_returning(_plan_json(5))
    plan = make_plan(BRIEF, "показать эффект пилота", "регистратура", 5, client)

    assert len(plan.slides) == 5
    assert plan.slides[0].kind.value == "title"
    assert plan.slides[-1].kind.value == "thanks"


def test_wrong_slide_count_triggers_one_retry():
    client = _client_returning(_plan_json(3), _plan_json(5))
    plan = make_plan(BRIEF, "показать эффект пилота", "регистратура", 5, client)

    assert len(plan.slides) == 5
    assert len(client.call_durations_ms) == 2


def test_number_missing_from_brief_is_dropped():
    client = _client_returning(_plan_json(5, extra_number="42"))
    plan = make_plan(BRIEF, "показать эффект пилота", "регистратура", 5, client)

    full_text = " ".join(item.body for slide in plan.slides for item in slide.items)
    assert "42" not in full_text
    assert "20" in full_text


BRIEF_WITH_PAIR = (
    "Сервис поддержки клиники. Число инцидентов снизилось с 9 до 2. "
    "Аудитория — администраторы регистратуры, назначение — показать эффект пилота."
)


def _plan_json_with_chart(n: int) -> dict:
    slides = [{"id": "s1", "kind": "title", "title": "Сервис поддержки клиники", "items": []}]
    slides.append({
        "id": "s2", "kind": "chart", "title": "Инцидентов стало меньше",
        "items": [],
        "chart": {
            "type": "column", "title": "Инциденты", "categories": ["Было", "Стало"],
            "series": [{"name": "Инциденты", "values": [9, 2]}], "unit": "шт",
        },
    })
    for i in range(2, n - 1):
        slides.append({
            "id": f"s{i + 1}", "kind": "bullets", "title": "Итог этапа",
            "items": [{"heading": "Пункт", "body": "Инцидентов снизилось с 9 до 2."}],
        })
    slides.append({"id": f"s{n}", "kind": "thanks", "title": "Спасибо"})
    return {"title": "План", "purpose": "показать эффект пилота", "audience": "регистратура", "slides": slides}


def test_number_pair_without_visualization_triggers_retry():
    client = _client_returning(_plan_json(5), _plan_json_with_chart(5))
    plan = make_plan(BRIEF_WITH_PAIR, "показать эффект пилота", "регистратура", 5, client)

    assert len(client.call_durations_ms) == 2
    assert any(slide.kind.value in ("chart", "table", "big_number") for slide in plan.slides)
