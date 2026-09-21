// Клиент сервиса designer. Пути и схемы сверены с api/app.py и api/schemas.py, contracts.py.
// import.meta.env типизирован через vite/client, которого в проекте нет: берём мягкой приведением типа.
const env = (import.meta as unknown as { env?: Record<string, string | undefined> }).env ?? {};
export const BASE_URL = env.VITE_DESIGNER_URL || 'http://localhost:8090';

export type Box = [number, number, number, number];

// ---------- дизайн-система ----------
export type ColorToken = { hex: string; role: string; share: number; source: string };
export type FontToken = { family: string; role: string; share: number; embedded_file?: string | null };
export type TypeStep = { size_pt: number; role: string; share: number };
export type Margins = { left: number; top: number; right: number; bottom: number };
export type Tokens = { colors: ColorToken[]; fonts: FontToken[]; type_scale: TypeStep[]; margins: Margins };
export type Asset = { id: string; path: string; kind: string; width_px: number; height_px: number; used_on: number[] };
export type Pattern = {
  id: string; kind: string; kind_confidence: number; theme: 'light' | 'dark';
  purpose: string; needs_images: boolean; background_asset?: string | null; preview?: string | null;
};
export type DesignSystem = {
  id: string; source_file: string; slide_size_emu: [number, number];
  tokens: Tokens; assets: Asset[]; patterns: Pattern[];
};

// ---------- план и сцена ----------
export type SlideIntent = { id: string; kind: string; title: string; key_message: string };
export type DeckPlan = { title: string; purpose: string; audience: string; language: string; slides: SlideIntent[] };
export type TextStyle = { size_pt?: number | null; bold?: boolean; italic?: boolean; color?: string | null; align?: 'left' | 'center' | 'right' | null };
export type Element = {
  id: string; type: 'text' | 'shape' | 'image' | 'icon' | 'chart' | 'table'; role: string;
  box: Box; text: string; style?: TextStyle | null; fill?: string | null; asset?: string | null;
};
export type Scene = {
  slide_id: string; pattern_id: string; variant: string; theme: 'light' | 'dark';
  background_asset?: string | null; background_color?: string | null; elements: Element[];
};
export type Finding = {
  id: string; slide_id: string; check_id: string; kind: 'deterministic' | 'contextual';
  severity: 'error' | 'warning'; message: string; box?: Box | null; fixable: boolean; fix_hint: string;
};

// ---------- состояние колоды ----------
export type DeckVariantState = {
  status: 'running' | 'done' | 'error';
  design_system_id: string;
  plan: DeckPlan | null;
  scenes: Scene[];
  findings: Finding[];
  error: string | null;
  slide_images?: string[];
};
export type DeckStateResponse = DeckVariantState & { variants: Record<string, DeckVariantState> };

export type SkillRef = { name: string; version: string; sha256: string };
export type RunManifest = {
  run_id: string; started_at: string; model: string;
  skills: SkillRef[]; timings_ms: Record<string, number>;
};

export type DeckEvent = { step: string; slide_index: number | null; variant: string | null; at: number };
export type FixReportItem = { finding_id: string; status: 'fixed' | 'skipped'; what: string };

function url(path: string): string {
  return `${BASE_URL}${path}`;
}

async function asJson<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`Сервис дизайнера ответил ${res.status}`);
  return res.json() as Promise<T>;
}

// Адреса картинок в slide_images могут прийти как путь без хоста.
export function absoluteUrl(pathOrUrl: string): string {
  return /^https?:\/\//.test(pathOrUrl) ? pathOrUrl : url(pathOrUrl);
}

export function assetUrl(dsId: string, assetPath: string): string {
  return url(`/design-systems/${dsId}/assets/${assetPath.replace(/^assets\//, '')}`);
}

export function fileUrl(deckId: string, variant: string, name: string): string {
  return url(`/decks/${deckId}/${variant}/files/${name}`);
}

export function listDesignSystems(): Promise<string[]> {
  return fetch(url('/design-systems')).then(r => asJson<{ ids: string[] }>(r)).then(r => r.ids);
}

export function uploadDesignSystem(file: File): Promise<DesignSystem> {
  const form = new FormData();
  form.append('file', file);
  return fetch(url('/design-systems'), { method: 'POST', body: form }).then(r => asJson<DesignSystem>(r));
}

export function getManifest(dsId: string): Promise<DesignSystem> {
  return fetch(url(`/design-systems/${dsId}`)).then(r => asJson<DesignSystem>(r));
}

export function createDeck(payload: {
  design_system_id: string; brief: string; purpose?: string; audience?: string;
  slide_count?: number | null; variants?: string[];
}): Promise<{ deck_id: string }> {
  return fetch(url('/decks'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }).then(r => asJson<{ deck_id: string }>(r));
}

export function watchDeckEvents(deckId: string, onEvent: (e: DeckEvent) => void): EventSource {
  const source = new EventSource(url(`/decks/${deckId}/events`));
  source.onmessage = message => {
    try {
      onEvent(JSON.parse(message.data));
    } catch {
      // Битое событие пропускаем, поток продолжает идти.
    }
  };
  return source;
}

export function getDeckState(deckId: string): Promise<DeckStateResponse> {
  return fetch(url(`/decks/${deckId}`)).then(r => asJson<DeckStateResponse>(r));
}

export function getRunManifest(deckId: string): Promise<RunManifest> {
  return fetch(url(`/decks/${deckId}/run`)).then(r => asJson<RunManifest>(r));
}

export function auditContextual(deckId: string, variant: string): Promise<{ findings: Finding[] }> {
  return fetch(url(`/decks/${deckId}/${variant}/audit-contextual`), { method: 'POST' })
    .then(r => asJson<{ findings: Finding[] }>(r));
}

export function fixFindings(deckId: string, variant: string, findingIds: string[]):
  Promise<{ report: FixReportItem[]; findings: Finding[] }> {
  return fetch(url(`/decks/${deckId}/${variant}/fix`), {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ finding_ids: findingIds }),
  }).then(r => asJson<{ report: FixReportItem[]; findings: Finding[] }>(r));
}
