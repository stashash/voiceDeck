"""Deterministic table display; the complete source is a separate export contract."""
from __future__ import annotations

import copy
import math
import re

PAGE_ROWS = 7
COMPACT_THRESHOLD = 20
MAX_FULL_PAGES = 30


def instruction_echo(slide) -> bool:
    """Specific generator bookkeeping, never an analytical/quoted/numeric slide."""
    if slide.provenance or slide.chart or slide.table or slide.kind.value not in {"bullets", "cards", "steps", "compare", "section"}:
        return False
    text = " ".join([slide.title, slide.key_message, *(i.heading + " " + i.body for i in slide.items)])
    # Source identifiers mentioned by the faulty planning prompt are not measures.
    without_ids = re.sub(r"\b[\w-]+\.(?:csv|xlsx?|json|md)\b", "", text)
    if re.search(r"\d", without_ids) or any(i.number for i in slide.items):
        return False
    return bool(re.search(
        r"(?:слайды.{0,70}уже (?:готовы|подготовлены)|готовые слайды.{0,60}по (?:темам|каждой теме)|"
        r"slides.{0,50}already (?:ready|prepared))", text, re.I))


def clean_instruction_echoes(plan):
    result = plan.model_copy(deep=True)
    removed = [s for s in result.slides if instruction_echo(s)]
    result.slides = [s for s in result.slides if not instruction_echo(s)]
    caveats = []
    for slide in removed:
        for item in slide.items:
            if re.search(r"синтетическ|synthetic", item.body, re.I):
                caveats.append(item.body.rstrip("."))
    # Retain the real data qualification, visibly, when its metatext wrapper is removed.
    modified = []
    if caveats and result.slides:
        cover = result.slides[0]
        existing = " ".join([cover.title, cover.key_message]).lower()
        if not re.search(r"синтетическ|synthetic", existing):
            cover.key_message = ". ".join([cover.key_message.rstrip("."), *dict.fromkeys(caveats)]) + "."
            modified.append(cover.id)
    return result, [s.id for s in removed], modified


def table_pages(suggestion: dict, snapshot: dict, mode: str = "compact") -> list[dict]:
    if mode not in {"compact", "full"}:
        raise ValueError("table_display must be compact or full")
    if suggestion.get("visual") != "table":
        return [suggestion]
    table = snapshot.get("table") or {}
    rows, lines, headers = (table.get(key) or [] for key in ("rows", "row_lines", "headers"))
    if (not rows or len(rows) != len(lines) or len(set(lines)) != len(lines)
            or not headers or any(len(row) != len(headers) for row in rows)):
        raise ValueError("Исходная таблица неполна; показ без проверяемых строк невозможен.")
    compact = len(rows) > COMPACT_THRESHOLD and mode == "compact"
    pages = 1 if compact else math.ceil(len(rows) / PAGE_ROWS)
    if pages > MAX_FULL_PAGES:
        raise ValueError(f"Полный показ требует {pages} слайдов (предел {MAX_FULL_PAGES}); выберите компактный показ с полным исходником.")
    result = []
    for index in range(pages):
        start, end = index * PAGE_ROWS, min(len(rows), (index + 1) * PAGE_ROWS)
        page = copy.deepcopy(suggestion)
        scope = lines[start:end]
        provenance = dict(page.get("provenance") or {})
        provenance.update(displayed_row_lines=scope, page_index=index + 1 if pages > 1 else None,
                          page_count=pages if pages > 1 else None,
                          table_display="compact" if compact else "full",
                          missing_policy="preserve_all_rows")
        page.update(visual="table", number="", chart=None,
                    table={"columns": headers, "rows": rows[start:end]}, provenance=provenance,
                    data_lines=[" | ".join([*headers, *row]) for row in rows[start:end]])
        # No claim that a physical line range is a count, or that a preview is all data.
        page["headline"], page["statement"] = table_copy(len(rows), start, end, compact, pages, "ru", rows)
        page["coverage"] = f"На слайде: {len(scope)} из {len(rows)} строк. Строки источника: {', '.join(map(str, scope))}."
        page["formula"] = f"Исходные строки без агрегации; показано {len(scope)} из {len(rows)}."
        page["provenance"]["formula"] = page["formula"]
        result.append(page)
    return result


