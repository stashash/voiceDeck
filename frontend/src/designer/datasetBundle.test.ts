import { afterEach, describe, expect, it, vi } from 'vitest';
import { BASE_URL, VisualizationCandidate } from './api';
import { analyzePersistedBundle, candidateKey, materializeDatasetBundle, PersistedBundle, selectedCandidates } from './datasetBundle';

afterEach(() => vi.unstubAllGlobals());

const line = { kind: 'line', required_fields: ['month', 'value'], renderable: true } as VisualizationCandidate;
const table = { kind: 'table', required_fields: ['name', 'value'], renderable: true } as VisualizationCandidate;
const scatter = { kind: 'scatter', required_fields: ['x', 'y'], renderable: false } as VisualizationCandidate;
const saved = { id: 'bundle-1', datasets: [
  { dataset_id: 'first', plan: { candidates: [line, table], selected_candidate: line } },
  { dataset_id: 'second', plan: { candidates: [table, scatter], selected_candidate: table } },
] } as PersistedBundle;

describe('persisted dataset bundle', () => {
  it('keeps choices across table navigation and excludes only unchecked tables', () => {
    const chosen = { first: candidateKey(table), second: candidateKey(scatter) };
    expect(selectedCandidates(saved, chosen, { second: false })).toEqual([
      { dataset_id: 'first', candidate_kind: 'table', required_fields: ['name', 'value'] },
    ]);
    expect(selectedCandidates(saved, {}, {})).toHaveLength(2);
    expect(selectedCandidates(saved, chosen, {})).toHaveLength(1);
  });

  it('passes stable ids and selected field names without uploading files or trusting browser values', async () => {
    const response = { id: 'insights-1', suggestions: [{ id: 's1' }, { id: 's2' }] };
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => response });
    vi.stubGlobal('fetch', fetch);
    const selections = selectedCandidates(saved, {}, {});
    expect(await materializeDatasetBundle(saved.id, selections)).toEqual(response);
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe(`${BASE_URL}/insights/plan/materialize-bundle`);
    expect(init.method).toBe('POST');
    expect(init.body.get('bundle_id')).toBe('bundle-1');
    expect(JSON.parse(init.body.get('selections'))).toEqual(selections);
    expect(init.body.has('file')).toBe(false);
  });

  it('surfaces source checksum rejection', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 422,
      json: async () => ({ detail: 'Контрольная сумма исходного файла не совпадает.' }) }));
    await expect(materializeDatasetBundle(saved.id, selectedCandidates(saved, {}, {}))).rejects.toThrow('Контрольная сумма');
  });

  it('rejects outdated nonpersistent analysis responses', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ datasets: [] }) }));
    await expect(analyzePersistedBundle([], '')).rejects.toThrow('не сохранил пакет');
  });
});
