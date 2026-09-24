// Разбор событий SSE генерации в шаги ленты слева на экране «Генерация».
// Порядок и подписи шагов — docs/model.md раздел «Ход генерации» и холст Generation.dc.html.
import type { DeckEvent, DeckPlan } from './api';

export type StepId = 'plan' | 'layout' | 'audit' | 'files' | 'meaning' | 'variants';
export type StepStatus = 'pending' | 'current' | 'done' | 'error';

export interface StepView {
  id: StepId;
  status: StepStatus;
  /** Мгновение первого и последнего события шага, мс с начала прогона (для «33 с»). */
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
 * Шаг «done», когда начался следующий шаг того же варианта или пришёл его собственный done;
 * шаг «current», когда по нему есть события, но он ещё не done; иначе «pending».
 */
export function buildSteps(
  events: DeckEvent[],
  activeVariant: string,
  otherVariants: string[],
  plan: DeckPlan | null,
  slidesDone: number,
): StepView[] {
  const forActive = events.filter(e => e.variant === activeVariant || e.variant === null);
  const byStep = new Map<StepId, DeckEvent[]>();
  for (const e of forActive) {
    const id = stepIdFor(e.step);
    if (!id) continue;
    if (!byStep.has(id)) byStep.set(id, []);
    byStep.get(id)!.push(e);
  }
  const variantDone = forActive.some(e => e.step === 'done');

  const mainSteps: StepId[] = ['plan', 'layout', 'audit', 'files', 'meaning'];
  const views: StepView[] = mainSteps.map((id, i) => {
    const evs = byStep.get(id) ?? [];
    const started = evs.length > 0;
    const laterStarted = mainSteps.slice(i + 1).some(later => byStep.has(later));
    const done = started && (laterStarted || variantDone);
    const status: StepStatus = done ? 'done' : started ? 'current' : 'pending';
    return {
      id, status,
      startAt: evs.length ? evs[0].at : null,
      endAt: done && evs.length ? evs[evs.length - 1].at : null,
      doneCount: id === 'layout' ? slidesDone : undefined,
      total: id === 'layout' ? (plan?.slides.length ?? undefined) : undefined,
    };
  });

  const othersDone = otherVariants.length > 0 && otherVariants.every(v => events.some(e => e.step === 'done' && e.variant === v));
  const othersStarted = otherVariants.some(v => events.some(e => e.variant === v));
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
