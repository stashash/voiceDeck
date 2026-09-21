"""Проверки плотности содержимого: пункты, таблицы, диаграммы, заполнение слайда.

Владелец: задача T-03.
"""
from designer.contracts import DesignSystem, Finding, Scene, SlideKind

# Помощники deterministic.py импортируются внутри функций (см. checks_layout.py):
# на уровне модуля это закольцовывает загрузку реестра проверок.

_MAX_BULLETS = 6
_MAX_BULLET_WORDS = 15
_MAX_TABLE_ROWS = 7
_MAX_TABLE_COLS = 5
_MAX_SERIES = 5
_MIN_FILL = 0.25
_MAX_FILL = 0.75
# Слайды, где мало текста по жанру: заполнение с ними не сверяется (T-29).
_FILL_EXCLUDED_KINDS = frozenset({SlideKind.title, SlideKind.section, SlideKind.quote, SlideKind.thanks})


def _bullet_lines(text: str) -> list[str]:
    return [line.strip() for line in text.split("\n") if line.strip()]


def check_bullets(scenes: list[Scene], ds: DesignSystem) -> list[Finding]:
    from designer.audit.deterministic import describe_element
    findings: list[Finding] = []
    for scene in scenes:
        for el in scene.elements:
            if el.type != "text" or not el.text:
                continue
            lines = _bullet_lines(el.text)
            if len(lines) > _MAX_BULLETS:
                findings.append(Finding(
                    id="", slide_id=scene.slide_id, check_id="density.bullets", kind="deterministic",
                    severity="warning",
                    message=f"В {describe_element(el)} {len(lines)} пунктов вместо не более {_MAX_BULLETS}",
                    element_ids=[el.id], box=el.box, fixable=False,
                ))
    return findings


def check_bullet_words(scenes: list[Scene], ds: DesignSystem) -> list[Finding]:
    from designer.audit.deterministic import describe_element
    findings: list[Finding] = []
    for scene in scenes:
        for el in scene.elements:
            if el.type != "text" or not el.text:
                continue
            for line in _bullet_lines(el.text):
                words = line.split()
                if len(words) > _MAX_BULLET_WORDS:
                    findings.append(Finding(
                        id="", slide_id=scene.slide_id, check_id="density.bullet_words", kind="deterministic",
                        severity="warning",
                        message=f"Пункт «{line[:30]}…» в {describe_element(el)} длиннее {_MAX_BULLET_WORDS} слов",
                        element_ids=[el.id], box=el.box, fixable=False,
                    ))
    return findings


def check_table(scenes: list[Scene], ds: DesignSystem) -> list[Finding]:
    from designer.audit.deterministic import describe_element
    findings: list[Finding] = []
    for scene in scenes:
        for el in scene.elements:
            if el.type != "table" or el.table is None:
                continue
            if len(el.table.rows) > _MAX_TABLE_ROWS or len(el.table.columns) > _MAX_TABLE_COLS:
                findings.append(Finding(
                    id="", slide_id=scene.slide_id, check_id="density.table", kind="deterministic",
                    severity="warning",
                    message=(f"{describe_element(el).capitalize()}: {len(el.table.rows)} строк, "
                             f"{len(el.table.columns)} колонок — больше нормы"),
                    element_ids=[el.id], box=el.box, fixable=False,
                ))
    return findings


def check_series(scenes: list[Scene], ds: DesignSystem) -> list[Finding]:
    from designer.audit.deterministic import describe_element
    findings: list[Finding] = []
    for scene in scenes:
        for el in scene.elements:
            if el.type != "chart" or el.chart is None:
                continue
            if len(el.chart.series) > _MAX_SERIES:
                findings.append(Finding(
                    id="", slide_id=scene.slide_id, check_id="density.series", kind="deterministic",
                    severity="warning",
                    message=f"На {describe_element(el)} {len(el.chart.series)} рядов вместо не более {_MAX_SERIES}",
                    element_ids=[el.id], box=el.box, fixable=False,
                ))
    return findings


def check_fill(scenes: list[Scene], ds: DesignSystem) -> list[Finding]:
    """Заполнение считается по содержимому без оформления (T-29): фон, декор и
    колонтитул из расчёта исключены. Титул, раздел, цитата и финальный слайд
    по жанру держатся на малом тексте — проверка их пропускает."""
    from designer.audit.deterministic import DECOR_ROLES, pattern_by_id
    patterns = pattern_by_id(ds)
    findings: list[Finding] = []
    for scene in scenes:
        pattern = patterns.get(scene.pattern_id)
        if pattern is not None and pattern.kind in _FILL_EXCLUDED_KINDS:
            continue
        els = [el for el in scene.elements if el.role not in DECOR_ROLES]
        if not els:
            area = 0.0
        else:
            min_x = min(el.box[0] for el in els)
            min_y = min(el.box[1] for el in els)
            max_x = max(el.box[0] + el.box[2] for el in els)
            max_y = max(el.box[1] + el.box[3] for el in els)
            area = max(0.0, max_x - min_x) * max(0.0, max_y - min_y)
        if area < _MIN_FILL or area > _MAX_FILL:
            findings.append(Finding(
                id="", slide_id=scene.slide_id, check_id="density.fill", kind="deterministic",
                severity="warning",
                message=f"Содержимое занимает {area * 100:.0f}% слайда — вне диапазона 25–75%",
                element_ids=[el.id for el in els], box=None, fixable=False,
            ))
    return findings
