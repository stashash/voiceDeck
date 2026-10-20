"""Portable, offline evidence: verified originals, normalized rows, searchable HTML."""
from __future__ import annotations

import base64
import hashlib
import html
import io
import json
import re
import zipfile
from pathlib import Path

from designer import store


def verified_source(dataset_id: str, expected_sha: str | None = None):
    snapshot = store.load_dataset(dataset_id)
    if snapshot is None:
        raise ValueError(f"Source snapshot is missing: {dataset_id}")
    raw = base64.b64decode(snapshot["source_base64"], validate=True)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != snapshot["source_sha256"] or expected_sha and digest != expected_sha:
        raise ValueError(f"Source checksum mismatch: {dataset_id}")
    return snapshot, raw


def collect_sources(plan):
    result = []
    seen = {}
    for slide in plan.slides:
        p = slide.provenance
        if not p:
            continue
        if p.dataset_id in seen:
            if seen[p.dataset_id] != p.source_sha256:
                raise ValueError("Conflicting source identity in deck")
            continue
        seen[p.dataset_id] = p.source_sha256
        snapshot, raw = verified_source(p.dataset_id, p.source_sha256)
        table = snapshot["table"]
        if (len(table["rows"]) != p.total_rows or len(table["row_lines"]) != p.total_rows
                or not set(p.row_lines).issubset(table["row_lines"])):
            raise ValueError("Source row scope differs from deck evidence")
        safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", snapshot["file_name"]).strip(". ") or "source"
        result.append({"dataset_id": p.dataset_id, "source_sha256": p.source_sha256,
                       "file_name": snapshot["file_name"], "sheet": table.get("sheet", ""),
                       "table_index": snapshot["table_index"], "total_rows": len(table["rows"]),
                       "original_path": f"sources/{p.dataset_id}/original/{safe}",
                       "table_path": f"sources/{p.dataset_id}/table.json",
                       "table": table, "raw": raw})
    return result


def _manifest(sources):
    return {"version": 1, "completeness": "all original bytes and all parsed rows",
            "datasets": [{k: v for k, v in s.items() if k not in {"raw", "table"}} for s in sources]}


def sources_archive(sources):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("sources-manifest.json", json.dumps(_manifest(sources), ensure_ascii=False, indent=2))
        for s in sources:
            archive.writestr(s["original_path"], s["raw"])
            archive.writestr(s["table_path"], json.dumps(s["table"], ensure_ascii=False, indent=2))
    return buffer.getvalue()


