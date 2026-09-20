"""Проверки целостности содержимого: заглушки, пустые слайды, подписи диаграмм, дубли.

Владелец: задача T-03.
"""
import re

from designer.contracts import DesignSystem, Element, Finding, Scene

_WORD_PLACEHOLDERS = ("xxx", "todo", "текст", "заголовок")
_PHRASE_PLACEHOLDERS = ("lorem ipsum", "вставьте текст")
_TITLE_ROLES = {"title", "heading"}


def _is_placeholder(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    if not normalized:
        return False
    if any(phrase in normalized for phrase in _PHRASE_PLACEHOLDERS):
        return True
    return any(re.search(rf"\b{re.escape(word)}\b", normalized) for word in _WORD_PLACEHOLDERS)


def check_placeholder_text(scenes: list[Scene], ds: DesignSystem) -> list[Finding]:
    findings: list[Finding] = []
    for scene in scenes:
        for el in scene.elements:
            if el.type != "text" or not el.text:
                continue
            if _is_placeholder(el.text):
                findings.append(Finding(
                    id="", slide_id=scene.slide_id, check_id="integrity.placeholder_text", kind="deterministic",
                    severity="error", message=f"В «{el.id}» остался текст-заглушка",
                    element_ids=[el.id], box=el.box, fixable=False,
                ))
    return findings


def _content_elements(scene: Scene) -> list[Element]:
    result = []
    for el in scene.elements:
        if el.type == "text" and el.text.strip():
            result.append(el)
        elif el.type in {"image", "chart", "table"}:
            result.append(el)
    return result


def check_empty(scenes: list[Scene], ds: DesignSystem) -> list[Finding]:
    findings: list[Finding] = []
    for scene in scenes:
        content = _content_elements(scene)
        if not content:
            findings.append(Finding(
                id="", slide_id=scene.slide_id, check_id="integrity.empty", kind="deterministic",
                severity="error", message="Слайд пуст", element_ids=[], box=None, fixable=False,
            ))
        elif len(content) == 1 and content[0].type == "text" and content[0].role in _TITLE_ROLES:
            findings.append(Finding(
                id="", slide_id=scene.slide_id, check_id="integrity.empty", kind="deterministic",
                severity="error", message="На слайде только заголовок",
                element_ids=[content[0].id], box=content[0].box, fixable=False,
            ))
    return findings


def check_chart_labels(scenes: list[Scene], ds: DesignSystem) -> list[Finding]:
    findings: list[Finding] = []
    for scene in scenes:
        for el in scene.elements:
            if el.type != "chart" or el.chart is None:
                continue
            missing = []
            if not el.chart.categories:
                missing.append("категорий")
            if any(not s.name for s in el.chart.series):
                missing.append("имён рядов")
            if not el.chart.unit:
                missing.append("единиц")
            if missing:
                findings.append(Finding(
                    id="", slide_id=scene.slide_id, check_id="integrity.chart_labels", kind="deterministic",
                    severity="warning", message=f"У диаграммы «{el.id}» нет: {', '.join(missing)}",
                    element_ids=[el.id], box=el.box, fixable=False,
                ))
    return findings


def _normalize_scene_text(scene: Scene) -> str:
    parts = [el.text.strip().lower() for el in scene.elements if el.type == "text" and el.text.strip()]
    return re.sub(r"\s+", " ", " ".join(parts))


def check_duplicate(scenes: list[Scene], ds: DesignSystem) -> list[Finding]:
    findings: list[Finding] = []
    seen: dict[str, str] = {}
    for scene in scenes:
        normalized = _normalize_scene_text(scene)
        if not normalized:
            continue
        earlier = seen.get(normalized)
        if earlier is not None:
            findings.append(Finding(
                id="", slide_id=scene.slide_id, check_id="integrity.duplicate", kind="deterministic",
                severity="warning", message=f"Слайд дублирует текст слайда «{earlier}»",
                element_ids=[], box=None, fixable=False,
            ))
        else:
            seen[normalized] = scene.slide_id
    return findings
