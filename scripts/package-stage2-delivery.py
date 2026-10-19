"""Package only verified final outputs; exclude failed captures and temporary renders."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import subprocess
from zipfile import ZipFile, ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"artifacts/stage2-demo"
verification=json.loads((OUT/"delivery-verification.json").read_text(encoding="utf-8"))
edit=json.loads((OUT/"screencast/edit-manifest.json").read_text(encoding="utf-8"))
capture=json.loads((OUT/"screencast/capture-manifest.json").read_text(encoding="utf-8"))
assert verification["status"]==capture["status"]=="passed" and edit["duration"]<=300
commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
entries={}
def add(source, target):
    path=Path(source)
    assert path.is_file(),path
    entries[target]=path
for run in json.loads((OUT/"final-v3/run-manifest.json").read_text(encoding="utf-8"))["runs"]:
    directory=Path(run["output_dir"])
    for name in ["deck.pdf","deck.pptx","deck.html","contact-sheet.png"]:
        add(directory/name,"challenge/"+directory.parent.name+"/"+run["variant"]+"/"+name)
for name in ["deck.pdf","deck.pptx","deck.html","VoiceDeck-stage2-screencast.mp4","subtitles.srt","capture-manifest.json","edit-manifest.json"]:
    add(OUT/"screencast"/name,"unknown-template/"+name)
for path in (OUT/"screencast/audio").glob("*.json"):add(path,"unknown-template/audio/"+path.name)
for path in (OUT/"content-v2").iterdir():
    if path.is_file():add(path,"content/"+path.name)
for path in (ROOT/"frontend/public/brandbooks").iterdir():add(path,"brandbooks/"+path.name)
add(ROOT/"examples/brandbooks/README.md","brandbooks/README.md")
add(ROOT/"examples/brandbooks/local-demo-fig.md","brandbooks/figma-provenance.md")
for name in ["README.md","LICENSE.txt","90s-consulting-strategy-slides.pptx"]:
    path=OUT/"sources"/name
    if path.is_file():add(path,"sources/"+name)
for name in ["delivery-verification.json","challenge-verification.json","backend-final-tests.xml","figma-browser-verification.json","runtime-verification.json"]:
    add(OUT/name,"verification/"+name)
add(OUT/"final-v3/run-manifest.json","verification/run-manifest.json")
add(ROOT/"docs/stage2-implementation-and-verification.md","verification/implementation.md")
readme=f"""# VoiceDeck — вторая ступень\n\nДата сборки: {datetime.now(timezone.utc).isoformat()}\nКод: `{commit}`.\n\n- `challenge/`: 9 презентаций — A/B/C × Education/VK Tech/WorkSpace, по три формата и контрольный лист.\n- `unknown-template/VoiceDeck-stage2-screencast.mp4`: реальный скринкаст с локальной озвучкой, {edit['duration']:.1f} с. Долгое ожидание модели ускорено и подписано; без подмены сетевых ответов.\n- `unknown-template/deck.*`: результат на стороннем общедоступном шаблоне с брендбуком.\n- `content/`: семь синтетических источников. Это учебные числа, не результаты реальной компании.\n- `brandbooks/`: JSON, PDF, бинарный Figma и ZIP-примеры.\n- `verification/`: проверка файлов, источников, всех 201 строк, тесты и фактический runtime.\n\nРедактор текущего локального сервиса: http://localhost:8088/#/decks/{capture['deckId']}/edit/a\n\nСторонний шаблон: Templates by ppttemplate.ai (CC BY 4.0), https://ppttemplate.ai/templates/90s-consulting-strategy-slides . Исходник и атрибуция в sources/.\n\nГраницы импорта и аудита описаны в verification/implementation.md. Аудио прошло техническую проверку и локальную ASR-сверку; это не человеческая оценка дикторской работы. Полная исходная экранная запись сохранена рядом с роликом в рабочем каталоге сервиса.\n"""
checksum={name:{"bytes":path.stat().st_size,"sha256":hashlib.sha256(path.read_bytes()).hexdigest()} for name,path in entries.items()}
archive=OUT/"VoiceDeck-stage2-delivery.zip"
with ZipFile(archive,"w",compression=ZIP_DEFLATED,compresslevel=6) as output:
    output.writestr("README.md",readme)
    output.writestr("SHA256.json",json.dumps(checksum,ensure_ascii=False,indent=2))
    for target,path in entries.items():output.write(path,target)
with ZipFile(archive) as check:assert check.testzip() is None
(OUT/"package-verification.json").write_text(json.dumps({"archive":str(archive),"bytes":archive.stat().st_size,
    "sha256":hashlib.sha256(archive.read_bytes()).hexdigest(),"files":len(entries)+2,"zipIntegrity":"passed","commit":commit},indent=2),encoding="utf-8")
print(str(archive))
