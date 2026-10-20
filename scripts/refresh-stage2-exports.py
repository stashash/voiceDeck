"""Refresh the nine delivered decks through the running latest local image."""
from pathlib import Path
import importlib.util
import json
import subprocess
import sys
import urllib.request
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"artifacts/stage2-demo/final-v3"
manifest=json.loads((OUT/"run-manifest.json").read_text(encoding="utf-8"))
spec=importlib.util.spec_from_file_location("stage2",ROOT/"examples/build-stage2.py")
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
download_only="--download-only" in sys.argv
if not download_only:
    subprocess.run(["docker","compose","cp","scripts/reexport-stage2-runtime.py","designer:/tmp/reexport-stage2-runtime.py"],cwd=ROOT,check=True)
for run in manifest["runs"]:
    deck_id,variant=run["deck_id"],run["variant"]
    if not download_only:
        subprocess.run(["docker","compose","exec","-T","designer","python","/tmp/reexport-stage2-runtime.py",deck_id,variant],cwd=ROOT,check=True)
    with urllib.request.urlopen(f"http://127.0.0.1:8090/decks/{deck_id}",timeout=60) as response: state=json.load(response)
    directory=Path(run["output_dir"])
    for name in ["deck.pptx","deck.pdf","deck.html"]:
        with urllib.request.urlopen(f"http://127.0.0.1:8090/decks/{deck_id}/{variant}/files/{name}",timeout=120) as response:
            (directory/name).write_bytes(response.read())
    images=[]
    for index,url in enumerate(state["variants"][variant]["slide_images"],1):
        target=directory/"slides"/f"slide-{index:03}.png"
        with urllib.request.urlopen("http://127.0.0.1:8090"+url,timeout=60) as response: target.write_bytes(response.read())
        images.append(target)
    module.make_contact_sheet(images,directory/"contact-sheet.png")
    run["final_exported_at"]=datetime.now(timezone.utc).isoformat()
    run["final_export_preserved_plan"]=True
    run["final_export_locale"]=state["variants"][variant]["plan"].get("language","ru")
    (OUT/"run-manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
print("Nine final exports refreshed without regenerating source facts")
