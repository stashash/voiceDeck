import { describe, it, expect } from 'vitest';
import { buildSteps, stepIdFor } from './generation';
import type { DeckEvent, DeckPlan } from './api';

const plan: DeckPlan = {
  title: 'Т', purpose: '', audience: '', language: 'ru',
  slides: [1, 2, 3].map(n => ({ id: `s${n}`, kind: 'body', title: `Слайд ${n}`, key_message: '' })),
};

describe('stepIdFor', () => {
  it('относит plan к шагу plan', () => { expect(stepIdFor('plan')).toBe('plan'); });
  it('относит slide и slide-image к шагу layout', () => {
    expect(stepIdFor('slide')).toBe('layout');
    expect(stepIdFor('slide-image')).toBe('layout');
  });
  it('относит audit к шагу audit, а audit-contextual к meaning', () => {
    expect(stepIdFor('audit')).toBe('audit');
    expect(stepIdFor('audit-contextual')).toBe('meaning');
  });
  it('относит export-pptx, export-html и convert к шагу files', () => {
    expect(stepIdFor('export-pptx')).toBe('files');
    expect(stepIdFor('export-html')).toBe('files');
    expect(stepIdFor('convert')).toBe('files');
  });
  it('неизвестный шаг даёт null', () => { expect(stepIdFor('done')).toBeNull(); });
});

describe('buildSteps', () => {
  it('шаг план идёт как current, пока не появилась вёрстка', () => {
    const events: DeckEvent[] = [{ step: 'plan', slide_index: null, variant: 'a', at: 0 }];
    const steps = buildSteps(events, 'a', ['b', 'c'], plan, 0);
    expect(steps.find(s => s.id === 'plan')!.status).toBe('current');
    expect(steps.find(s => s.id === 'layout')!.status).toBe('pending');
  });
  it('план становится done, когда началась вёрстка, вёрстка знает готово X из N', () => {
    const events: DeckEvent[] = [
      { step: 'plan', slide_index: null, variant: 'a', at: 0 },
      { step: 'slide', slide_index: 0, variant: 'a', at: 1 },
      { step: 'slide', slide_index: 1, variant: 'a', at: 2 },
    ];
    const steps = buildSteps(events, 'a', ['b', 'c'], plan, 2);
    expect(steps.find(s => s.id === 'plan')!.status).toBe('done');
    const layout = steps.find(s => s.id === 'layout')!;
    expect(layout.status).toBe('current');
    expect(layout.doneCount).toBe(2);
    expect(layout.total).toBe(3);
  });
  it('игнорирует события других вариантов, кроме варианта null (общие для колоды)', () => {
    const events: DeckEvent[] = [
      { step: 'plan', slide_index: null, variant: null, at: 0 },
      { step: 'slide', slide_index: 0, variant: 'b', at: 1 },
    ];
    const steps = buildSteps(events, 'a', ['b', 'c'], plan, 0);
    expect(steps.find(s => s.id === 'plan')!.status).toBe('current');
    expect(steps.find(s => s.id === 'layout')!.status).toBe('pending');
  });
  it('шаг «Варианты 2 и 3» done, только когда done пришёл у всех остальных вариантов', () => {
    const events: DeckEvent[] = [
      { step: 'done', slide_index: null, variant: 'a', at: 10 },
      { step: 'done', slide_index: null, variant: 'b', at: 11 },
    ];
    const partial = buildSteps(events, 'a', ['b', 'c'], plan, 3);
    expect(partial.find(s => s.id === 'variants')!.status).toBe('current');
    const full = buildSteps(
      [...events, { step: 'done', slide_index: null, variant: 'c', at: 12 }],
      'a', ['b', 'c'], plan, 3,
    );
    expect(full.find(s => s.id === 'variants')!.status).toBe('done');
  });
  it('последний шаг варианта помечается done при событии done без начала следующего шага', () => {
    const events: DeckEvent[] = [
      { step: 'plan', slide_index: null, variant: 'a', at: 0 },
      { step: 'slide', slide_index: 0, variant: 'a', at: 1 },
      { step: 'audit', slide_index: null, variant: 'a', at: 2 },
      { step: 'export-pptx', slide_index: null, variant: 'a', at: 3 },
      { step: 'audit-contextual', slide_index: null, variant: 'a', at: 4 },
      { step: 'done', slide_index: null, variant: 'a', at: 5 },
    ];
    const steps = buildSteps(events, 'a', [], plan, 1);
    expect(steps.find(s => s.id === 'meaning')!.status).toBe('done');
  });
});
