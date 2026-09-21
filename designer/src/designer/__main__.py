"""CLI: `python -m designer serve` поднимает сервис, `python -m designer deck` собирает колоду без сервера.

Владелец: задача T-13.
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


def _deck(pptx_path: str, brief_path: str, out_dir: str) -> None:
    design_system = pipeline.import_template(Path(pptx_path).read_bytes(), Path(pptx_path).name)
    brief = Path(brief_path).read_text(encoding="utf-8")

    def _on_event(event: pipeline.PipelineEvent) -> None:
        slide = f" слайд {event.slide_index + 1}" if event.slide_index is not None else ""
        print(f"[{event.step}]{slide}", file=sys.stderr)

    deck = pipeline.generate_deck(design_system.id, brief, "", "", None, _on_event)

    files_dir = store.deck_files_dir(deck.id)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name in ("deck.pptx", "deck.html", "deck.pdf"):
        source = files_dir / name
        if source.is_file():
            (out / name).write_bytes(source.read_bytes())
    print(f"готово: {deck.id}", file=sys.stderr)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="designer")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("serve")
    deck_parser = sub.add_parser("deck")
    deck_parser.add_argument("pptx")
    deck_parser.add_argument("brief")
    deck_parser.add_argument("out_dir")

    args = parser.parse_args(argv)
    if args.command == "serve":
        _serve()
    else:
        _deck(args.pptx, args.brief, args.out_dir)


if __name__ == "__main__":
    main()
