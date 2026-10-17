"""Советы по колоде из наработок кинодек: не огрехи вёрстки, а то, что делает слайд слабым для зала.

Два совета считает код: слайд читается дольше трёх секунд и три слайда подряд на одном образце.
Три даёт модель по скиллу `advise-deck`: одинокое число без базы, слайд, который мог бы стоять в чужой
презентации, и слайд без функции. Совет это находка с check_id `advice.*`: экран правки показывает её
у своего слайда, «Применить» отдаёт слайд агенту с текстом совета как просьбой автора.
"""
from __future__ import annotations

import httpx
from pydantic import BaseModel, Field

from designer.contracts import DesignSystem, Finding, Scene
from designer.llm.client import LlmClient, LlmResponseError, ModelLoading
from designer.llm.skills import load_skill

SKILL = "advise-deck"
READ_WORDS = 40
"""Сколько слов кроме заголовка зал читает за три секунды: больше, и экран становится документом."""
_TITLE_ROLES = ("title",)
_SKIP_ROLES = ("decor", "footer")
_RULES = {
    "lonely_number": "advice.lonely_number",
    "not_distinct": "advice.not_distinct",
    "no_function": "advice.no_function",
}


def _words(scene: Scene) -> int:
    return sum(len(el.text.split()) for el in scene.elements
               if el.type == "text" and el.role not in _TITLE_ROLES + _SKIP_ROLES)


def check_three_seconds(scenes: list[Scene], ds: DesignSystem) -> list[Finding]:
    findings = []
    for scene in scenes:
        count = _words(scene)
        if count > READ_WORDS:
            findings.append(Finding(
                id="", slide_id=scene.slide_id, check_id="advice.three_seconds", kind="deterministic",
                severity="warning",
                message=f"Слайд читается дольше трёх секунд: {count} слов кроме заголовка. Оставьте на слайде "
                        "главное в коротких пунктах, пояснения перенесите в заметки докладчика."))
    return findings


def check_same_view(scenes: list[Scene], ds: DesignSystem) -> list[Finding]:
    findings = []
    for index in range(2, len(scenes)):
        if scenes[index].pattern_id == scenes[index - 1].pattern_id == scenes[index - 2].pattern_id:
            findings.append(Finding(
                id="", slide_id=scenes[index].slide_id, check_id="advice.same_view", kind="deterministic",
                severity="warning",
                message="Третий слайд подряд одного вида: зал не видит, что мысль сменилась. Покажите эту мысль "
                        "иначе: крупным числом, сравнением или схемой шагов."))
    return findings


class _Advice(BaseModel):
    slide_id: str
    rule: str = Field(description="lonely_number, not_distinct или no_function")
    advice: str = Field(max_length=300)


class _Answer(BaseModel):
    items: list[_Advice] = Field(max_length=12)


def _deck_text(scenes: list[Scene]) -> str:
    blocks = []
    for scene in scenes:
        texts = [el.text.strip() for el in scene.elements if el.type == "text" and el.text.strip()
                 and el.role not in _SKIP_ROLES]
        blocks.append(f"[{scene.slide_id}]\n" + "\n".join(texts))
    return "\n\n".join(blocks)


def advise_deck(scenes: list[Scene], client: LlmClient) -> list[Finding]:
    """Советы модели по всей колоде одним запросом. Сбой модели советов не даёт и аудит не роняет."""
    if not scenes:
        return []
    skill = load_skill(SKILL)
    try:
        data = client.complete_json(system=skill.render(), user=_deck_text(scenes),
                                    schema=_Answer.model_json_schema(), params=skill.params)
        answer = _Answer.model_validate(data)
    except (LlmResponseError, ModelLoading, ValueError, httpx.HTTPError):
        return []
    known = {scene.slide_id for scene in scenes}
    seen: set[tuple[str, str]] = set()
    findings = []
    for item in answer.items:
        check_id = _RULES.get(item.rule)
        if check_id is None or item.slide_id not in known or (item.slide_id, check_id) in seen or not item.advice.strip():
            continue
        seen.add((item.slide_id, check_id))
        findings.append(Finding(id=f"{item.slide_id}.{check_id}.0", slide_id=item.slide_id, check_id=check_id,
                                kind="contextual", severity="warning", message=item.advice.strip()))
    return findings
