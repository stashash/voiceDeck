import {request as fetch} from './request';
// Клиент сервиса designer. Пути и схеммы сверены с api/app.py и api/schemas.py, contracts.py.
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
export type PatternSlot = { id: string; role: string; box: Box; style?: {family?:string;size_pt?:number;bold?:boolean;color?:string} };
export type PatternUnit = { index: number; box: Box };
export type PatternGroup = { id?:string; linked_group_ids?:string[]; min_units: number; max_units: number; unit_slots: { role: string }[]; units: PatternUnit[] };
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
  revision?: string | null;
  /** Правка, по которой нарисованы картинки слайдов: пока не равна revision, экспорт ещё идёт. */
  images_revision?: string | null;
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
/** Экран «Агенты и модели»: адрес сервера модели, как его видит человек, модель по умолчанию, модели CLI. */
export type ModelSettings = { llm_url: string; llm_model: string; server: 'lmstudio' | 'ollama' | 'api'; cli_models: Record<string, string> };

function url(path: string): string {
  return `${BASE_URL}${path}`;
}

/** Ошибка запроса словами человека: сбой сети браузер отдаёт как «TypeError: Failed to fetch». */
export function errorText(e: unknown): string {
  if (e instanceof TypeError) return `Сервис дизайнера не отвечает (${BASE_URL}). Проверьте, что контейнеры запущены: docker compose ps.`;
  return e instanceof Error ? e.message : String(e);
}

async function asJson<T>(res: Response): Promise<T> {
  if (!res.ok) return uploadResponse<T>(res);
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
    throw Object.assign(new Error(typeof detail==='string'?detail:JSON.stringify(detail)),{status:res.status});
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

export function libraryAction(id:string,action:'delete'|'restore'|'copy'):Promise<{deck_id?:string}>{
 return fetch(url(`/library/${encodeURIComponent(id)}/${action}`),{method:'POST'}).then(r=>asJson<{deck_id?:string}>(r));
}
export function listTrash():Promise<DeckListItem[]>{return fetch(url('/library/trash')).then(r=>asJson<{items:DeckListItem[]}>(r)).then(r=>r.items);}

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

export function moveDeckElement(deckId:string,variant:string,n:number,elementId:string,dx:number,dy:number,align?:string):Promise<DeckVariantState>{
  return fetch(url(`/decks/${deckId}/${variant}/slides/${n}/position`),{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({element_id:elementId,dx,dy,align})}).then(r=>uploadResponse<DeckVariantState>(r));
}

export type DeckElementPayload={
 action:'add'|'delete'|'duplicate'|'style'|'background'|'z_order'|'table_cell'|'table_row_add'|'table_row_delete'|'table_column_add'|'table_column_delete';
 element_id?:string;element_type?:'text'|'title'|'shape'|'card'|'table';text?:string;
 scale?:number;size_pt?:number;color?:string;bold?:boolean;italic?:boolean;text_align?:'left'|'center'|'right';
 fill?:string;width?:number;height?:number;order?:'front'|'back';row?:number;column?:number;values?:string[];
 table?:{columns:string[];rows:string[][]};
};
export function deckElementAction(deckId:string,variant:string,n:number,payload:DeckElementPayload):Promise<DeckVariantState>{
  return fetch(url(`/decks/${deckId}/${variant}/slides/${n}/elements`),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}).then(r=>uploadResponse<DeckVariantState>(r));
}

export type SlidesAction = { action: 'add' | 'copy' | 'delete' | 'move'; index: number; to?: number; expected_revision?:string; target_slide_id?:string };
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

export function recoverEditor(deckId:string,variant:string):Promise<DeckVariantState>{
  return fetch(url(`/decks/${deckId}/${variant}/recover`),{method:'POST'}).then(r=>asJson<DeckVariantState>(r));
}

export function commitDeckDictation(deckId:string,variant:string,n:number,payload:{element_id:string;text:string;expected_revision:string;target_slide_id:string}):Promise<DeckVariantState>{
 return fetch(url(`/decks/${deckId}/${variant}/slides/${n}/voice-text`),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}).then(r=>uploadResponse<DeckVariantState>(r));
}

export type VoiceBatchOperation={element_id:string;box?:Element['box'];style?:TextStyle;fill?:string};
export function commitVoiceBatch(deckId:string,variant:string,n:number,payload:{expected_revision:string;target_slide_id:string;operations:VoiceBatchOperation[]}):Promise<DeckVariantState>{
 return fetch(url(`/decks/${deckId}/${variant}/slides/${n}/voice-batch`),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)},8000).then(r=>uploadResponse<DeckVariantState>(r));
}

export function rewriteDeckVoice(deckId:string,variant:string,n:number,payload:{request_id:string;element_id:string;instruction:string;constraints?:{preserve_numbers?:boolean;preserve_dates?:boolean}},signal:AbortSignal):Promise<{state?:DeckVariantState;notice:string;elapsed_ms?:number}>{
 return fetch(url(`/decks/${deckId}/${variant}/slides/${n}/voice-rewrite`),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal},35000).then(r=>uploadResponse(r));
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

export function getModelSettings(): Promise<ModelSettings> {
  return fetch(url('/settings/models')).then(r => asJson<ModelSettings>(r));
}

export function setModelSettings(change: Partial<Omit<ModelSettings, 'server'>>): Promise<ModelSettings> {
  return fetch(url('/settings/models'), {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(change),
  }).then(r => asJson<ModelSettings>(r));
}

export function setAgentAssignments(assignments: AgentAssignments): Promise<AgentAssignments> {
  return fetch(url('/settings/agents'), {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(assignments),
  }).then(r => asJson<AgentAssignments>(r));
}
