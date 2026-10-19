#!/usr/bin/env python3
"""Run the semantic Stage 2 fixtures through the live Designer API."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "designer" / "tests" / "fixtures" / "semantic_stage2"
OUTPUT = ROOT / "artifacts" / "stage2-demo" / "generated"
FIXTURES = (
    "category_comparison.csv", "category_shares.json", "distribution.csv",
    "embedded_table.md", "missing_zero.csv", "reference_201.csv", "time_series.csv",
)
BRIEF = (
    "Подготовь русскоязычную демонстрацию аналитики на синтетических учебных данных. "
    "Чётко отделяй наблюдения от интерпретаций, сохраняй периоды, единицы и оговорки источника. "
    "Не выдавай синтетические примеры за реальные компании или рыночные результаты."
)
PURPOSE = "Демонстрация возможностей анализа данных и подготовки слайдов"
AUDIENCE = "Русскоязычные специалисты, оценивающие прототип"
VARIANTS = ("a", "b", "c")


class DemoError(RuntimeError):
    pass


def request(base: str, path: str, *, method: str = "GET", body: bytes | None = None,
            headers: dict[str, str] | None = None, timeout: float) -> tuple[bytes, str]:
    req = Request(base.rstrip("/") + path, data=body, headers=headers or {}, method=method)
    try:
        with urlopen(req, timeout=timeout) as response:
            return response.read(), response.headers.get("Content-Type", "")
    except HTTPError as exc:
        detail = exc.read(4000).decode("utf-8", "replace")
        raise DemoError(f"HTTP {exc.code} {method} {path}: {detail}") from exc
    except (TimeoutError, URLError, OSError) as exc:
        raise DemoError(f"Request failed {method} {path}: {exc}") from exc


def json_request(base: str, path: str, *, method: str = "GET", payload: dict[str, Any] | None = None,
                 timeout: float) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    data, _ = request(base, path, method=method, body=body, headers=headers, timeout=timeout)
    try:
        value = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DemoError(f"Expected JSON from {method} {path}") from exc
    if not isinstance(value, dict):
        raise DemoError(f"Expected JSON object from {method} {path}")
    return value


def multipart(fields: dict[str, str], files: list[tuple[str, Path]], boundary: str) -> bytes:
    chunks: list[bytes] = []
    marker = f"--{boundary}".encode()
    for key, value in fields.items():
        chunks += [marker, f'Content-Disposition: form-data; name="{key}"'.encode(), b"", value.encode()]
    for field, path in files:
        chunks += [marker,
                   f'Content-Disposition: form-data; name="{field}"; filename="{path.name}"'.encode(),
                   b"Content-Type: application/octet-stream", b"", path.read_bytes()]
    chunks += [f"--{boundary}--".encode(), b""]
    return b"\r\n".join(chunks)


def candidate_selection(dataset: dict[str, Any]) -> dict[str, Any]:
    plan = dataset.get("plan") or {}
    candidates = plan.get("candidates") or []
    selected = plan.get("selected_candidate") or {}
    ordered = [selected, *candidates]
    for candidate in ordered:
        if candidate.get("renderable") is True:
            fields = candidate.get("required_fields")
            kind = candidate.get("kind")
            if isinstance(kind, str) and isinstance(fields, list) and all(isinstance(x, str) for x in fields):
                return {"dataset_id": dataset["dataset_id"], "candidate_kind": kind, "required_fields": fields}
    raise DemoError(f"No renderable plan candidate for {dataset.get('file_name')!r} table {dataset.get('table_index')}")


def wait_for_deck(base: str, deck_id: str, timeout: float, poll: float,
                  required_variants: tuple[str, ...] = VARIANTS) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    path = f"/decks/{quote(deck_id, safe='')}"
    while time.monotonic() < deadline:
        try:
            state = json_request(base, path, timeout=min(30, timeout))
        except DemoError as exc:
            if "timed out" not in str(exc).lower():
                raise
            print(f"State request timed out; retrying existing job {deck_id}", flush=True)
            time.sleep(min(poll, max(0, deadline-time.monotonic())))
            continue
        variants = state.get("variants") or {}
        if state.get("status") == "error" or any(v.get("status") == "error" for v in variants.values()):
            errors = {k: v.get("error") for k, v in variants.items() if v.get("status") == "error"}
            raise DemoError(f"Deck {deck_id} failed: {errors or state.get('error')}")
        if all(variants.get(code, {}).get("status") == "done" for code in required_variants):
            return state
        time.sleep(min(poll, max(0, deadline - time.monotonic())))
    raise DemoError(f"Timed out after {timeout:g}s waiting for deck {deck_id}")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def make_contact_sheet(images: list[Path], destination: Path) -> None:
    try:
        from PIL import Image, ImageOps, ImageDraw
    except ImportError as exc:
        raise DemoError("Pillow is required to create contact sheets (install designer project's dependencies)") from exc
    tiles = []
    thumb_w, thumb_h = 480, 270
    for image_path in images:
        with Image.open(image_path) as source:
            tile = ImageOps.contain(source.convert("RGB"), (thumb_w, thumb_h))
        canvas = Image.new("RGB", (thumb_w, thumb_h + 28), "white")
        canvas.paste(tile, ((thumb_w - tile.width) // 2, 0))
        ImageDraw.Draw(canvas).text((8, thumb_h + 6), image_path.name, fill="black")
        tiles.append(canvas)
    if not tiles:
        raise DemoError(f"No slide PNGs found for contact sheet {destination}")
    columns = min(3, len(tiles))
    rows = (len(tiles) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * thumb_w, rows * (thumb_h + 28)), "#dddddd")
    for i, tile in enumerate(tiles):
        sheet.paste(tile, ((i % columns) * thumb_w, (i // columns) * (thumb_h + 28)))
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination)


def run(args: argparse.Namespace) -> Path:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    fixtures = (sorted(path for path in args.content_dir.iterdir() if path.suffix.lower() in {".csv", ".xlsx", ".json", ".txt", ".md"} and path.name != "README.md")
                if args.content_dir else [FIXTURE_DIR / name for name in FIXTURES])
    if not 5 <= len(fixtures) <= 7:
        raise DemoError("Supply five to seven datasets")
    missing = [str(path) for path in fixtures if not path.is_file()]
    if missing:
        raise DemoError("Missing committed fixtures: " + ", ".join(missing))
    templates = [path.resolve() for path in (args.template or [])]
    if len(templates) != 3 or any(not p.is_file() or p.suffix.lower() != ".pptx" for p in templates):
        raise DemoError("Pass exactly three existing .pptx template files with --template")

    manifest: dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(), "base_url": args.base_url.rstrip("/"),
        "brief": BRIEF, "purpose": PURPOSE, "audience": AUDIENCE, "variants": list(VARIANTS),
        "fixtures": [{"name": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in fixtures],
        "templates": [], "runs": [], "assumptions": [
            "API uses POST /insights/plan (multipart files[] and goal), POST /insights/plan/materialize-bundle, POST /design-systems, POST /decks, GET /decks/{id}, and variant file/slide routes.",
            "Templates are supplied by the operator because dataset fixtures do not contain PPTX template files.",
            "Designer API is served at base URL root (no /designer prefix).",
        ],
    }
    boundary = "----VoiceDeckStage2" + hashlib.sha256(os.urandom(32)).hexdigest()
    plan_body = multipart({"goal": "Подготовь аналитический план для русскоязычной демонстрации; сохраняй исходные значения, не заполняй пропуски нулями."},
                          [("files", path) for path in fixtures], boundary)
    plan_raw, _ = request(args.base_url, "/insights/plan", method="POST", body=plan_body,
                          headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, timeout=args.request_timeout)
    try:
        bundle = json.loads(plan_raw)
    except json.JSONDecodeError as exc:
        raise DemoError("/insights/plan returned invalid JSON") from exc
    datasets = bundle.get("datasets", [])
    if bundle.get("file_count") != 7 or len(datasets) != 7:
        raise DemoError(f"Expected 7 files and 7 datasets, got file_count={bundle.get('file_count')} datasets={len(datasets)}")
    selections = [candidate_selection(dataset) for dataset in datasets]
    mat_boundary = "----VoiceDeckMaterialize" + hashlib.sha256(os.urandom(32)).hexdigest()
    mat_body = multipart({"bundle_id": str(bundle["id"]), "selections": json.dumps(selections, ensure_ascii=False)}, [], mat_boundary)
    mat_raw, _ = request(args.base_url, "/insights/plan/materialize-bundle", method="POST", body=mat_body,
                         headers={"Content-Type": f"multipart/form-data; boundary={mat_boundary}"}, timeout=args.request_timeout)
    try:
        materialized = json.loads(mat_raw)
    except json.JSONDecodeError as exc:
        raise DemoError("bundle materialization returned invalid JSON") from exc
    if not materialized.get("id") or not materialized.get("suggestions"):
        raise DemoError("bundle materialization did not return an insights id and suggestions")
    write_json(output / "dataset-plan.json", bundle)
    write_json(output / "materialized-insights.json", materialized)
    manifest["bundle_id"] = bundle["id"]
    manifest["selected_candidates"] = selections
    manifest["materialized_insights_id"] = materialized["id"]

    for template_index, template in enumerate(templates):
        if template_index < len(args.resume_deck):
            deck_id = args.resume_deck[template_index]
            existing = json_request(args.base_url, f"/decks/{quote(deck_id,safe='')}", timeout=args.request_timeout)
            design_id = existing["design_system_id"]
            design_system = json_request(args.base_url, f"/design-systems/{quote(design_id,safe='')}", timeout=args.request_timeout)
            if design_system["source_file"] != template.name or not existing.get("brief", "").startswith(BRIEF):
                raise DemoError("Existing job does not match this template and brief")
            item = {"template": str(template), "design_system_id": design_id, "decks": [], "resumed_deck": deck_id}
            manifest["templates"].append(item)
            print(f"Resuming A/B/C: {design_id} / {deck_id}", flush=True)
        else:
            deck_id = ""
        if not deck_id:
            deck_id, design_id, item = start_template_run(args, template, manifest, materialized)
        write_json(output / "run-manifest.json", manifest)
        state = wait_for_deck(args.base_url, deck_id, args.generation_timeout, args.poll_interval)
        collect_template_run(args, output, manifest, item, deck_id, design_id, state)
        write_json(output / "run-manifest.json", manifest)
    return finish_run(args, output, manifest, materialized)


def start_template_run(args, template, manifest, materialized):
    print(f"Importing template: {template.name}", flush=True)
    boundary = "----VoiceDeckTemplate" + hashlib.sha256(os.urandom(32)).hexdigest()
    body = multipart({}, [("file", template)], boundary)
    raw, _ = request(args.base_url, "/design-systems", method="POST", body=body,
                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, timeout=args.request_timeout)
    try:
        design_system = json.loads(raw)
        design_id = design_system["id"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise DemoError(f"Template upload did not return design-system id: {template}") from exc
    item = {"template": str(template), "design_system_id": design_id, "decks": []}
    manifest["templates"].append(item)
    payload = {"design_system_id": design_id, "brief": BRIEF, "purpose": PURPOSE,
               "audience": AUDIENCE, "variants": list(VARIANTS), "insights_id": materialized["id"],
               "insight_ids": [suggestion["id"] for suggestion in materialized["suggestions"]]}
    created = json_request(args.base_url, "/decks", method="POST", payload=payload, timeout=args.request_timeout)
    deck_id = created.get("deck_id")
    if not deck_id:
        raise DemoError("POST /decks returned no deck_id")
    print(f"Generating A/B/C: {design_id} / {deck_id}", flush=True)
    item["deck_id"] = deck_id
    return deck_id, design_id, item


def collect_template_run(args, output, manifest, item, deck_id, design_id, state):
    run_raw, _ = request(args.base_url, f"/decks/{quote(deck_id, safe='')}/run", timeout=args.request_timeout)
    try:
        run_manifest = json.loads(run_raw)
    except json.JSONDecodeError as exc:
        raise DemoError(f"Run endpoint returned invalid JSON for deck {deck_id}") from exc
    template_run_manifest = output / design_id / "run.json"
    write_json(template_run_manifest, run_manifest)
    for variant in VARIANTS:
        variant_state = (state.get("variants") or {}).get(variant, {})
        run_path = f"/decks/{quote(deck_id, safe='')}/{variant}/files/"
        run_dir = output / design_id / variant
        run_dir.mkdir(parents=True, exist_ok=True)
        downloaded: list[str] = []
        for filename in ("deck.pdf", "deck.pptx", "deck.html"):
            try:
                data, _ = request(args.base_url, run_path + filename, timeout=args.request_timeout)
            except DemoError as exc:
                if filename == "deck.pdf":
                    raise
                manifest.setdefault("optional_download_errors", []).append(str(exc))
                continue
            (run_dir / filename).write_bytes(data)
            if filename == "deck.pdf":
                downloaded.append(filename)
        if "deck.pdf" not in downloaded:
            raise DemoError(f"PDF missing for {design_id}/{variant}")
        # API state includes image paths; retrieve each generated PNG to make a local contact sheet.
        local_slides = []
        for index, image_url in enumerate(variant_state.get("slide_images", []), start=1):
            path = image_url.split("?", 1)[0]
            data, _ = request(args.base_url, path, timeout=args.request_timeout)
            image_path = run_dir / "slides" / f"slide-{index:03d}.png"
            image_path.parent.mkdir(parents=True, exist_ok=True)
            image_path.write_bytes(data)
            local_slides.append(image_path)
        if not local_slides:
            raise DemoError(f"No slide images in completed state for {design_id}/{variant}")
        make_contact_sheet(local_slides, run_dir / "contact-sheet.png")
        record = {"deck_id": deck_id, "variant": variant, "status": variant_state.get("status"),
                  "output_dir": str(run_dir), "files": downloaded, "slide_count": len(local_slides),
                  "contact_sheet": str(run_dir / "contact-sheet.png"), "run_manifest": str(template_run_manifest)}
        item["decks"].append(record)
        manifest["runs"].append(record)


def finish_run(args, output, manifest, materialized):
    pdfs = list(output.rglob("deck.pdf"))
    if len(manifest["runs"]) != 9 or len(pdfs) != 9:
        raise DemoError(f"Expected exactly 9 successful runs and PDFs, got {len(manifest['runs'])} runs / {len(pdfs)} PDFs")
    if args.foreign_template:
        template = args.foreign_template.resolve()
        if not template.is_file() or template.suffix.lower() != ".pptx":
            raise DemoError("--foreign-template must be an existing .pptx file")
        foreign_boundary = "----VoiceDeckForeignTemplate" + hashlib.sha256(os.urandom(32)).hexdigest()
        body = multipart({}, [("file", template)], foreign_boundary)
        raw, _ = request(args.base_url, "/design-systems", method="POST", body=body,
                         headers={"Content-Type": f"multipart/form-data; boundary={foreign_boundary}"}, timeout=args.request_timeout)
        foreign_ds = json.loads(raw)
        foreign_id = foreign_ds["id"]
        created = json_request(args.base_url, "/decks", method="POST", payload={
            "design_system_id": foreign_id, "brief": BRIEF, "purpose": PURPOSE, "audience": AUDIENCE,
            "variants": ["a"], "insights_id": materialized["id"],
            "insight_ids": [item["id"] for item in materialized["suggestions"]],
        }, timeout=args.request_timeout)
        foreign_deck_id = created.get("deck_id")
        if not foreign_deck_id:
            raise DemoError("Unknown-template deck creation returned no deck_id")
        foreign_state = wait_for_deck(args.base_url, foreign_deck_id, args.generation_timeout,
                                      args.poll_interval, ("a",))
        foreign_dir = output / "unknown-template" / "a"
        foreign_dir.mkdir(parents=True, exist_ok=True)
        for filename in ("deck.pdf", "deck.pptx", "deck.html"):
            try:
                data, _ = request(args.base_url, f"/decks/{quote(foreign_deck_id, safe='')}/a/files/{filename}", timeout=args.request_timeout)
            except DemoError as exc:
                if filename == "deck.pdf":
                    raise
                manifest.setdefault("optional_download_errors", []).append(str(exc))
                continue
            (foreign_dir / filename).write_bytes(data)
        foreign_variant = foreign_state["variants"]["a"]
        slide_files = []
        for index, image_url in enumerate(foreign_variant.get("slide_images", []), start=1):
            data, _ = request(args.base_url, image_url.split("?", 1)[0], timeout=args.request_timeout)
            slide = foreign_dir / "slides" / f"slide-{index:03d}.png"
            slide.parent.mkdir(parents=True, exist_ok=True)
            slide.write_bytes(data)
            slide_files.append(slide)
        if not slide_files:
            raise DemoError("Unknown-template deck has no rendered slide images")
        make_contact_sheet(slide_files, foreign_dir / "contact-sheet.png")
        foreign_record = {"template": str(template), "design_system_id": foreign_id, "deck_id": foreign_deck_id,
                          "variant": "a", "slide_count": len(slide_files), "output_dir": str(foreign_dir),
                          "contact_sheet": str(foreign_dir / "contact-sheet.png"), "unknown_template": True}
        manifest["unknown_template_run"] = foreign_record
        manifest["runs"].append(foreign_record)
        pdfs = list(output.rglob("deck.pdf"))
    manifest["pdf_count"] = len(pdfs)
    manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
    manifest_path = output / "run-manifest.json"
    write_json(manifest_path, manifest)
    return manifest_path


def run_unknown_template(args: argparse.Namespace) -> Path:
    output = args.output.resolve()
    materialized_path = output / "materialized-insights.json"
    manifest_path = output / "run-manifest.json"
    if not materialized_path.is_file() or not manifest_path.is_file():
        raise DemoError("Run the nine challenge-template combinations first; materialized insights and run manifest are required")
    try:
        materialized = json.loads(materialized_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DemoError("Existing stage-two run artifacts are unreadable") from exc
    template = args.foreign_template.resolve()
    if not template.is_file() or template.suffix.lower() != ".pptx":
        raise DemoError("--foreign-template must be an existing .pptx file")
    boundary = "----VoiceDeckForeignTemplate" + hashlib.sha256(os.urandom(32)).hexdigest()
    body = multipart({}, [("file", template)], boundary)
    raw, _ = request(args.base_url, "/design-systems", method="POST", body=body,
                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, timeout=args.request_timeout)
    design_system = json.loads(raw)
    design_id = design_system["id"]
    created = json_request(args.base_url, "/decks", method="POST", payload={
        "design_system_id": design_id, "brief": manifest["brief"], "purpose": manifest["purpose"],
        "audience": manifest["audience"], "variants": ["a"], "insights_id": materialized["id"],
        "insight_ids": [item["id"] for item in materialized["suggestions"]],
    }, timeout=args.request_timeout)
    deck_id = created.get("deck_id")
    if not deck_id:
        raise DemoError("Unknown-template deck creation returned no deck_id")
    state = wait_for_deck(args.base_url, deck_id, args.generation_timeout, args.poll_interval, ("a",))
    variant = state["variants"]["a"]
    run_dir = output / "unknown-template" / "a"
    run_dir.mkdir(parents=True, exist_ok=True)
    for filename in ("deck.pdf", "deck.pptx", "deck.html"):
        try:
            data, _ = request(args.base_url, f"/decks/{quote(deck_id, safe='')}/a/files/{filename}", timeout=args.request_timeout)
        except DemoError as exc:
            if filename == "deck.pdf":
                raise
            manifest.setdefault("optional_download_errors", []).append(str(exc))
            continue
        (run_dir / filename).write_bytes(data)
    slide_files = []
    for index, image_url in enumerate(variant.get("slide_images", []), start=1):
        data, _ = request(args.base_url, image_url.split("?", 1)[0], timeout=args.request_timeout)
        image_path = run_dir / "slides" / f"slide-{index:03d}.png"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(data)
        slide_files.append(image_path)
    if not slide_files:
        raise DemoError("Unknown-template deck has no rendered slide images")
    make_contact_sheet(slide_files, run_dir / "contact-sheet.png")
    run_data, _ = request(args.base_url, f"/decks/{quote(deck_id, safe='')}/run", timeout=args.request_timeout)
    write_json(run_dir / "run.json", json.loads(run_data))
    record = {"deck_id": deck_id, "design_system_id": design_id, "template": str(template), "variant": "a",
              "status": variant.get("status"), "slide_count": len(slide_files), "output_dir": str(run_dir),
              "contact_sheet": str(run_dir / "contact-sheet.png"), "unknown_template": True}
    manifest["unknown_template_run"] = record
    manifest["runs"] = [item for item in manifest.get("runs", []) if not item.get("unknown_template")]
    manifest["runs"].append(record)
    manifest["pdf_count"] = len(list(output.rglob("deck.pdf")))
    manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
    write_json(manifest_path, manifest)
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("DESIGNER_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--template", action="append", type=Path, help="PPTX template path; pass exactly three times for challenge runs")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--content-dir", type=Path, help="Optional directory of five to seven CSV/XLSX/JSON/text datasets")
    parser.add_argument("--resume-deck", action="append", default=[], help="Existing job ID for the corresponding template; repeat in template order to resume without regeneration")
    parser.add_argument("--request-timeout", type=float, default=90)
    parser.add_argument("--generation-timeout", type=float, default=1800)
    parser.add_argument("--poll-interval", type=float, default=3)
    parser.add_argument("--foreign-template", type=Path, help="Optional public PPTX outside the challenge templates; generates one additional A variant")
    parser.add_argument("--only-foreign", action="store_true", help="Run only the unknown-template demonstration, using saved stage-two insights")
    args = parser.parse_args()
    try:
        if args.only_foreign:
            if not args.foreign_template:
                raise DemoError("--only-foreign requires --foreign-template")
            manifest = run_unknown_template(args)
        else:
            manifest = run(args)
    except DemoError as exc:
        print(f"stage2 demo failed: {exc}", file=sys.stderr)
        return 1
    print((f"Updated stage-two manifest with unknown-template run: {manifest}"
           if args.only_foreign else f"Created 9 PDFs, run manifest: {manifest}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
