"""CLI: `python -m designer serve` поднимает сервис, `python -m designer deck` собирает колоду без сервера.

Владелец: задача T-13, ключ --variants — T-12.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from designer import pipeline, store


def _serve() -> None:
    import uvicorn

    port = int(os.environ.get("DESIGNER_PORT", "8090"))
    uvicorn.run("designer.api.app:app", host="0.0.0.0", port=port)


def _deck(pptx_path: str, brief_path: str, out_dir: str, variant_codes: list[str]) -> None:
    design_system = pipeline.import_template(Path(pptx_path).read_bytes(), Path(pptx_path).name)
    brief = Path(brief_path).read_text(encoding="utf-8")

    def _on_event(event: pipeline.PipelineEvent) -> None:
        slide = f" слайд {event.slide_index + 1}" if event.slide_index is not None else ""
        variant = f" [{event.variant}]" if event.variant else ""
        print(f"[{event.step}]{variant}{slide}", file=sys.stderr)

    deck = pipeline.generate_deck(design_system.id, brief, "", "", None, _on_event, variants=variant_codes)

    out = Path(out_dir)
    single = len(variant_codes) == 1
    for variant in variant_codes:
        files_dir = store.deck_variant_files_dir(deck.id, variant)
        variant_out = out if single else out / variant
        variant_out.mkdir(parents=True, exist_ok=True)
        for name in ("deck.pptx", "deck.html", "deck.pdf"):
            source = files_dir / name
            if source.is_file():
                (variant_out / name).write_bytes(source.read_bytes())
    print(f"готово: {deck.id}", file=sys.stderr)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="designer")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("serve")
    deck_parser = sub.add_parser("deck")
    deck_parser.add_argument("pptx")
    deck_parser.add_argument("brief")
    deck_parser.add_argument("out_dir")
    deck_parser.add_argument("--variants", default="a", help="через запятую: a,b,c")

    args = parser.parse_args(argv)
    if args.command == "serve":
        _serve()
    else:
        variant_codes = [v.strip() for v in args.variants.split(",") if v.strip()]
        _deck(args.pptx, args.brief, args.out_dir, variant_codes)


if __name__ == "__main__":
    main()
