"""Verify the archived demo migration and publish a separate, unlocked flat folder."""
import hashlib
import json
import shutil
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/stage2-demo'
before = json.loads((OUT / 'reference-compact-runtime-before.json').read_text(encoding='utf-8'))
reports = json.loads((OUT / 'reference-compact-migrations.json').read_text(encoding='utf-8'))
target = OUT / 'Все презентации — компактно'
target.mkdir(exist_ok=True)
labels = {'6b57bd92f26041b78f94df1706d2a80a': 'Education',
          '664bf9e00de04590a028a6cb0e2c92a3': 'VK Tech',
          'bdb8e8a2f7164f9094e98d351bfceed7': 'WorkSpace',
          '325c31043ccc4acf8411fe2a734e354f': 'Незнакомый шаблон'}
manifest = json.loads((OUT / 'final-v3/run-manifest.json').read_text(encoding='utf-8'))
directories = {(r['deck_id'], r['variant']): Path(r['output_dir']) for r in manifest['runs']}
checks = []
for deck_id, label in labels.items():
    with urllib.request.urlopen(f'http://localhost:8090/decks/{deck_id}', timeout=60) as response:
        current = json.load(response)
    for variant, state in current['variants'].items():
        old = before[deck_id]['variants'][variant]
        report = next(r for r in reports if r['deck_id'] == deck_id and r['variant'] == variant)
        old_charts = {s['id']: s['chart'] for s in old['plan']['slides'] if s.get('chart')}
        new_charts = {s['id']: s['chart'] for s in state['plan']['slides'] if s.get('chart')}
        assert new_charts == old_charts, 'Analytical chart changed'
        sources = lambda plan: {(s['provenance']['dataset_id'], s['provenance']['source_sha256']) for s in plan['slides'] if s.get('provenance')}
        assert sources(state['plan']) == sources(old['plan'])
        old_tables = {s['id']: s for s in old['plan']['slides'] if s.get('table') and s['provenance']['file_name'] != 'reference_201.csv'}
        for s in state['plan']['slides']:
            if s['id'] in old_tables:
                assert s['table'] == old_tables[s['id']]['table']
        ref = [s for s in state['plan']['slides'] if (s.get('provenance') or {}).get('file_name') == 'reference_201.csv']
        assert len(ref) == 1 and len(ref[0]['table']['rows']) == 7
        assert ref[0]['provenance']['total_rows'] == 201
        assert len(state['slide_images']) == len(state['plan']['slides'])
        checks.append({'deck_id': deck_id, 'variant': variant, 'before': len(old['plan']['slides']),
                       'after': len(state['plan']['slides']), 'chart_arrays_unchanged': True,
                       'source_identities_unchanged': True, 'removed_instruction_echo_ids': report['removed_instruction_echo_ids']})
        if label == 'Незнакомый шаблон' and variant != 'a':
            continue
        directory = directories.get((deck_id, variant), OUT / 'compact-unknown-template')
        directory.mkdir(exist_ok=True)
        for name in ['deck.pptx', 'deck.pdf', 'deck.html', 'deck.sources.zip', 'sources-manifest.json']:
            if label == 'Незнакомый шаблон':
                with urllib.request.urlopen(f'http://localhost:8090/decks/{deck_id}/{variant}/files/{name}', timeout=120) as response:
                    (directory / name).write_bytes(response.read())
            if name != 'sources-manifest.json':
                shutil.copy2(directory / name, target / f'{label} — {variant.upper()}.{name[5:]}')
        with zipfile.ZipFile(directory / 'deck.sources.zip') as z:
            for source in json.loads(z.read('sources-manifest.json'))['datasets']:
                raw = (OUT / 'content-v2' / source['file_name']).read_bytes()
                assert z.read(source['original_path']) == raw
                table = json.loads(z.read(source['table_path']))
                assert len(table['rows']) == source['total_rows']
                if source['file_name'] == 'reference_201.csv':
                    assert len(table['rows']) == 201
                    assert table['rows'][-1][0] == 'REF-201'

suites = list(ET.parse(OUT / 'reference-compact-final-tests.xml').iter('testsuite'))
assert all(int(s.get('failures', 0)) == int(s.get('errors', 0)) == 0 for s in suites)
result = {'status': 'passed', 'checks': checks, 'files': {
    p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in target.iterdir() if p.is_file()},
    'backend': [{k: s.get(k) for k in ('tests', 'failures', 'errors', 'skipped')} for s in suites]}
(OUT / 'reference-compact-verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
(target / 'ПРОЧИТАЙТЕ.md').write_text('''# Обновлённые презентации

9 результатов на Education, VK Tech и WorkSpace; отдельно результат на стороннем шаблоне.
Справочник показан одним слайдом: первые 7 из 201 строк, без выдуманных выводов.
Для полной таблицы откройте HTML → «Источники» → поиск либо архив *.sources.zip.
При отправке PPTX/PDF приложите одноимённый архив исходников.
Оригинальные английские подписи в исходниках сохранены намеренно; слайды на русском.
Все числа учебные, синтетические. Это не реальные показатели компаний.
Предыдущие файлы и резервные копии сохранены. Старое видео показывает прежнюю версию.
''', encoding='utf-8')
print(json.dumps({'status': 'passed', 'variants': len(checks), 'flat_folder': str(target)}, ensure_ascii=False))