def source_panel(plan, sources) -> str:
    if not sources:
        return ""
    en = plan.language == "en"
    title = "Sources" if en else "Источники"
    sections = []
    for s in sources:
        escape = html.escape
        table = s["table"]
        rows = "".join("<tr><td>" + str(line) + "</td>" + "".join(f"<td>{escape(str(cell))}</td>" for cell in row) + "</tr>"
                       for line, row in zip(table["row_lines"], table["rows"]))
        heads = "".join(f"<th>{escape(str(c))}</th>" for c in table["headers"])
        download = "Download original" if en else "Скачать оригинал"
        caption = f'All {s["total_rows"]} source rows' if en else f'Все {s["total_rows"]} строки источника'
        line_label = "Source row" if en else "Строка источника"
        sections.append(f'<details class="source-dataset"><summary>{escape(s["file_name"])} · {escape(s["sheet"])} · {caption}</summary>'
            f'<p><a download="{escape(s["file_name"], quote=True)}" href="data:application/octet-stream;base64,{base64.b64encode(s["raw"]).decode()}">{download}</a>'
            f' · SHA-256: <code>{s["source_sha256"]}</code></p>'
            f'<div class="source-scroll"><table><thead><tr><th>{line_label}</th>{heads}</tr></thead><tbody>{rows}</tbody></table></div></details>')
    label = "Search all source cells" if en else "Поиск по всем ячейкам источников"
    hint = ("Original labels and missing cells are preserved. Search hides nonmatching rows; clear to show all."
            if en else "Оригинальные подписи и пропуски сохранены. Поиск скрывает несовпадения; очистите поле, чтобы увидеть все строки.")
    return f"""<aside id="source-access"><details><summary>{title} · {len(sources)}</summary>
<div class="source-panel"><label>{label} <input id="source-filter" type="search"></label><p>{hint}</p>{''.join(sections)}</div></details></aside>
<style>
#source-access {{position:fixed;right:12px;top:12px;z-index:9999;color:#111;background:#fff;font:14px Arial,sans-serif;border:1px solid #555;border-radius:6px;padding:10px;max-width:95vw}}
#source-access summary {{cursor:pointer;line-height:1.5}}
#source-access .source-panel {{max-height:78vh;max-width:90vw;overflow:auto;padding:10px}}
#source-access input {{color:#111;background:#fff;border:1px solid #555;padding:6px}}
#source-access a {{color:#004a99;text-decoration:underline}}
#source-access .source-scroll {{overflow:auto;max-height:45vh}}
#source-access table {{border-collapse:collapse;color:#111;background:#fff;font-size:13px}}
#source-access th,#source-access td {{padding:6px;border:1px solid #999;text-align:left;white-space:pre-wrap}}
#source-access code {{overflow-wrap:anywhere}}
@media print {{#source-access {{display:none}}}}
</style><script>
(function(){{
var panel=document.getElementById('source-access'), input=document.getElementById('source-filter');
panel.addEventListener('keydown',function(e){{e.stopPropagation();}});
input.addEventListener('input',function(){{
 var q=input.value.toLocaleLowerCase();
 panel.querySelectorAll('.source-dataset').forEach(function(d){{
   if(q) d.open=true;
   d.querySelectorAll('tbody tr').forEach(function(r){{r.hidden=!r.textContent.toLocaleLowerCase().includes(q);}});
 }});
}});
}})();
</script>"""


def embed_sources(markup: str, plan, sources=None) -> str:
    sources = collect_sources(plan) if sources is None else sources
    return markup.replace("</body>", source_panel(plan, sources) + "</body>")


def export_source_package(plan, files_dir: Path) -> dict:
    """Call AFTER the final PPTX/PDF/HTML. Fail closed if evidence cannot be resolved."""
    sources = collect_sources(plan)
    if not sources:
        return {"datasets": []}
    files_dir = Path(files_dir)
    data = sources_archive(sources)
    (files_dir / "deck.sources.zip").write_bytes(data)
    for name in ("deck.html", "deck.markup.html"):
        path = files_dir / name
        if path.exists():
            markup = path.read_text(encoding="utf-8")
            if 'id="source-access"' not in markup:
                path.write_text(embed_sources(markup, plan, sources), encoding="utf-8")
    manifest = _manifest(sources)
    (files_dir / "sources-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    with zipfile.ZipFile(files_dir / "deck.bundle.zip", "w", zipfile.ZIP_DEFLATED) as bundle:
        for name in ("deck.pptx", "deck.pdf", "deck.html", "deck.sources.zip", "sources-manifest.json"):
            path = files_dir / name
            if path.is_file():
                bundle.write(path, name)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for name in archive.namelist():
                if name != "sources-manifest.json":
                    bundle.writestr(name, archive.read(name))
        bundle.writestr("README.txt", (
            "Open deck.html for the offline presentation, source search and original file downloads.\n"
            "Keep the sources archive with PPTX/PDF when sharing individual files.\n"
            "A source-preview slide contains only the explicitly stated rows; it is not a representative sample.\n"
            "Sources retain original labels, missing cells and exact bytes; table.json records parsed rows and source lines.\n"
            "Откройте deck.html: презентация, поиск по полным таблицам и скачивание оригиналов работают без сети.\n"
            "При пересылке PPTX/PDF приложите архив исходников. Фрагмент на слайде не является полным справочником.\n"))
    return manifest
