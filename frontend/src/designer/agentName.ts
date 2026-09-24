// Человекочитаемое имя агента для чипа выбора (холст Home.dc.html: «Qwen3.8 27B в LM Studio»).
// CLI-агент уже приходит с именем от сервиса («Claude Code»). Локальная модель приходит как id
// («qwen/qwen3.8-27b»): достаём имя семейства и размер, остальные служебные хвосты (a4b — активные
// параметры MoE) убираем, как в примере «google/gemma-4-26b-a4b» → «Gemma 4 26B».
import type { AgentInfo } from './api';

export function humanizeModelId(id: string): string {
  const slug = id.includes('/') ? id.split('/').pop()! : id;
  const parts = slug.split('-').filter(p => p && !/^a\d+[bm]$/i.test(p));
  return parts.map((p, i) => {
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

/** Имя на закрытом чипе выбора агента («Qwen3.8 27B в LM Studio»). */
export function agentDisplayName(a: Pick<AgentInfo, 'kind' | 'name' | 'model' | 'id'>): string {
  return a.kind === 'local' ? `${agentOptionName(a)} в LM Studio` : a.name;
}

/**
 * Подпись под именем в списке выбора («2.1.270, найден в PATH» / «LM Studio, загружена»).
 * У локальной модели `detail` от сервиса — внутренний адрес (host.docker.internal:1234/v1),
 * читателю он не нужен: подпись называет источник, как на холсте Home-agent.dc.html.
 */
export function agentOptionSub(a: Pick<AgentInfo, 'kind' | 'detail' | 'found'>): string {
  return a.kind === 'local' ? `LM Studio${a.found ? ', загружена' : ''}` : a.detail;
}

const CLI_NAMES: Record<string, string> = { claude: 'Claude Code', codex: 'Codex', 'cursor-agent': 'Cursor Agent', opencode: 'OpenCode' };

/** Имя по id агента или модели из run.json: «cli:cursor-agent» → «Cursor Agent», «qwen/qwen3.8-27b» → «Qwen3.8 27B в LM Studio». */
export function modelDisplayName(id: string): string {
  const raw = id.replace(/^local:/, '');
  if (raw.startsWith('cli:')) return CLI_NAMES[raw.slice(4)] ?? raw.slice(4);
  return `${humanizeModelId(raw)} в LM Studio`;
}