def table_copy(total, start, end, compact, pages, language, rows=()):
    en = language == "en"
    if compact:
        return ((f"Source preview · {end - start} of {total} rows" if en else f"Фрагмент таблицы · {end - start} из {total} строк"),
                (f"First {end - start} rows, not a representative sample. All {total} rows: HTML → Sources or accompanying sources archive."
                 if en else f"Первые {end - start} строк, не репрезентативная выборка. Все {total}: HTML → «Источники» или приложенный архив исходников."))
    if pages > 1:
        return ((f"Appendix · rows {start + 1}–{end} of {total}" if en else f"Приложение · строки {start + 1}–{end} из {total}"),
                ("Original values and missing cells; no aggregation." if en else "Исходные значения и пропуски; без агрегации."))
    missing = any(cell == "" for row in rows for cell in row)
    zero = any(cell.strip() in {"0", "0.0", "0,0"} for row in rows for cell in row)
    if missing and zero:
        return (("Zero is a value; a blank is missing data" if en else "Ноль — значение, пропуск — отсутствие данных"),
                (f"All {total} rows shown. Blank cells are not filled with zeros." if en else f"Показаны все {total} строки. Пустые ячейки не заменены нулями."))
    return ((f"Source table · {total} rows" if en else f"Исходная таблица · {total} строк"),
            ("All rows shown, without aggregation." if en else "Все строки показаны без агрегации."))


def localize_table_copy(slide, language):
    """Regenerate only code-owned table wording, leaving original evidence untouched."""
    p = slide.provenance
    if not p or not p.table_display or slide.table is None:
        return
    start = p.row_lines.index(p.displayed_row_lines[0]) if p.displayed_row_lines else 0
    slide.title, slide.key_message = table_copy(
        p.total_rows, start, start + len(p.displayed_row_lines), p.table_display == "compact",
        p.page_count or 1, language, slide.table.rows)


def recompose_reference_plan(plan, mode="compact"):
    """Pure replacement plan + old-id mapping; validates every replaced source cell."""
    from designer.contracts import TableSpec, SlideKind
    from designer.export.sources import collect_sources
    from designer.localization import localize_slide

    sources = {s["dataset_id"]: s for s in collect_sources(plan)}
    groups = {}
    for slide in plan.slides:
        p = slide.provenance
        if p and p.visualization == "table" and (slide.table is not None or
                (slide.kind == SlideKind.big_number and not p.displayed_row_lines
                 and p.total_rows > PAGE_ROWS)):
            groups.setdefault(p.dataset_id, []).append(slide)
    replacements, dropped, origin = {}, set(), {}
    for dataset_id, group in groups.items():
        source = sources[dataset_id]
        table = source["table"]
        # Modified source slides require review, not silent reconstruction from old data.
        for old in group:
            if old.provenance.warnings and any("изменено после расчёта" in w for w in old.provenance.warnings):
                raise ValueError(f"Edited evidence needs review: {old.id}")
            if old.table:
                positions = {line: i for i, line in enumerate(table["row_lines"])}
                expected = old.model_copy(deep=True)
                expected.table = TableSpec(columns=table["headers"], rows=[
                    table["rows"][positions[line]] for line in old.provenance.displayed_row_lines])
                expected = localize_slide(expected, plan.language)
                if old.table != expected.table:
                    raise ValueError(f"Displayed source cells differ from snapshot: {old.id}")
        base = next((s for s in group if s.table is not None), None)
        if base is None:
            raise ValueError("Reference summary has no source table")
        # Source selection/filter must not be widened by migration.
        if base.provenance.row_lines != table["row_lines"] or base.provenance.excluded_row_lines:
            raise ValueError("Migration supports complete source tables only")
        pages = table_pages({"visual": "table", "provenance": base.provenance.model_dump()},
                            {"table": table}, mode)
        generated = []
        first_id = group[0].id
        for index, page in enumerate(pages):
            new = base.model_copy(deep=True)
            new.id = first_id if index == 0 else f"{first_id}-ref-{index + 1}"
            new.kind = SlideKind.table
            new.items = []
            new.chart = None
            new.table = TableSpec(**page["table"])
            new.provenance = base.provenance.model_copy(update=page["provenance"])
            # Notes of previous generated pages carry a code-owned calculation
            # description. Update it along with the visible scope, retaining the
            # source identity and all other notes.
            new.notes = re.sub(r"(?<=Расчёт: ).*?(?= Данные:)",
                               lambda _: page["formula"].rstrip(".") + ".",
                               new.notes, count=1)
            new.title, new.key_message = page["headline"], page["statement"]
            new = localize_slide(new, plan.language)
            generated.append(new)
            origin[new.id] = base.id
        replacements[first_id] = generated
        dropped.update(s.id for s in group)
    output = plan.model_copy(deep=True)
    output.slides = [new for old in plan.slides
                     for new in (replacements.get(old.id, []) if old.id in dropped else [old.model_copy(deep=True)])]
    output, echo_ids, modified = clean_instruction_echoes(output)
    dropped.update(echo_ids)
    dropped.update(modified)
    origin.update({slide_id: slide_id for slide_id in modified})
    if len({s.id for s in output.slides}) != len(output.slides):
        raise ValueError("Generated reference ids conflict with existing slide ids")
    if not output.slides or any(not s.title.strip() for s in output.slides):
        raise ValueError("Recomposition produced empty slides")
    unaffected = [s.model_dump(mode="json") for s in plan.slides if s.id not in dropped]
    after = [s.model_dump(mode="json") for s in output.slides if s.id not in origin]
    if unaffected != after:
        raise ValueError("Main-slide evidence changed")
    return output, origin, sorted(dropped)


