import { analyzeDatasetBundle, BASE_URL, DatasetBundlePlanResponse, DatasetTablePlan, InsightsResponse, VisualizationCandidate } from './api';
import { request } from './request';

export type PersistedDataset = DatasetTablePlan & { dataset_id: string; source_sha256: string };
export type PersistedBundle = Omit<DatasetBundlePlanResponse, 'datasets'> & { id: string; datasets: PersistedDataset[] };
export type TableDisplay = 'compact' | 'full';
export type DatasetSelection = { dataset_id: string; candidate_kind: VisualizationCandidate['kind']; required_fields: string[]; table_display?: TableDisplay };

export function tableDisplayEstimate(rows: number, mode: TableDisplay = 'compact') {
  return rows > 20 && mode === 'compact' ? 1 : Math.ceil(rows / 7);
}

export async function analyzePersistedBundle(files: File[], goal: string): Promise<PersistedBundle> {
  const result = await analyzeDatasetBundle(files, goal) as PersistedBundle;
  if (!result.id || result.datasets.some(item => !item.dataset_id)) {
    throw new Error('Сервис не сохранил пакет данных. Обновите сервис дизайнера и повторите анализ.');
  }
  return result;
}

export function candidateKey(candidate: VisualizationCandidate) {
  return JSON.stringify([candidate.kind, candidate.required_fields]);
}

export function selectedCandidates(bundle: PersistedBundle, selected: Record<string, string>, included: Record<string, boolean>,
                                   tableDisplay: Record<string, TableDisplay> = {}): DatasetSelection[] {
  return bundle.datasets.flatMap(dataset => {
    if (included[dataset.dataset_id] === false) return [];
    const candidate = dataset.plan.candidates.find(item => candidateKey(item) === selected[dataset.dataset_id])
      ?? dataset.plan.selected_candidate;
    return candidate.renderable ? [{ dataset_id: dataset.dataset_id, candidate_kind: candidate.kind,
                                    required_fields: candidate.required_fields,
                                    ...(candidate.kind === 'table' && tableDisplay[dataset.dataset_id]
                                      ? { table_display: tableDisplay[dataset.dataset_id] } : {}) }] : [];
  });
}

export async function materializeDatasetBundle(bundleId: string, selections: DatasetSelection[]): Promise<InsightsResponse> {
  const form = new FormData();
  form.append('bundle_id', bundleId);
  form.append('selections', JSON.stringify(selections));
  const response = await request(`${BASE_URL}/insights/plan/materialize-bundle`, { method: 'POST', body: form }, 90_000);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === 'string' ? body.detail : `Сервис дизайнера ответил ${response.status}`);
  }
  return response.json();
}
