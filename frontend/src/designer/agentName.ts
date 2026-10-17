// Человекочитаемое имя агента для чипа выбора (холст Home.dc.html: «Qwen3.8 27B в LM Studio»).
// CLI-агент уже приходит с именем от сервиса («Claude Code»). Локальная модель приходит как id
// («qwen/qwen3.8-27b»): достаём имя семейства и размер, остальные служебные хвосты (a4b — активные
// параметры MoE) убираем, как в примере «google/gemma-4-26b-a4b» → «Gemma 4 26B».
import type { AgentInfo } from './api';

// Модель инференса VK приходит без адреса в run.json: её узнаём по имени из инструкции организаторов.
const VK_MODELS = new Set(['qwen38-27b-fp8']);

export function humanizeModelId(id: string): string {
  const slug = id.includes('/') ? id.split('/').pop()! : id;
  // fp8 и подобные хвосты это формат весов, а не имя модели; qwen38 у VK это Qwen3.8.
  const parts = slug.split('-').filter(p => p && !/^a\d+[bm]$/i.test(p) && !/^(fp|bf|int)\d+$/i.test(p));
  return parts.map((p, i) => {
    const qwen = /^qwen(\d)(\d)$/i.exec(p);
    if (qwen) return `Qwen${qwen[1]}.${qwen[2]}`;
    if (/^\d+(\.\d+)?[bm]$/i.test(p)) return p.slice(0, -1) + p.slice(-1).toUpperCase();
    if (/^\d/.test(p)) return p;
    return p.charAt(0).toUpperCase() + p.slice(1);
  }).join(' ');
}

/** Имя в списке выбора («Qwen3.8 27B», без «в LM Studio»); у CLI совпадает с именем сервиса. */
export function agentOptionName(a: Pick<AgentInfo, 'kind' | 'name' | 'model' | 'id'>): string {
  if (a.kind !== 'local') return a.name;
  return humanizeModelId(a.model ?? a.id.replace(/^local:/, ''));
}

/** Где работает модель, по её адресу: инференс VK, Ollama или LM Studio. */
export function modelServer(detail?: string, model?: string | null): 'VK' | 'Ollama' | 'LM Studio' {
  if ((detail ?? '').includes('platformpreview.ru') || (model && VK_MODELS.has(model))) return 'VK';
  if ((detail ?? '').includes(':11434')) return 'Ollama';
  return 'LM Studio';
}

const IN_SERVER = { VK: 'в инференсе VK', Ollama: 'в Ollama', 'LM Studio': 'в LM Studio' } as const;
const SERVER_NAME = { VK: 'Инференс VK', Ollama: 'Ollama', 'LM Studio': 'LM Studio' } as const;

/** Имя на закрытом чипе выбора агента («Qwen3.8 27B в LM Studio», «Qwen3.8 27B в инференсе VK»). */
export function agentDisplayName(a: Pick<AgentInfo, 'kind' | 'name' | 'model' | 'id'> & { detail?: string }): string {
  return a.kind === 'local' ? `${agentOptionName(a)} ${IN_SERVER[modelServer(a.detail, a.model)]}` : a.name;
}

/**
 * Подпись под именем в списке выбора («2.1.270, найден в PATH» / «LM Studio, загружена»).
 * У локальной модели `detail` от сервиса — внутренний адрес (host.docker.internal:1234/v1),
 * читателю он не нужен: подпись называет источник, как на холсте Home-agent.dc.html.
 */
export function agentOptionSub(a: Pick<AgentInfo, 'kind' | 'detail' | 'found'>): string {
  if (a.kind !== 'local') return a.detail;
  const server = modelServer(a.detail);
  return server === 'VK' ? SERVER_NAME.VK : `${SERVER_NAME[server]}${a.found ? ', загружена' : ''}`;
}

const CLI_NAMES: Record<string, string> = { claude: 'Claude Code', codex: 'Codex', 'cursor-agent': 'Cursor Agent', opencode: 'OpenCode' };

/** Имя по id агента или модели из run.json: «cli:cursor-agent» → «Cursor Agent», «qwen/qwen3.8-27b» → «Qwen3.8 27B в LM Studio». */
export function modelDisplayName(id: string): string {
  const raw = id.replace(/^local:/, '');
  if (raw.startsWith('cli:')) return CLI_NAMES[raw.slice(4)] ?? raw.slice(4);
  return `${humanizeModelId(raw)} ${IN_SERVER[modelServer(undefined, raw)]}`;
}
