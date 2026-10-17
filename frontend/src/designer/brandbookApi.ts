import { BASE_URL, DesignSystem } from './api';
import { request } from './request';

export type BrandbookState = {
  design_system: DesignSystem;
  file_name: string;
  sha256: string;
  priority: 'brand' | 'template';
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
  const form = new FormData();
  form.append('file', file);
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
