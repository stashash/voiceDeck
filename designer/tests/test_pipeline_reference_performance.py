"""Bound automatic model work without weakening source or deterministic checks."""
import json
from types import SimpleNamespace

from designer import pipeline, store
from designer.contracts import DataProvenance, DeckPlan, Scene, SlideIntent, SlideKind, SlideSpec, TableSpec
from designer.llm.run import RunRecorder


def reference_page(page, count=29, dataset='source'):
    return SlideIntent(id=f'{dataset}-{page}', kind=SlideKind.table, title=f'Приложение {page}',
        key_message='Exact source value 8; empty cell remains missing.', notes='Источник: source.csv',
        table=TableSpec(columns=['actual', 'planned'], rows=[['8', '']]),
        provenance=DataProvenance(dataset_id=dataset, source_sha256='a' * 64, content_hash='b' * 64,
            file_name='source.csv', table_index=0, columns=['actual', 'planned'], total_rows=201,
            row_lines=list(range(2, 203)), excluded_row_lines=[], displayed_row_lines=[page + 1],
            visualization='table', aggregation='none', missing_policy='preserve_all_rows', formula='Source rows',
            page_index=page, page_count=count))


def appendix_plan():
    return DeckPlan(title='Review', purpose='review', slides=[
        SlideIntent(id='main', kind=SlideKind.title, title='Main message'),
        *[reference_page(i) for i in range(1, 30)],
        SlideIntent(id='next', kind=SlideKind.cta, title='Next step'),
    ])


def test_source_insight_returns_a_deep_copy_without_any_model_or_limit_work(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Deterministic source slides must not invoke this path')
    monkeypatch.setattr(pipeline, 'fill_slots', forbidden)
    monkeypatch.setattr(pipeline, '_role_limits', forbidden)
    monkeypatch.setattr(pipeline, 'main_group', forbidden)
    source = reference_page(3)
    before = source.model_dump()
    result = pipeline._fill_intent(source, None, None, forbidden, 0)
    assert result.model_dump() == before and result is not source
    result.table.rows[0][0] = 'mutated'
    result.provenance.displayed_row_lines.append(999)
    assert source.model_dump() == before


def test_sampling_preserves_main_slides_and_each_independent_appendix_boundaries():
    plan = appendix_plan()
    plan.slides[15:15] = [reference_page(2, 3, 'other'), reference_page(1, 3, 'other'), reference_page(3, 3, 'other')]
    selected = [plan.slides[i].id for i in pipeline._automatic_contextual_indices(plan)]
    assert selected == ['main', 'source-1', 'other-1', 'other-3', 'source-29', 'next']


def test_contextual_images_deck_audit_and_advice_share_sample_but_manual_default_is_full(tmp_path, monkeypatch):
    plan = appendix_plan()
    scenes = [Scene(slide_id=slide.id, pattern_id='p') for slide in plan.slides]
    pngs = []
    for scene in scenes:
        path = tmp_path / f'{scene.slide_id}.png'
        path.write_bytes(scene.slide_id.encode())
        pngs.append(path)
    image_ids, deck_ids, advice_ids = [], [], []
    def audit_slide(scene, image, text, client):
        assert image == scene.slide_id.encode()
        image_ids.append(scene.slide_id)
        return []
    monkeypatch.setattr(pipeline, 'audit_slide', audit_slide)
    monkeypatch.setattr(pipeline, 'audit_deck', lambda selected, client: deck_ids.extend(s.slide_id for s in selected) or [])
    monkeypatch.setattr(pipeline, 'advise_deck', lambda selected, client: advice_ids.extend(s.slide_id for s in selected) or [])
    pipeline._contextual_findings(scenes, pngs, 'Source', None, selected_indices=pipeline._automatic_contextual_indices(plan))
    assert image_ids == deck_ids == advice_ids == ['main', 'source-1', 'source-29', 'next']
    image_ids.clear(); deck_ids.clear(); advice_ids.clear()
    pipeline._contextual_findings(scenes, pngs, 'Source', None)
    assert image_ids == deck_ids == advice_ids == [scene.slide_id for scene in scenes]


def test_variant_checks_every_scene_and_records_actual_automatic_scope(tmp_path, monkeypatch):
    monkeypatch.setenv(store.DATA_DIR_ENV, str(tmp_path / 'data'))
    plan = appendix_plan()
    pattern = SimpleNamespace(id='p')
    ds = SimpleNamespace(tokens=SimpleNamespace(type_scale=[]))
    checked, contextual, saved = [], [], []
    monkeypatch.setattr(pipeline, 'choose_pattern', lambda *args: pattern)
    monkeypatch.setattr(pipeline, '_fill_intent', lambda intent, *args: intent.model_copy(deep=True))
    monkeypatch.setattr(pipeline, 'compose', lambda intent, pattern, ds: SlideSpec(slide_id=intent.id, pattern_id='p'))
    monkeypatch.setattr(pipeline, 'build_scene', lambda spec, *args: Scene(slide_id=spec.slide_id, pattern_id='p'))
    monkeypatch.setattr(pipeline, 'export_pptx', lambda specs, ds, package, path: path.write_bytes(b'pptx'))
    monkeypatch.setattr(pipeline.convert, 'available', lambda: True)
    monkeypatch.setattr(pipeline.convert, 'to_pdf', lambda source, dest: dest.write_bytes(b'pdf'))
    paths = []
    for slide in plan.slides:
        path = tmp_path / f'{slide.id}.png'
        path.write_bytes(b'png')
        paths.append(path)
    monkeypatch.setattr(pipeline, '_save_slide_images', lambda *args: paths)
    monkeypatch.setattr(pipeline, 'run_checks', lambda scenes, ds: checked.extend(s.slide_id for s in scenes) or [])
    monkeypatch.setattr(pipeline, '_contextual_findings', lambda scenes, pngs, brief, client, **kwargs: contextual.extend(kwargs['selected_indices']) or [])
    monkeypatch.setattr(pipeline, 'render_deck', lambda *args: '<html/>')
    monkeypatch.setattr(pipeline, 'render_deck_images', lambda *args: '<html/>')
    monkeypatch.setattr(store, 'save_deck_result', lambda deck_id, deck, findings, **kwargs: saved.append(deck))
    pipeline._build_and_export_variant('test', 'ds', 'a', plan, [], ds, tmp_path, None, RunRecorder('mock'),
                                       lambda event: None, brief='Source', with_contextual_audit=True)
    assert checked == [slide.id for slide in plan.slides]
    assert contextual == [0, 1, 29, 30]
    metadata = json.loads((store.deck_variant_files_dir('test', 'a') / 'contextual-audit-policy.json').read_text(encoding='utf-8'))
    assert metadata['contextual_slide_ids'] == ['main', 'source-1', 'source-29', 'next']
    assert metadata['deterministic_slide_ids'] == checked
    assert len(metadata['contextual_skipped_slide_ids']) == 27
    assert metadata['manual_contextual_policy'] == 'all_scenes'
    assert 'contextual_skipped_slide_ids' in saved[0].plan.slides[0].notes
