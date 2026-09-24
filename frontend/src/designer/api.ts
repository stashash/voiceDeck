// Клиент сервиса designer. Пути и схемы сверены с api/app.py и api/schemas.py, contracts.py.
// import.meta.env типизирован через vite/client, которого в проекте нет: берём мягкой приведением типа.
const env = (import.meta as unknown as { env?: Record<string, string | undefined> }).env ?? {};
// Пустая строка — осознанный выбор (адрес того же источника, что и приложение; см. vite.config.ts proxy
// для /design-systems, /decks, /agents, /settings/agents), поэтому проверяем undefined, а не пустоту.
export const BASE_URL = env.VITE_DESIGNER_URL !== undefined ? env.VITE_DESIGNER_URL : 'http://localhost:8090';

export type Box = [number, number, number, number];

// ---------- дизайн-система ----------
export type ColorToken = { hex: string; role: string; share: number; source: string };
export type EmbeddedState = 'extracted' | 'embedded_not_extracted' | 'missing';
export type FontToken = { family: string; role: string; share: number; embedded_file?: string | null; embedded_state?: EmbeddedState };
export type TypeStep = { size_pt: number; role: string; share: number };
export type Margins = { left: number; top: number; right: number; bottom: number };
export type Tokens = { colors: ColorToken[]; fonts: FontToken[]; type_scale: TypeStep[]; margins: Margins };
export type Asset = { id: string; path: string; kind: string; width_px: number; height_px: number; used_on: number[] };
export type PatternSlot = { id: string; role: string; box: Box };
export type PatternUnit = { index: number; box: Box };
export type PatternGroup = { min_units: number; max_units: number; unit_slots: { role: string }[]; units: PatternUnit[] };
export type Pattern = {
  id: string; source_slide?: number; kind: string; kind_confidence: number; theme: 'light' | 'dark';
  purpose: string; needs_images: boolean; background_asset?: string | null; preview?: string | null;
  slots?: PatternSlot[]; groups?: PatternGroup[];
};
export type DescribeStatus = { status: 'pending' | 'running' | 'done' | 'failed'; done: number; total: number; error?: string | null };
export type DesignSystem = {
  id: string; name?: string; created_at?: string; source_file: string; slide_size_emu: [number, number];
  tokens: Tokens; assets: Asset[]; patterns: Pattern[];
  pattern_overrides?: Record<string, boolean>; removal_confirmed?: boolean; describe?: DescribeStatus;
};
export type DesignSystemListItem = {
  id: string; name: string; source_file: string; patterns: number; preview: string | null;
  created_at: string; describe_status: DescribeStatus['status'];
};

// ---------- план и сцена ----------
export type SlideIntent = { id: string; kind: string; title: string; key_message: string; notes?: string };
export type DeckPlan = { title: string; purpose: string; audience: string; language: string; slides: SlideIntent[] };
export type TextStyle = { size_pt?: number | null; bold?: boolean; italic?: boolean; color?: string | null; align?: 'left' | 'center' | 'right' | null };
export type Element = {
  id: string; type: 'text' | 'shape' | 'image' | 'icon' | 'chart' | 'table'; role: string;
  box: Box; text: string; style?: TextStyle | null; fill?: string | null; asset?: string | null;
};
export type Scene = {
  slide_id: string; pattern_id: string; variant: string; theme: 'light' | 'dark';
  background_asset?: string | null; background_color?: string | null; elements: Element[]; notes?: string;
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
export type DeckStateResponse = DeckVariantState & { brief?: string; variants: Record<string, DeckVariantState> };

export type SkillRef = { name: string; version: string; sha256: string };
export type RunManifest = {
  run_id: string; started_at: string; model: string;
  skills: SkillRef[]; timings_ms: Record<string, number>;
};

export type DeckEvent = { step: string; slide_index: number | null; variant: string | null; at: number };
export type FixReportItem = { finding_id: string; status: 'fixed' | 'skipped'; what: string };
export type DeckListItem = {
  id: string; title: string; design_system_id: string; slides: number;
  status: string; started_at: string; preview: string | null;
};

// ---------- агенты ----------
export type AgentInfo = { id: string; kind: 'cli' | 'local'; name: string; detail: string; found: boolean; model: string | null };
export type AgentCheckResult = { ok: boolean; images: boolean | null; seconds: number; message: string };
export type AgentAssignments = { deck: string; live: string; describe: string };

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

export function listDesignSystemItems(): Promise<DesignSystemListItem[]> {
  return fetch(url('/design-systems')).then(r => asJson<{ items: DesignSystemListItem[] }>(r)).then(r => r.items ?? []);
}

// Не pptx или битый файл: сервис отвечает 400 с {detail}, показываем его дословно.
async function uploadResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `Сервис дизайнера ответил ${res.status}`;
    try { const body = await res.json(); if (body?.detail) detail = body.detail; } catch { /* тело не JSON */ }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export function uploadDesignSystem(file: File): Promise<DesignSystem> {
  const form = new FormData();
  form.append('file', file);
  return fetch(url('/design-systems'), { method: 'POST', body: form }).then(r => uploadResponse<DesignSystem>(r));
}

export function getManifest(dsId: string): Promise<DesignSystem> {
  return fetch(url(`/design-systems/${dsId}`)).then(r => asJson<DesignSystem>(r));
}

export function patchDesignSystem(dsId: string, payload: {
  name?: string; pattern_overrides?: Record<string, boolean>; removal_confirmed?: boolean;
}): Promise<DesignSystem> {
  return fetch(url(`/design-systems/${dsId}`), {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }).then(r => asJson<DesignSystem>(r));
}

export function deleteDesignSystem(dsId: string): Promise<void> {
  return fetch(url(`/design-systems/${dsId}`), { method: 'DELETE' }).then(r => {
    if (!r.ok) throw new Error(`Сервис дизайнера ответил ${r.status}`);
  });
}

export function describeDesignSystem(dsId: string): Promise<DesignSystem> {
  return fetch(url(`/design-systems/${dsId}/describe`), { method: 'POST' }).then(r => asJson<DesignSystem>(r));
}

export function patternPreviewUrl(dsId: string, patternId: string): string {
  return url(`/design-systems/${dsId}/previews/${patternId}.png`);
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

export function rewriteFinding(deckId: string, variant: string, findingId: string): Promise<DeckVariantState> {
  return fetch(url(`/decks/${deckId}/${variant}/rewrite`), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ finding_id: findingId }),
  }).then(r => asJson<DeckVariantState>(r));
}

