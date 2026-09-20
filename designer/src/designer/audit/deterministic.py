"""Детерминированные проверки готовой сцены. Владелец: задача T-03."""
from collections.abc import Callable
from typing import NamedTuple

from designer.audit import checks_density, checks_integrity, checks_layout, checks_template
from designer.contracts import DesignSystem, Finding, Scene

CheckFunc = Callable[[list[Scene], DesignSystem], list[Finding]]


class CheckDef(NamedTuple):
    id: str
    group: str
    title_ru: str
    func: CheckFunc


CHECKS: list[CheckDef] = [
    CheckDef("layout.out_of_bounds", "layout", "Элемент вышел за границы слайда", checks_layout.check_out_of_bounds),
    CheckDef("layout.overlap", "layout", "Наложение содержательных блоков", checks_layout.check_overlap),
    CheckDef("layout.text_overflow", "layout", "Текст не помещается в рамку", checks_layout.check_text_overflow),
    CheckDef("layout.in_margins", "layout", "Содержимое зашло в поля", checks_layout.check_in_margins),
    CheckDef("layout.off_guides", "layout", "Блок не совпадает с направляющей", checks_layout.check_off_guides),
    CheckDef("layout.image_aspect", "layout", "Картинка растянута", checks_layout.check_image_aspect),
    CheckDef("template.font", "template", "Шрифт не из шаблона", checks_template.check_font),
    CheckDef("template.type_scale", "template", "Кегль не из шкалы", checks_template.check_type_scale),
    CheckDef("template.color", "template", "Цвет не из палитры", checks_template.check_color),
    CheckDef("template.pattern", "template", "Паттерн отсутствует в дизайн-системе", checks_template.check_pattern),
    CheckDef("template.contrast", "template", "Низкий контраст текста", checks_template.check_contrast),
    CheckDef("density.bullets", "density", "Слишком много пунктов", checks_density.check_bullets),
    CheckDef("density.bullet_words", "density", "Слишком длинный пункт", checks_density.check_bullet_words),
    CheckDef("density.table", "density", "Слишком большая таблица", checks_density.check_table),
    CheckDef("density.series", "density", "Слишком много рядов на диаграмме", checks_density.check_series),
    CheckDef("density.fill", "density", "Заполнение слайда вне нормы", checks_density.check_fill),
    CheckDef("integrity.placeholder_text", "integrity", "Остался текст-заглушка", checks_integrity.check_placeholder_text),
    CheckDef("integrity.empty", "integrity", "Пустой слайд", checks_integrity.check_empty),
    CheckDef("integrity.chart_labels", "integrity", "Диаграмме не хватает подписей", checks_integrity.check_chart_labels),
    CheckDef("integrity.duplicate", "integrity", "Слайд дублирует другой", checks_integrity.check_duplicate),
]


def run_checks(scenes: list[Scene], ds: DesignSystem) -> list[Finding]:
    """Прогоняет все зарегистрированные проверки и возвращает находки в стабильном порядке."""
    order = {scene.slide_id: idx for idx, scene in enumerate(scenes)}
    findings: list[Finding] = []
    for check in CHECKS:
        findings.extend(check.func(scenes, ds))
    findings.sort(key=lambda f: (order.get(f.slide_id, len(order)), f.check_id, f.element_ids))

    counters: dict[tuple[str, str], int] = {}
    for f in findings:
        key = (f.slide_id, f.check_id)
        n = counters.get(key, 0)
        f.id = f"{f.slide_id}.{f.check_id}.{n}"
        counters[key] = n + 1
    return findings
