"""Package only verified final outputs; exclude failed captures and temporary renders."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import subprocess
import html
from urllib.parse import quote
import xml.etree.ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"artifacts/stage2-demo"
verification=json.loads((OUT/"delivery-verification.json").read_text(encoding="utf-8"))
edit=json.loads((OUT/"screencast/edit-manifest.json").read_text(encoding="utf-8"))
capture=json.loads((OUT/"screencast/capture-manifest.json").read_text(encoding="utf-8"))
assert verification["status"]==capture["status"]=="passed" and edit["duration"]<=300
separation=json.loads((OUT/"separation-verification.json").read_text(encoding="utf-8"))
assert separation["status"]=="passed" and separation["challengeCount"]==9
assert separation["video"]["deckId"]==capture["deckId"]
assert separation["video"]["sha256"]==hashlib.sha256(Path(edit["finalVideo"]).read_bytes()).hexdigest()
media=json.loads((OUT/"presubmission-video-verification.json").read_text(encoding="utf-8"))
assert media["status"]=="passed" and media["fullDecode"]=="passed" and media["duration"]<=300
assert media["sha256"]==separation["video"]["sha256"]
assert any(c["unknownTemplate"] and c["deckId"]==capture["deckId"] for c in verification["checks"])
for item in verification["files"]:
    assert hashlib.sha256((ROOT/item["path"]).read_bytes()).hexdigest()==item["sha256"], item["path"]
commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
dirty=bool(subprocess.check_output(["git","status","--porcelain","--untracked-files=no"],cwd=ROOT,text=True).strip())
final_tests=OUT/"presubmission-backend-final.xml"
if final_tests.exists():
    suites=list(ET.parse(final_tests).getroot().iter("testsuite"))
    assert suites and all(int(s.get("failures",0))==int(s.get("errors",0))==0 for s in suites), "Latest presubmission tests failed"
entries={}
def add(source, target):
    path=Path(source)
    assert path.is_file(),path
    entries[target]=path
index_rows=[]
labels={(item["deckId"],item["variant"]):item["template"] for item in separation["challengePresentations"]}
for run in json.loads((OUT/"final-v3/run-manifest.json").read_text(encoding="utf-8"))["runs"]:
    directory=Path(run["output_dir"])
    label=labels[(run["deck_id"],run["variant"])]
    target_dir="challenge/"+label+"/"+run["variant"].upper()
    for name in ["deck.pdf","deck.pptx","deck.html","contact-sheet.png"]:
        add(directory/name,target_dir+"/"+name)
    links=" · ".join(f'<a href="{quote(target_dir+"/deck."+ext)}">{ext.upper()}</a>' for ext in ["pdf","pptx","html"])
    index_rows.append(f'<tr><td>{html.escape(label)}</td><td>{run["variant"].upper()}</td><td>{links}</td></tr>')
for name in ["deck.pdf","deck.pptx","deck.html","VoiceDeck-stage2-screencast.mp4","subtitles.srt","capture-manifest.json","edit-manifest.json","video-contact-sheet.jpg"]:
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
for name in ["delivery-verification.json","challenge-verification.json","separation-verification.json","backend-final-tests.xml","figma-browser-verification.json","runtime-verification.json"]:
    add(OUT/name,"verification/"+name)
for name in ["presubmission-backend-final.xml","presubmission-runtime-checks.json","presubmission-public-browser.json","presubmission-compression.json","presubmission-video-verification.json","presubmission-fresh-generation.json","presubmission-live-audio.log","presubmission-editor-smoke.log"]:
    if (OUT/name).exists():add(OUT/name,"verification/"+name)
for name in ["presubmission-audit-2026-10-19.md","presubmission-data-audit.md"]:
    if (ROOT/"docs"/name).exists():add(ROOT/"docs"/name,"verification/"+name)
add(OUT/"final-v3/run-manifest.json","verification/run-manifest.json")
add(ROOT/"docs/stage2-implementation-and-verification.md","verification/implementation.md")
readme=f"""# VoiceDeck — вторая ступень\n\nДата сборки: {datetime.now(timezone.utc).isoformat()}\nБазовый коммит: `{commit}`. Незакоммиченные изменения: `{dirty}`; фактические Python-исходники контейнера перечислены в runtime-verification.json.\n\n- `challenge/`: 9 презентаций — A/B/C × Education/VK Tech/WorkSpace, по три формата и контрольный лист.\n- `unknown-template/VoiceDeck-stage2-screencast.mp4`: реальный скринкаст с локальной озвучкой, {edit['duration']:.1f} с. Долгое ожидание модели ускорено и подписано; без подмены сетевых ответов.\n- `unknown-template/deck.*`: результат на стороннем общедоступном шаблоне с брендбуком.\n- `content/`: семь синтетических источников. Это учебные числа, не результаты реальной компании.\n- `brandbooks/`: JSON, PDF, бинарный Figma и ZIP-примеры.\n- `verification/`: проверка файлов, источников, всех 201 строк, тесты и фактический runtime.\n\nРедактор текущего локального сервиса: http://localhost:8088/#/decks/{capture['deckId']}/edit/a\n\nСторонний шаблон: Templates by ppttemplate.ai (CC BY 4.0), https://ppttemplate.ai/templates/90s-consulting-strategy-slides . Исходник и атрибуция в sources/.\n\nГраницы импорта и аудита описаны в verification/implementation.md. Аудио прошло техническую проверку и локальную ASR-сверку; это не человеческая оценка дикторской работы. Полная исходная экранная запись сохранена рядом с роликом в рабочем каталоге сервиса.\n"""
readme="Откройте START-HERE.html: девять презентаций и отдельное видео на неизвестном шаблоне.\n\n"+readme
readme+="\nЛЦТ2026 — только шаблон питча. В этом комплекте демо и девять результатов не используют его.\n"
(OUT/"README-DELIVERY.md").write_text(readme,encoding="utf-8")
add(OUT/"README-DELIVERY.md","README.md")
(OUT/"demo-brief.txt").write_text(capture["finalDeck"]["brief"],encoding="utf-8")
add(OUT/"demo-brief.txt","content/demo-brief.txt")
index=f'''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VoiceDeck — комплект сдачи</title>
<style>body{{font:17px system-ui;max-width:1000px;margin:40px auto;padding:0 20px;background:#f5f6fa;color:#192237}}h1{{font-size:32px}}table{{width:100%;border-collapse:collapse;background:white}}td,th{{text-align:left;border-bottom:1px solid #dde1eb;padding:12px}}a{{color:#5930c8}}video{{width:100%;background:#101217;border-radius:12px}}section{{margin:36px 0}}p{{line-height:1.6}}</style>
<h1>VoiceDeck — вторая ступень</h1><p>Два отдельных результата: 9 презентаций на выданных шаблонах и сквозное видео на стороннем шаблоне. Учебные данные синтетические.</p>
<section><h2>1. Девять презентаций: 3 × 3</h2><table><tr><th>Шаблон</th><th>Вариант</th><th>Открыть результат</th></tr>{''.join(index_rows)}</table></section>
<section><h2>2. Видео на неизвестном шаблоне</h2><p>90s Consulting Strategy Slides — открытый сторонний PPTX, не VK Tech, WorkSpace, Education или ЛЦТ2026. Реальная загрузка шаблона и контента → генерация локальной моделью → просмотр → скачивание. Ожидание генерации ускорено и подписано. Озвучка синтетическая, создана локально.</p>
<video controls preload="metadata" src="unknown-template/VoiceDeck-stage2-screencast.mp4"></video>
<p><a href="unknown-template/VoiceDeck-stage2-screencast.mp4">Скачать видео</a> · <a href="unknown-template/subtitles.srt">Субтитры</a> · <a href="content/demo-brief.txt">Текст контент-пакета</a></p>
<p>Результат прогона: <a href="unknown-template/deck.pdf">PDF</a> · <a href="unknown-template/deck.pptx">PPTX</a> · <a href="unknown-template/deck.html">HTML</a>.</p>
<p>Источник: <a href="https://ppttemplate.ai/templates/90s-consulting-strategy-slides">Templates by ppttemplate.ai</a>, CC BY 4.0. Исходник и лицензия в sources/.</p></section>
<section><h2>Проверка разделения</h2><p><a href="verification/separation-verification.json">Хеши трёх выданных и стороннего шаблона, матрица 9 результатов и видео</a>. ЛЦТ2026 предназначен только для питча и в демо не используется.</p></section></html>'''
(OUT/"START-HERE.html").write_text(index,encoding="utf-8")
add(OUT/"START-HERE.html","START-HERE.html")
checksum={name:{"bytes":path.stat().st_size,"sha256":hashlib.sha256(path.read_bytes()).hexdigest()} for name,path in entries.items()}
archive=OUT/"VoiceDeck-stage2-delivery.zip"
with ZipFile(archive,"w",compression=ZIP_DEFLATED,compresslevel=6) as output:
    output.writestr("SHA256.json",json.dumps(checksum,ensure_ascii=False,indent=2))
    for target,path in entries.items():output.write(path,target)
with ZipFile(archive) as check:assert check.testzip() is None
(OUT/"package-verification.json").write_text(json.dumps({"archive":str(archive),"bytes":archive.stat().st_size,
    "sha256":hashlib.sha256(archive.read_bytes()).hexdigest(),"files":len(entries)+1,"zipIntegrity":"passed","commit":commit,"workingTreeDirty":dirty},indent=2),encoding="utf-8")
print(str(archive))
