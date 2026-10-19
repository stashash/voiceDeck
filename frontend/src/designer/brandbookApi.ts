import { BASE_URL, DesignSystem } from './api';
import { request } from './request';
import { convertFigmaBrandbook } from './figmaBrandbook';

export type BrandbookState = {
  design_system: DesignSystem;
  file_name: string;
  sha256: string;
  priority: 'brand' | 'template';
  source_format?: 'json' | 'figma_json' | 'pdf' | 'zip';
  warnings?: string[];
  assets?: Array<{ name: string; size: number; sha256: string }>;
  source?: { format?: string; file_name?: string; sha256?: string; warnings?: string[]; [key: string]: unknown } | null;
  rules?: { logo?: string | null; logo_box?: [number, number, number, number]; clear_space?: number; grid_columns?: number; grid_gutter?: number } | null;
  brand_fields: string[];
  applied_fields: string[];
};

async function jsonResponse<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof body?.detail === 'string' ? body.detail : `Сервис дизайнера ответил ${response.status}`);
  return body as T;
}

export async function getBrandbook(dsId: string): Promise<BrandbookState> {
  return jsonResponse<BrandbookState>(await request(`${BASE_URL}/design-systems/${encodeURIComponent(dsId)}/brandbook`));
}

export async function uploadBrandbook(dsId: string, file: File, priority: 'brand' | 'template'): Promise<BrandbookState> {
  const upload = /\.fig$/i.test(file.name) ? await convertFigmaBrandbook(file) : file;
  const form = new FormData();
  form.append('file', upload);
  form.append('priority', priority);
  return jsonResponse<BrandbookState>(await request(`${BASE_URL}/design-systems/${encodeURIComponent(dsId)}/brandbook`, { method: 'POST', body: form }));
}

export async function setBrandbookPriority(dsId: string, priority: 'brand' | 'template'): Promise<BrandbookState> {
  const form = new FormData();
  form.append('priority', priority);
  return jsonResponse<BrandbookState>(await request(`${BASE_URL}/design-systems/${encodeURIComponent(dsId)}/brandbook`, { method: 'POST', body: form }));
}

export async function removeBrandbook(dsId: string): Promise<void> {
  const response = await request(`${BASE_URL}/design-systems/${encodeURIComponent(dsId)}/brandbook`, { method: 'DELETE' });
  await jsonResponse<{ removed: boolean }>(response);
}
