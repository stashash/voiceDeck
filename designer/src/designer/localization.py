"""Presentation display locale. Source snapshots, provenance and values are immutable.

The vocabulary is deliberately bounded. Unknown names are retained for human review;
we never ask a model to translate source rows or infer a brand's meaning.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Literal

from designer.contracts import DeckPlan, SlideIntent
from designer.insights.labels import display_label, field_label

Language = Literal["ru", "en"]


def validate_language(language: str) -> Language:
    if language not in {"ru", "en"}:
        raise ValueError("Supported presentation languages: ru, en")
    return language


def language_instruction(language: str) -> str:
    validate_language(language)
    target = "Russian" if language == "ru" else "English"
    return (f"\nRequired presentation language: {target} ({language}). This overrides any language "
            "default in the template. Write all audience-facing titles, body text, labels, captions "
            "and notes in this language. Preserve brand/product names, URLs, IDs, exact numbers "
            "and units. Do not copy template filler text or translate proper names speculatively. "
            f"Set the plan language to {language}.")


def prose_language_violations(slides: list[SlideIntent], language: str) -> list[str]:
    """Catch an ignored model locale; short names/abbreviations are not rejected."""
    text = " ".join(
        part for slide in slides for part in
        [slide.title, slide.key_message, *(item.heading + " " + item.body for item in slide.items)])
    text = re.sub(r"https?://\S+|\b[A-Z][A-Z0-9_-]+\b", "", text)
    latin, cyrillic = len(re.findall("[A-Za-z]", text)), len(re.findall("[А-Яа-яЁё]", text))
    foreign, target = (latin, cyrillic) if language == "ru" else (cyrillic, latin)
    if foreign > 120 and foreign > target:
        return [f"основной язык текста не соответствует запрошенному {language}; переведи прозу, сохрани числа и имена"]
    return []


_CATEGORIES = {
    "channel": {"Search": "Поиск", "Social": "Социальные сети", "Partners": "Партнёры", "Email": "Электронная почта"},
    "status": {"Resolved": "Решено", "Pending": "В ожидании", "Escalated": "На эскалации"},
    "region": {"North": "Север", "Central": "Центр", "South": "Юг", "East": "Восток", "West": "Запад"},
    "note": {"observed zero": "Наблюдаемое нулевое значение", "actual missing": "Факт отсутствует",
             "planned missing": "План отсутствует", "actual zero": "Фактическое значение равно нулю"},
}
_FIELD_ALIASES = {"канал": "channel", "статус": "status", "outcome": "status", "результат": "status", "регион": "region",
                  "примечание": "note", "период": "period", "наименование": "label", "название": "name"}
_NUMBER = re.compile(r"(?<!\w)[+-]?\d+(?:[.,]\d+)?")


def category_label(value: str, field: str, language: str) -> str:
    key = _FIELD_ALIASES.get(field.lower(), field.lower())
    terms = _CATEGORIES.get(key, {})
    pairs = terms if language == "ru" else {v: k for k, v in terms.items()}
    translated = next((v for k, v in pairs.items() if k.casefold() == value.casefold()), None)
    if translated is not None:
        return translated
    # Full cell patterns only. The numeric identifier remains byte-for-byte intact.
    patterns = ([(r"Week (\d+)", r"Неделя \1")] if key == "period" else
                [(r"Reference item (\d+)", r"Запись справочника \1"), (r"Item (\d+)", r"Позиция \1")]
                if key in {"label", "name"} else [])
    if language == "en":
        patterns = ([(r"Неделя (\d+)", r"Week \1")] if key == "period" else
                    [(r"Запись справочника (\d+)", r"Reference item \1"), (r"Позиция (\d+)", r"Item \1")]
                    if key in {"label", "name"} else [])
    for pattern, replacement in patterns:
        if re.fullmatch(pattern, value, re.I):
            return re.sub(pattern, replacement, value, flags=re.I)
    return value


def _replace_labels(text: str, mapping: dict[str, str]) -> str:
    """Replace observed source labels at word boundaries, in analytical prose only."""
    keys = sorted((key for key in mapping if key and mapping[key] != key), key=len, reverse=True)
    if not keys:
        return text
    pattern = re.compile(r"(?<![\w./:@-])(?:" + "|".join(re.escape(k) for k in keys) + r")(?![\w/@-])")
    return pattern.sub(lambda m: mapping[m.group()], text)


def _display_mapping(slide: SlideIntent, language: str) -> dict[str, str]:
    mapping = {}
    fields = slide.provenance.columns if slide.provenance else []
    for field in fields:
        label, unit = field_label(field, language)
        translated = label + (f", {unit}" if unit else "")
        mapping[field] = translated
        mapping[field.replace("_", " ")] = translated
        mapping[field_label(field, "ru")[0]] = label
    if slide.chart:
        for category in slide.chart.categories:
            for field in fields:
                translated = category_label(category, field, language)
                if translated != category:
                    mapping[category] = translated
    return mapping


def _source_note(slide: SlideIntent, language: str) -> str:
    p = slide.provenance
    if p is None:
        return slide.source_note
    # File/sheet names are source identifiers. Context prose remains in original notes.
    source = f"{'Источник' if language == 'ru' else 'Source'}: {p.file_name}"
    if p.sheet:
        source += f" · {'лист' if language == 'ru' else 'sheet'} «{p.sheet}»"
    if language == "ru":
        coverage = f"Охват: {len(p.row_lines)} из {p.total_rows} строк; исключено: {len(p.excluded_row_lines)}."
        if p.page_count:
            coverage += f" Страница {p.page_index}/{p.page_count}."
    else:
        coverage = f"Coverage: {len(p.row_lines)} of {p.total_rows} rows; excluded: {len(p.excluded_row_lines)}."
        if p.page_count:
            coverage += f" Page {p.page_index}/{p.page_count}."
    if len(p.displayed_row_lines) < len(p.row_lines):
        coverage += (f" Показано: {len(p.displayed_row_lines)}." if language == "ru" else
                     f" Shown: {len(p.displayed_row_lines)}.")
    return source + "\n" + coverage


def localize_slide(slide: SlideIntent, language: str = "ru") -> SlideIntent:
    """Return a display copy. Do not mutate any numerical/source evidence."""
    validate_language(language)
    result = slide.model_copy(deep=True)
    mapping = _display_mapping(slide, language)
    if result.chart:
        chart = result.chart
        for attr in ("title", "x_axis_title", "y_axis_title"):
            setattr(chart, attr, _replace_labels(display_label(getattr(chart, attr), language), mapping))
        chart.categories = [mapping.get(c, c) for c in chart.categories]
        for series in chart.series:
            series.name = _replace_labels(display_label(series.name, language), mapping)
    if result.table:
        columns = list(result.table.columns)
        result.table.columns = [field_label(c, language)[0] + (f", {field_label(c, language)[1]}" if field_label(c, language)[1] else "")
                                for c in columns]
        result.table.rows = [[category_label(value, columns[i], language) if i < len(columns) else value
                              for i, value in enumerate(row)] for row in result.table.rows]
    if result.provenance:
        for attr in ("title", "key_message"):
            setattr(result, attr, _replace_labels(getattr(result, attr), mapping))
        for item in result.items:
            item.heading = _replace_labels(item.heading, mapping)
            item.body = _replace_labels(item.body, mapping)
        result.source_note = _source_note(result, language)
        if language == "en":
            _english_analytical_text(result)
    return result


_ANALYTICAL_EN = {
    "изменение между крайними наблюдениями": "change between the first and last observations",
    "Промежуточные значения могут колебаться": "Intermediate values may fluctuate",
    "Относительно первого наблюдения": "Relative to the first observation",
    "Доли относятся только к показанным строкам": "Shares refer only to the displayed rows",
    "Структура показанной суммы": "Composition of the displayed total",
    "все наблюдения, включая выбросы, сохранены": "all observations, including outliers, are retained",
    "Максимум разделяют несколько категорий": "Multiple categories share the maximum",
    "полных наблюдений по полю": "complete observations for",
    "максимальное значение": "maximum value",
    "исходные значения полных строк": "original values of complete rows",
    "показаны исходные значения без группировки": "original values shown without grouping",
    "связь не доказывает причинность": "association does not establish causation",
    "полных пар": "complete pairs", "полных наблюдений": "complete observations",
    "Максимальная доля": "Largest share", "показанной суммы": "of the displayed total",
    "округлено до": "rounded to", "знаков": "decimal places",
    "строк справочника сохранены в приложении": "reference rows retained in the appendix",
    "страниц в приложении после основных выводов": "pages in the appendix after the main findings",
    "исходные значения сохранены": "original values retained",
    "Полный справочник": "Complete reference", "Справочная таблица": "Reference table",
    "Справочные данные": "Reference data", "Количество исходных записей": "Source record count",
    "показаны первые": "first rows shown", "Справочник": "Reference table",
    "Приложение": "Appendix", "Распределение": "Distribution", "динамика": "trend",
    "частота по": "frequency across", "интервалам": "intervals", "учтены все": "all included",
    "значений": "values", "Число наблюдений": "Observation count",
    "по полю": "by", "Среди": "Among", "максимум": "maximum", "минимум": "minimum",
    "между": "between", "от": "from", "до": "to", "и": "and", "из": "of",
    "строки": "rows", "строк": "rows", "страница": "page", "категории": "categories",
    "п. п.": "pp", "наблюдений": "observations", "шт.": "pcs",
}


def _english_analytical_text(slide: SlideIntent) -> None:
    """Translate code-owned phrases without dropping/recomputing a single claim."""
    for attr in ("title", "key_message"):
        setattr(slide, attr, _replace_labels(getattr(slide, attr), _ANALYTICAL_EN))
    for item in slide.items:
        item.heading = _replace_labels(item.heading, _ANALYTICAL_EN)
        item.body = _replace_labels(item.body, _ANALYTICAL_EN)
    if slide.chart:
        for attr in ("title", "x_axis_title", "y_axis_title", "unit"):
            setattr(slide.chart, attr, _replace_labels(getattr(slide.chart, attr), _ANALYTICAL_EN))
        for series in slide.chart.series:
            series.name = _replace_labels(series.name, _ANALYTICAL_EN)


def language_findings(scenes, language: str):
    """Review unknown language; retained names are not falsely called translation errors."""
    from designer.contracts import Finding
    findings = []
    for scene in scenes:
        candidates = []
        for element in scene.elements:
            if element.role in {"source", "brand_logo", "footer"}:
                continue  # source identifiers and licensed branding keep their spelling
            candidates.append(element.text)
            if element.chart:
                c = element.chart
                candidates += [c.title, c.x_axis_title, c.y_axis_title, *c.categories, *(s.name for s in c.series)]
            if element.table:
                candidates += element.table.columns + [cell for row in element.table.rows for cell in row]
        unknown = set()
        for value in candidates:
            cleaned = re.sub(r"https?://\S+|\b[A-Z][A-Z0-9_-]+\b|\b\S+\.(?:csv|xlsx?|json|md|pdf|pptx)\b", "", value)
            words = re.findall(r"[A-Za-z][A-Za-z_ ]{2,}" if language == "ru" else r"[А-Яа-яЁё][А-Яа-яЁё ]{2,}", cleaned)
            unknown.update(w.strip() for w in words if w.strip())
        if unknown:
            examples = "; ".join(sorted(unknown))[:220]
            findings.append(Finding(id=f"language-review-{scene.slide_id}", slide_id=scene.slide_id,
                check_id="language_unresolved", kind="deterministic", severity="warning",
                message=f"Проверьте язык подписей ({language}): {examples}. Оригинальные названия сохранены.",
                fix_hint="Подтвердите бренд/имя/термин или задайте проверенный перевод; исходные данные не изменялись."))
        if any(re.search(r"lorem ipsum|click to add|text goes here|insert (?:title|text)|your (?:title|text) here", v, re.I)
               for v in candidates):
            findings.append(Finding(id=f"template-residue-{scene.slide_id}", slide_id=scene.slide_id,
                check_id="template_residue", kind="deterministic", severity="warning",
                message="На слайде остался текст-заполнитель шаблона.", fix_hint="Удалите или заполните заглушку."))
    return findings


def localize_plan(plan: DeckPlan, language: str = "ru") -> DeckPlan:
    validate_language(language)
    result = plan.model_copy(deep=True)
    result.language = language
    result.slides = [localize_slide(slide, language) for slide in result.slides]
    return result


def evidence_fingerprint(plan: DeckPlan) -> str:
    """Identity of immutable evidence, independent of presentation display labels."""
    evidence = []
    for slide in plan.slides:
        evidence.append({
            "id": slide.id,
            "provenance": slide.provenance.model_dump(mode="json") if slide.provenance else None,
            "chart": {"type": slide.chart.type, "unit": {"observations": "наблюдений", "pcs": "шт."}.get(slide.chart.unit, slide.chart.unit),
                      "categories_count": len(slide.chart.categories),
                      "series": [(s.values, s.x_values) for s in slide.chart.series]} if slide.chart else None,
            "table": [[_NUMBER.findall(c) for c in row] for row in slide.table.rows] if slide.table else None,
            "numbers": [item.number for item in slide.items],
        })
    return hashlib.sha256(json.dumps(evidence, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def migrate_deck_locale(deck_id: str, variant: str = "a", language: str = "ru") -> dict:
    """Synchronous, snapshotted RU display repair; no model call.

    Use against a backed-up generated deck with no concurrent editing. Unknown
    narrative prose is retained. English is a creation option; translating existing
    arbitrary Russian prose requires an explicit reviewed translation workflow.
    """
    if language != "ru":
        raise ValueError("Existing-deck migration supports ru; use language=en when creating a new deck")
    from designer import edit, store
    from designer.contracts import Deck
    from designer.edit_runtime import lock, ensure_export
    from designer.layout.scene import build_scene
    from designer.layout.compose import compose
    import uuid
    import shutil
    import tempfile
    from pathlib import Path

    with lock(deck_id, variant):
        state = edit._load(deck_id, variant)
        if state.raw.get("revision") and not state.raw.get("locale_migration"):
            raise ValueError("Deck has editor revisions; migrate a reviewed generated copy to preserve manual edits")
        if state.plan.language == "en":
            raise ValueError("Колода создана на английском. Русификация подписей не переводит её авторский текст; создайте русскую версию по исходному брифу.")
        before = evidence_fingerprint(state.plan)
        original = state.plan
        state.plan = localize_plan(state.plan, language)
        if evidence_fingerprint(state.plan) != before:
            raise ValueError("Locale migration would change source or numerical evidence")
        patterns = {pattern.id: pattern for pattern in state.ds.patterns}
        for index, (old, new, spec) in enumerate(zip(original.slides, state.plan.slides, state.specs)):
            if new.provenance:
                # Refit translated labels against the same pattern; old fitted
                # sizes were measured for shorter English strings.
                state.specs[index] = compose(new, patterns[spec.pattern_id], state.ds)
                continue
            mapping = _display_mapping(old, language)
            mapping.update({old.title: new.title, old.key_message: new.key_message,
                            old.source_note: new.source_note})
            spec.slot_text = {key: _replace_labels(value, mapping) for key, value in spec.slot_text.items()}
            spec.unit_text = [{key: _replace_labels(value, mapping) for key, value in row.items()} for row in spec.unit_text]
            spec.linked_unit_text = {key: [{k: _replace_labels(v, mapping) for k, v in row.items()} for row in rows]
                                     for key, rows in spec.linked_unit_text.items()}
            spec.chart, spec.table = new.chart, new.table
            for position in spec.element_positions.values():
                if position.text:
                    position.text = _replace_labels(position.text, mapping)
            for element in spec.added_elements:
                if element.role == "source":
                    element.text = new.source_note
                elif element.text:
                    element.text = _replace_labels(element.text, mapping)
        state.scenes = [build_scene(spec, patterns[spec.pattern_id], state.ds, state.package_dir) for spec in state.specs]
        findings = edit._checks(state, {slide.id for slide in state.plan.slides})
        backup = Path(tempfile.mkdtemp(prefix="locale-backup-", dir=store.deck_variant_state_path(deck_id, variant).parent))
        shutil.copy2(store.deck_variant_state_path(deck_id, variant), backup / "deck.json")
        for name, directory in (("files", store.deck_variant_files_dir(deck_id, variant)),
                                ("slides", store.deck_variant_slides_dir(deck_id, variant))):
            if directory.exists():
                shutil.copytree(directory, backup / name)
        edit._snapshot(state)
        deck = Deck(id=deck_id, design_system_id=state.ds_id, variant=variant,
                    plan=state.plan, specs=state.specs, scenes=state.scenes)
        # Intentional: do not call generic _persist/_mark_edited_evidence. Only this
        # constrained vocabulary transformation has passed the immutable fingerprint.
        store.save_deck_result(deck_id, deck, findings, variant=variant)
        raw = store.load_deck_state(deck_id, variant)
        raw["revision"] = uuid.uuid4().hex
        report = {"language": language, "evidence_sha256": before, "numerical_evidence_unchanged": True,
                  "contextual_audit": "invalidated; rerun on exported images",
                  "unknown_names": "retained; review unknown source labels manually", "backup": str(backup),
                  "language_review_slide_ids": [f.slide_id for f in findings if f.check_id == "language_unresolved"]}
        raw["locale_migration"] = report
        store._write_json(store.deck_variant_state_path(deck_id, variant), raw)
    ensure_export(deck_id, variant)
    return report