export function listDecks(): Promise<DeckListItem[]> {
  return fetch(url('/decks')).then(r => asJson<{ items: DeckListItem[] }>(r)).then(r => r.items ?? []);
}

// ---------- правка варианта ----------
export function patchSlideText(deckId: string, variant: string, n: number, elementId: string, text: string): Promise<DeckVariantState> {
  return fetch(url(`/decks/${deckId}/${variant}/slides/${n}/text`), {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ element_id: elementId, text }),
  }).then(r => asJson<DeckVariantState>(r));
}

export function setSlidePattern(deckId: string, variant: string, n: number, patternId: string): Promise<DeckVariantState> {
  return fetch(url(`/decks/${deckId}/${variant}/slides/${n}/pattern`), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pattern_id: patternId }),
  }).then(r => asJson<DeckVariantState>(r));
}

export type SlidePatternOption = { pattern_id: string; kind: string; preview: string | null; current: boolean };
export function getSlidePatterns(deckId: string, variant: string, n: number): Promise<SlidePatternOption[]> {
  return fetch(url(`/decks/${deckId}/${variant}/slides/${n}/patterns`))
    .then(r => asJson<{ items: SlidePatternOption[] }>(r)).then(r => r.items ?? []);
}

export function askSlide(deckId: string, variant: string, n: number, instruction: string): Promise<DeckVariantState> {
  return fetch(url(`/decks/${deckId}/${variant}/slides/${n}/ask`), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ instruction }),
  }).then(r => asJson<DeckVariantState>(r));
}

export type SlidesAction = { action: 'add' | 'copy' | 'delete' | 'move'; index: number; to?: number };
export function slidesAction(deckId: string, variant: string, action: SlidesAction): Promise<DeckVariantState> {
  return fetch(url(`/decks/${deckId}/${variant}/slides`), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(action),
  }).then(r => asJson<DeckVariantState>(r));
}

export function patchNotes(deckId: string, variant: string, n: number, notes: string): Promise<DeckVariantState> {
  return fetch(url(`/decks/${deckId}/${variant}/notes/${n}`), {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ notes }),
  }).then(r => asJson<DeckVariantState>(r));
}

export function cancelDeck(deckId: string): Promise<{ status: string }> {
  return fetch(url(`/decks/${deckId}/cancel`), { method: 'POST' }).then(r => asJson<{ status: string }>(r));
}

export function renameDeck(deckId: string, title: string): Promise<{ title: string }> {
  return fetch(url(`/decks/${deckId}/title`), {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title }),
  }).then(r => asJson<{ title: string }>(r));
}

export function revertVariant(deckId: string, variant: string): Promise<DeckVariantState> {
  return fetch(url(`/decks/${deckId}/${variant}/revert`), { method: 'POST' }).then(r => asJson<DeckVariantState>(r));
}

// ---------- агенты ----------
export function listAgents(): Promise<AgentInfo[]> {
  return fetch(url('/agents')).then(r => asJson<{ items: AgentInfo[] }>(r)).then(r => r.items ?? []);
}

export function checkAgent(agentId: string, model?: string): Promise<AgentCheckResult> {
  return fetch(url(`/agents/${encodeURIComponent(agentId)}/check`), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(model ? { model } : {}),
  }).then(r => asJson<AgentCheckResult>(r));
}

export function getAgentAssignments(): Promise<AgentAssignments> {
  return fetch(url('/settings/agents')).then(r => asJson<AgentAssignments>(r));
}

export function setAgentAssignments(assignments: AgentAssignments): Promise<AgentAssignments> {
  return fetch(url('/settings/agents'), {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(assignments),
  }).then(r => asJson<AgentAssignments>(r));
}
