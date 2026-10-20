"""Acceptance gate: 3 provided templates x ABC, plus a separate external-template video.

Run after record-stage2-demo.cjs, assemble-stage2-screencast.py and
verify-stage2-delivery.py. Does not generate or modify presentation content.
"""
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import subprocess
from urllib.request import urlopen
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/stage2-demo"
TEMPLATES = {
    "VK Tech шаблон.pptx": "VK Tech",
    "VK_WorkSpace_Клиентская_конференция_Шаблон_03.pptx": "WorkSpace",
    "Шаблон презентации VK Education.pptx": "Education",
}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runtime_source_hash(design_id):
    # The ID is passed as an argv value, never interpolated into Python or shell.
    program = ('import sys,hashlib; from designer import store; '
               'p=store.design_system_dir(sys.argv[1])/"source.pptx"; '
               'print(hashlib.sha256(p.read_bytes()).hexdigest())')
    return subprocess.check_output([
        "docker", "compose", "exec", "-T", "designer", "python", "-c", program, design_id,
    ], cwd=ROOT, text=True).strip()


def verify():
    manifest = read(OUT / "final-v3/run-manifest.json")
    delivery = read(OUT / "delivery-verification.json")
    capture = read(OUT / "screencast/capture-manifest.json")
    edit = read(OUT / "screencast/edit-manifest.json")
    assert delivery["status"] == "passed" and len(delivery["checks"]) == 10
    templates = manifest["templates"]
    assert len(templates) == 3
    assert {Path(t["template"]).name for t in templates} == set(TEMPLATES)
    provided_hashes = {}
    matrix = []
    states = {}
    for template in templates:
        path = Path(template["template"])
        assert path.resolve().parent == (ROOT / "docs/requirements/template").resolve()
        fingerprint = sha(path)
        assert runtime_source_hash(template["design_system_id"]) == fingerprint
        provided_hashes[path.name] = fingerprint
        pairs = {(r["deck_id"], r["variant"]) for r in template["decks"]}
        runs = [r for r in manifest["runs"] if (r["deck_id"], r["variant"]) in pairs]
        assert Counter(r["variant"] for r in runs) == Counter({"a": 1, "b": 1, "c": 1})
        for run in runs:
            if run["deck_id"] not in states:
                with urlopen("http://127.0.0.1:8090/decks/" + quote(run["deck_id"], safe=""), timeout=30) as response:
                    states[run["deck_id"]] = json.load(response)
            assert states[run["deck_id"]]["variants"][run["variant"]]["design_system_id"] == template["design_system_id"]
            directory = Path(run["output_dir"])
            assert all((directory / ("deck." + ext)).is_file() for ext in ["pdf", "pptx", "html"])
            matrix.append({"template": TEMPLATES[path.name], "variant": run["variant"],
                           "sourceSha256": fingerprint, "deckId": run["deck_id"],
                           "outputDirectory": str(directory), "files": ["deck.pdf", "deck.pptx", "deck.html"]})
    assert len(manifest["runs"]) == len(matrix) == 9 and len(set(provided_hashes.values())) == 3

    external = OUT / "sources/90s-consulting-strategy-slides.pptx"
    external_hash = sha(external)
    assert external_hash not in provided_hashes.values()
    assert capture["designSystemId"] not in {t["design_system_id"] for t in templates}
    assert runtime_source_hash(capture["designSystemId"]) == external_hash
    assert "лцт" not in external.name.casefold() and "lct2026" not in external.name.casefold()
    assert capture["status"] == "passed" and capture["networkMocks"] is False
    assert not capture["browserErrors"] and not capture["errors"]
    stages = capture["stages"]
    required = ["home", "template-upload-start", "template-upload-end", "content-upload", "analysis-ready",
                "generation-wait-start", "generation-wait-end", "editor-ready", "result-slide", "export-options", "complete"]
    cursor = -1
    for name in required:
        cursor = next(i for i in range(cursor + 1, len(stages)) if stages[i]["name"] == name)
    assert all(a["seconds"] <= b["seconds"] for a, b in zip(stages, stages[1:]))
    assert {s.get("kind") for s in stages if s["name"] == "result-slide"} >= {"trend", "shares", "comparison"}
    assert capture["finalDeck"]["brief"].strip()
    assert all(capture["finalDeck"]["variants"][v]["status"] == "done" for v in "abc")
    assert edit["actualUiCapture"] and edit["networkMocks"] is False and edit["narrationLocalOnly"]
    assert 0 < edit["duration"] <= 300 and Path(edit["finalVideo"]).stat().st_size > 1_000_000
    assert edit["sourceVideo"] == capture["rawVideo"] and Path(capture["rawVideo"]).is_file()
    assert {p["name"] for p in edit["timeline"]} >= {"template", "content", "generate", "editor", "export"}
    for part in edit["timeline"]:
        assert part["sourceVideo"] == capture["rawVideo"]
        assert 0 <= part["sourceStart"] < part["sourceEnd"] <= stages[-1]["seconds"] + .01
        assert sha(Path(part["audio"]["file"])) == part["audio"]["sha256"]

    # Inspect the application engines, excluding demo scripts, fixtures and docs.
    # This detects direct template-name special cases; it is not a proof about
    # every possible form of tuning. The real upload/generation remains essential.
    markers = ["90s-consulting-strategy-slides", "90s consulting strategy slides"]
    special_cases = []
    for tree in ["designer/src", "frontend/src", "backend/src/main"]:
        for file in (ROOT / tree).rglob("*"):
            if file.suffix in {".py", ".ts", ".tsx", ".java"}:
                text = file.read_text(encoding="utf-8-sig").casefold()
                if any(m in text for m in markers):
                    special_cases.append(str(file.relative_to(ROOT)))
    assert not special_cases, special_cases
    result = {"status": "passed", "checkedAt": datetime.now(timezone.utc).isoformat(),
              "challengePresentations": matrix, "challengeCount": 9,
              "externalTemplate": {"source": "https://ppttemplate.ai/templates/90s-consulting-strategy-slides",
                  "file": str(external), "sha256": external_hash, "license": "CC BY 4.0",
                  "attribution": "Templates by ppttemplate.ai", "designSystemId": capture["designSystemId"]},
              "video": {"file": edit["finalVideo"], "sha256": sha(Path(edit["finalVideo"])),
                        "deckId": capture["deckId"], "seconds": edit["duration"],
                        "captureStartedAt": capture["startedAt"], "networkMocks": False,
                        "datasetTemplate": False, "pitchTemplateUsed": False},
              "applicationTemplateNameSpecialCases": special_cases,
              "limits": ["The name scan detects literal special cases, not all possible tuning.",
                         "Generation waiting is compressed and explicitly labelled in the final video."]}
    (OUT / "separation-verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "passed", "challengePresentations": 9, "externalVideoSeconds": edit["duration"]}))


if __name__ == "__main__":
    verify()
