"""CLI: python -m designer.parse <файл.pptx> <каталог> — собирает пакет дизайн-системы."""
from __future__ import annotations

import sys
from pathlib import Path

from designer.parse.package import build_package


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("использование: python -m designer.parse <файл.pptx> <каталог>", file=sys.stderr)
        return 2
    pptx_path = Path(argv[0])
    out_dir = Path(argv[1])
    design_system = build_package(pptx_path, out_dir)
    print(
        f"{design_system.id}: цветов {len(design_system.tokens.colors)}, "
        f"шрифтов {len(design_system.tokens.fonts)}, "
        f"картинок {len(design_system.assets)} -> {out_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
