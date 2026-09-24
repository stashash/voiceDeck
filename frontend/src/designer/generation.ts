// Разбор событий SSE генерации в шаги ленты слева на экране «Генерация».
// Порядок и подписи шагов — docs/model.md раздел «Ход генерации» и холст Generation.dc.html.
import type { DeckEvent, DeckPlan } from './api';

export type StepId = 'plan' | 'layout' | 'audit' | 'files' | 'meaning' | 'variants';
export type StepStatus = 'pending' | 'current' | 'done' | 'error';

export interface StepView {
  id: StepId;
  status: StepStatus;
  /** Начало и конец шага в мс (at событий приходит в секундах): конец — первое событие следующего шага. */
  startAt: number | null;
  endAt: number | null;
  /** Для «Вёрстка»: готово X из N. */
  doneCount?: number;
  total?: number;
}

const STEP_ORDER: StepId[] = ['plan', 'layout', 'audit', 'files', 'meaning', 'variants'];

/** Сырой шаг события SSE → канонический шаг ленты. null — событие не относится к пяти шагам одного варианта. */
export function stepIdFor(rawStep: string): StepId | null {
  if (rawStep === 'plan') return 'plan';
  if (rawStep === 'slide' || rawStep === 'slide-image' || rawStep === 'slide-fallback') return 'layout';
  if (rawStep === 'audit') return 'audit';
  if (rawStep === 'export-pptx' || rawStep === 'export-html' || rawStep === 'export-pdf' || rawStep === 'convert' || rawStep === 'convert-failed') return 'files';
  if (rawStep === 'audit-contextual') return 'meaning';
  return null;
}

/**
 * Строит пять шагов текущего варианта плюс «Варианты 2 и 3» по журналу событий SSE этой колоды.
 * Шаг «done», когда начался следующий шаг того же варианта, пришёл его собственный done, или сам
 * вариант уже done по опросу `GET /decks/{id}` (statuses) — SSE не хранит историю для давно
 * законченной колоды, открытой заново, поэтому статус варианта из REST-опроса первичен.
 * Шаг «current», когда по нему есть события, но он ещё не done; иначе «pending».
 */
export function buildSteps(
  events: DeckEvent[],
  activeVariant: string,
  otherVariants: string[],
  plan: DeckPlan | null,
  slidesDone: number,
  variantStatus?: Record<string, string>,
): StepView[] {
  const forActive = events.filter(e => e.variant === activeVariant || e.variant === null);
  const byStep = new Map<StepId, DeckEvent[]>();
  for (const e of forActive) {
    const id = stepIdFor(e.step);
    if (!id) continue;
    if (!byStep.has(id)) byStep.set(id, []);
    byStep.get(id)!.push(e);
  }
  const variantDone = forActive.some(e => e.step === 'done') || variantStatus?.[activeVariant] === 'done';

  const sorted = [...events].sort((x, y) => x.at - y.at);
  // Конец шага: первое событие после его последнего, которое к этому шагу этого варианта не относится.
  const endOf = (id: StepId, lastAt: number): number | null => {
    const next = sorted.find(e => e.at > lastAt
      && !(stepIdFor(e.step) === id && (e.variant === activeVariant || e.variant === null)));
    return next ? next.at : null;
  };
  const mainSteps: StepId[] = ['plan', 'layout', 'audit', 'files', 'meaning'];
  const views: StepView[] = mainSteps.map((id, i) => {
    const evs = byStep.get(id) ?? [];
    const evsStarted = evs.length > 0;
    const laterStarted = mainSteps.slice(i + 1).some(later => byStep.has(later));
    const done = variantDone || (evsStarted && laterStarted);
    const status: StepStatus = done ? 'done' : evsStarted ? 'current' : 'pending';
    const total = id === 'layout' ? (plan?.slides.length ?? undefined) : undefined;
    // Готово «X из N»: once the step is done a stale scenes-length snapshot must not show 0 из N.
    const doneCount = id === 'layout' ? (done ? total : slidesDone) : undefined;
    return {
      id, status,
      startAt: evs.length ? evs[0].at * 1000 : null,
      endAt: done && evs.length ? ((endOf(id, evs[evs.length - 1].at) ?? evs[evs.length - 1].at) * 1000) : null,
      doneCount, total,
    };
  });

  const otherDoneOf = (v: string) => events.some(e => e.step === 'done' && e.variant === v) || variantStatus?.[v] === 'done';
  const othersDone = otherVariants.length > 0 && otherVariants.every(otherDoneOf);
  const othersStarted = otherVariants.some(v => events.some(e => e.variant === v) || variantStatus?.[v] !== undefined);
  views.push({
    id: 'variants',
    status: otherVariants.length === 0 ? 'pending' : othersDone ? 'done' : othersStarted ? 'current' : 'pending',
    startAt: null, endAt: null,
  });
  return views;
}

export const STEP_LABEL: Record<StepId, string> = {
  plan: 'План', layout: 'Вёрстка', audit: 'Проверка по правилам шаблона',
  files: 'Файлы pptx, pdf и html', meaning: 'Проверка смысла', variants: 'Варианты 2 и 3',
};