def migrate_deck_reference_display(deck_id, variant="a", mode="compact", export=True):
    """Archive+history, preserve unaffected specs/scenes verbatim, no model invocation.

    The source cells of every replaced table must match verified original evidence.
    Existing editor changes outside those tables are preserved. Failed validation
    does not write. The archive includes prior exports and images for exact recovery.
    """
    import hashlib
    import json
    import shutil
    import tempfile
    import uuid
    from pathlib import Path
    from designer import edit, store
    from designer.edit_runtime import lock
    from designer.export.sources import collect_sources
    from designer.layout.compose import compose
    from designer.layout.scene import build_scene

    with lock(deck_id, variant):
        state = edit._load(deck_id, variant)
        original = state.plan
        new_plan, origin, removed = recompose_reference_plan(original, mode)
        if new_plan == original:
            return {"changed": False, "slides_before": len(original.slides), "slides_after": len(original.slides)}
        old_specs = {s.slide_id: s for s in state.specs}
        old_scenes = {s.slide_id: s for s in state.scenes}
        patterns = {p.id: p for p in state.ds.patterns}
        state.plan = new_plan
        state.specs, state.scenes = [], []
        for slide in new_plan.slides:
            if slide.id not in origin:
                state.specs.append(old_specs[slide.id])
                state.scenes.append(old_scenes[slide.id])
            else:
                pattern = patterns[old_specs[origin[slide.id]].pattern_id]
                spec = compose(slide, pattern, state.ds)
                state.specs.append(spec)
                state.scenes.append(build_scene(spec, pattern, state.ds, state.package_dir))
        findings = edit._checks(state, set(origin))
        evidence = [{k: v for k, v in s.items() if k not in {"raw", "table"}}
                    for s in collect_sources(new_plan)]
        unaffected = [s.model_dump(mode="json") for s in original.slides if s.id not in removed]
        fingerprint = hashlib.sha256(json.dumps(unaffected, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        state_path = store.deck_variant_state_path(deck_id, variant)
        backup = Path(tempfile.mkdtemp(prefix="reference-backup-", dir=state_path.parent))
        shutil.copy2(state_path, backup / "deck.json")
        for name, directory in (("files", store.deck_variant_files_dir(deck_id, variant)),
                                ("slides", store.deck_variant_slides_dir(deck_id, variant))):
            if directory.exists():
                shutil.copytree(directory, backup / name)
        report = {"changed": True, "mode": mode, "slides_before": len(original.slides),
                  "slides_after": len(new_plan.slides), "replaced_slide_ids": removed,
                  "new_slide_ids": list(origin), "backup": str(backup),
                  "unaffected_slides_sha256": fingerprint, "main_evidence_unchanged": True,
                  "sources": evidence, "model_calls": 0}
        report["removed_instruction_echo_ids"] = [s.id for s in original.slides if instruction_echo(s)]
        # Produce files before publishing a new revision. Export failure leaves the document intact.
        with tempfile.TemporaryDirectory(prefix="reference-export-", dir=state_path.parent) as directory:
            staging = Path(directory)
            if export:
                edit._export_files(state, staging)
            edit._snapshot(state)
            raw = copy.deepcopy(state.raw)
            raw.update(plan=new_plan.model_dump(mode="json"),
                       specs=[s.model_dump(mode="json") for s in state.specs],
                       scenes=[s.model_dump(mode="json") for s in state.scenes],
                       findings=[f.model_dump(mode="json") for f in findings],
                       revision=uuid.uuid4().hex, reference_display_migration=report)
            if export:
                target = store.deck_variant_files_dir(deck_id, variant)
                for name in ("deck.pdf", "deck.sources.zip", "deck.bundle.zip", "sources-manifest.json"):
                    if not (staging / name).is_file():
                        (target / name).unlink(missing_ok=True)
                for path in staging.iterdir():
                    if path.is_file():
                        shutil.copy2(path, target / path.name)
                images = staging / "slides"
                target_images = store.deck_variant_slides_dir(deck_id, variant)
                # Archive already exists. Retire old images so removed pages cannot be served.
                for path in target_images.glob("slide-*.png"):
                    path.unlink()
                if images.exists():
                    for path in images.iterdir():
                        shutil.copy2(path, target_images / path.name)
                store._write_json(target / "export-revision.json", {"revision": raw["revision"], "images": images.exists()})
            store._write_json(state_path, raw)
        return report
