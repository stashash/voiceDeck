"""Девять презентаций: три выданных шаблона на три варианта вёрстки через поднятый сервис designer.

Запуск из корня репозитория при работающем `docker compose up -d`:
    python examples/build.py examples/brief.txt
Кладёт в examples/<id дизайн-системы>/<вариант>/ файлы deck.pptx, deck.html, deck.pdf,
лист слайдов sheet.jpg и карточку прогона run.json; итог по времени в examples/build.log.
"""
import json
import os
import sys
import time
import urllib.request
import uuid
from pathlib import Path

from PIL import Image

API = os.environ.get("DESIGNER_API", "http://localhost:8090")
ROOT = Path(__file__).resolve().parent
TEMPLATES = ROOT.parent / "docs" / "requirements" / "template"


def _post(path: str, data: bytes, ctype: str = "application/json; charset=utf-8") -> dict:
    req = urllib.request.Request(API + path, data=data, headers={"Content-Type": ctype})
    return json.loads(urllib.request.urlopen(req, timeout=900).read())


def _get(path: str) -> dict:
    return json.loads(urllib.request.urlopen(API + path, timeout=60).read())


def _upload(path: Path) -> dict:
    boundary = uuid.uuid4().hex
    name = path.name.encode("utf-8").decode("latin-1")
    head = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n").encode("latin-1")
    body = head + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    return _post("/design-systems", body, f"multipart/form-data; boundary={boundary}")


def _sheet(pngs: list[Path], out: Path, cols: int = 4, tile: tuple[int, int] = (480, 270)) -> None:
    rows = (len(pngs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tile[0], rows * tile[1]), "#888")
    for i, png in enumerate(pngs):
        tile_img = Image.open(png).convert("RGB").resize((tile[0] - 4, tile[1] - 4))
        sheet.paste(tile_img, ((i % cols) * tile[0] + 2, (i // cols) * tile[1] + 2))
    sheet.save(out, quality=85)


def main(brief_path: str) -> None:
    brief = Path(brief_path).read_text(encoding="utf-8")
    log: list[str] = []
    for template in sorted(TEMPLATES.glob("*.pptx")):
        started = time.time()
        ds = _upload(template)
        log.append(f"{template.name}: импорт {time.time() - started:.0f} с, id {ds['id']}, паттернов {len(ds['patterns'])}")
        print(log[-1], flush=True)
        started = time.time()
        payload = {"design_system_id": ds["id"], "brief": brief, "purpose": "Инициатива",
                   "audience": "Директора направлений", "variants": ["a", "b", "c"]}
        deck_id = _post("/decks", json.dumps(payload, ensure_ascii=False).encode("utf-8"))["deck_id"]
        while True:
            time.sleep(15)
            state = _get(f"/decks/{deck_id}")
            statuses = {k: v["status"] for k, v in state["variants"].items()}
            if all(s in ("done", "error") for s in statuses.values()) or time.time() - started > 900:
                break
        findings = {k: len(v["findings"]) for k, v in state["variants"].items()}
        log.append(f"{template.name}: колода {deck_id} {statuses} за {time.time() - started:.0f} с, находок {findings}")
        print(log[-1], flush=True)
        for variant, item in state["variants"].items():
            out = ROOT / ds["id"] / variant
            out.mkdir(parents=True, exist_ok=True)
            for name in ("deck.pptx", "deck.html", "deck.pdf"):
                urllib.request.urlretrieve(f"{API}/decks/{deck_id}/{variant}/files/{name}", out / name)
            pngs = []
            for i, url in enumerate(item["slide_images"], 1):
                png = out / f"slide-{i:02d}.png"
                urllib.request.urlretrieve(API + url, png)
                pngs.append(png)
            _sheet(pngs, out / "sheet.jpg")
            for png in pngs:
                png.unlink()
            run = _get(f"/decks/{deck_id}/run") if variant == "a" else {"deck_id": deck_id, "variant": variant}
            (out / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
    (ROOT / "build.log").write_text("\n".join(log) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "brief.txt"))
