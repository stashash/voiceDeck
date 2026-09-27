import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {afterAll, beforeAll, describe, expect, it, vi} from 'vitest';
import {BASE_URL, getDeckState, libraryAction, listDecks} from '../designer/api';
import type {DeckVariantState, Element} from '../designer/api';
import {parseDeckVoice} from './deckVoice';
import {deckSelectable, executeDeckVoice} from './deckVoiceExecutor';
import type {DeckVoiceContext} from './deckVoiceExecutor';

const enabled = process.env.VOICE_FACTORY_LIVE === '1';
const audioManifest = process.env.VOICE_FACTORY_AUDIO_MANIFEST;
const priorFixture = process.env.VOICE_FACTORY_PRIOR_FIXTURE;
const output = fileURLToPath(new URL('../../../scripts/voice-factory-output/', import.meta.url));
const audioModule = fileURLToPath(new URL('../../../scripts/voice-factory-audio.mjs', import.meta.url));
const realFetch = globalThis.fetch;
const evidence: Record<string, any>[] = [];
const writes: string[] = [];
const timings: {parserMs: number; executorMs: number; persistedReadMs: number; mutated: boolean}[] = [];
let context: DeckVoiceContext;
let state: DeckVariantState;
let original: DeckVariantState;
let originalId: string;
let manifest: {mode: string; engine: string; cases: {id: string; text: string; expectedKind: string; wav: string; sha256: string}[]};
let activeRecord: Record<string, any> | undefined;
const semantic = (s: DeckVariantState) => ({plan: s.plan, scenes: s.scenes});
type PersistedElement = Element & {table?: {columns: string[]; rows: string[][]}};
const selected = (s = state): PersistedElement => {
  const result = s.scenes[context.index].elements.find(e => e.id === context.selectedId);
  expect(result, 'A real persisted element must be selected').toBeDefined();
  return result!;
};
const p95 = (values: number[]) => values.length ? [...values].sort((a, b) => a - b)[Math.ceil(values.length * .95) - 1] : null;

async function perform(phrase: string, dictated = false) {
  const before = structuredClone(semantic(state));
  const start = performance.now();
  const action = dictated ? {kind: 'text' as const, text: phrase} : parseDeckVoice(phrase);
  const parsed = performance.now();
  expect(['ask', 'repeat'], `Unexpected model/UI-only command: ${phrase}`).not.toContain(action.kind);
  const result = await executeDeckVoice(action, context);
  const executed = performance.now();
  state = (await getDeckState(context.deckId)).variants.a;
  const read = performance.now();
  if (result.state) expect(semantic(state), 'Fresh HTTP read must equal the mutation response').toEqual(semantic(result.state));
  else expect(semantic(state), 'Non-mutating commands must leave persisted state intact').toEqual(before);
  context.scenes = state.scenes;
  if (result.index !== undefined) context.index = result.index;
  if (result.selectedId !== undefined) context.selectedId = result.selectedId;
  const timing = {parserMs: parsed - start, executorMs: executed - parsed, persistedReadMs: read - executed, mutated: !!result.state};
  timings.push(timing);
  activeRecord?.steps.push({phrase, source: dictated ? 'literal-dictation-after-production-textStart' : 'production-parser', action, result, timing, before, after: structuredClone(semantic(state))});
  return {action, result};
}

async function resetSelection(index = 0) {
  state = (await getDeckState(context.deckId)).variants.a;
  context.scenes = state.scenes;
  context.index = index;
  context.selectedId = deckSelectable(state.scenes[index]).find(e => e.type === 'text')!.id;
}

async function recordCase(name: string, fn: () => Promise<void>) {
  const record: Record<string, any> = {name, result: 'RUNNING', steps: []};
  evidence.push(record); activeRecord = record;
  try { await fn(); record.result = 'PASS'; }
  catch (error) {
    record.result = 'FAIL'; record.error = String(error);
    record.replay = (error as {replayEvidence?: unknown}).replayEvidence ?? record.replay;
    throw error;
  } finally { activeRecord = undefined; }
}

async function assertLiveText(text: string) {
  const response = await realFetch(`${BASE_URL}/decks/${context.deckId}/a/slides/${context.index + 1}/live`, {signal: AbortSignal.timeout(15000)});
  expect(response.ok).toBe(true);
  const html = await response.text();
  const escaped = text.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
  expect(html, 'Saved literal value must reach production live HTML').toContain(escaped);
  activeRecord!.preview = {bytes: Buffer.byteLength(html), sha256: createHash('sha256').update(html).digest('hex'), assertedText: text};
}

describe.skipIf(!enabled)('factory: production generated-deck operations against isolated persistence', () => {
  beforeAll(async () => {
    const {isolatedUrl} = await import(audioModule);
    isolatedUrl(BASE_URL, 8091);
    vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
      const value = input instanceof Request ? input.url : String(input);
      const url = new URL(value);
      if (url.port === '8089') isolatedUrl(url.origin, 8089);
      else isolatedUrl(url.origin, 8091);
      expect(url.pathname, 'Deterministic acceptance must never invoke a language model').not.toMatch(/\/(ask|intent|rewrite)(\/|$)/);
      if (init?.method && !['GET', 'HEAD'].includes(init.method)) writes.push(`${init.method} ${url.pathname}`);
      return realFetch(input, init);
    });
    const decks = await listDecks();
    originalId = process.env.VOICE_FACTORY_SEED_DECK ?? decks.find(d => d.id === 'shablon-prezentacii-vk-education')?.id ?? decks.find(d => d.status === 'done' && d.slides >= 2)?.id ?? '';
    expect(originalId, 'An isolated demo deck with at least two slides is required').not.toBe('');
    original = (await getDeckState(originalId)).variants.a;
    const copy = await libraryAction(originalId, 'copy');
    expect(copy.deck_id).toBeTruthy(); expect(copy.deck_id).not.toBe(originalId);
    state = (await getDeckState(copy.deck_id!)).variants.a;
    context = {deckId: copy.deck_id!, variant: 'a', scenes: state.scenes, index: 0, selectedId: null};
    await resetSelection();
    if (audioManifest) manifest = JSON.parse(await fs.readFile(audioManifest, 'utf8'));
  }, 30000);

  afterAll(async () => {
    let sourceUnchanged = false;
    try {
      if (originalId) {
        const unchanged = (await getDeckState(originalId)).variants.a;
        expect(semantic(unchanged), 'Source demo deck must remain unchanged').toEqual(semantic(original));
        sourceUnchanged = true;
      }
    } finally {
      vi.unstubAllGlobals();
      const mutationTimings = timings.filter(t => t.mutated);
      const deterministicP95 = p95(mutationTimings.map(t => t.parserMs + t.executorMs));
      const report = {
        result: context && sourceUnchanged && evidence.length && evidence.every(e => e.result === 'PASS') ? 'PASS' : 'FAIL',
        completedAt: new Date().toISOString(), designerUrl: BASE_URL,
        originalDeckId: originalId, acceptanceDeckId: context?.deckId, sourceUnchanged,
        scope: audioManifest ? 'offline-synthetic-tts-to-local-asr-to-production-executor-to-persisted-generated-deck' : 'text-to-production-executor-to-persisted-generated-deck',
        physicalMicrophone: 'NOT_TESTED', browserMicrophoneCapture: 'NOT_TESTED',
        generationRegression: 'Not run by verifier; owned by main',
        audioManifest: audioManifest ?? null, ttsEngine: manifest?.engine,
        latency: {samples: mutationTimings.length, parserP95Ms: p95(mutationTimings.map(t => t.parserMs)),
          deterministicP95Ms: deterministicP95,
          savedStateRoundTripP95Ms: p95(mutationTimings.map(t => t.parserMs + t.executorMs + t.persistedReadMs)),
          targetMs: 250, targetMet: deterministicP95 !== null && deterministicP95 < 250,
          note: 'Client wall time; executor includes production HTTP save, separate fresh GET; ASR timings are in replay evidence. No server-only or microphone latency claim.'},
        writes, cases: evidence,
      };
      await fs.mkdir(output, {recursive: true});
      const label = process.env.VOICE_FACTORY_RUN_LABEL ?? (audioManifest ? 'acceptance-audio' : 'acceptance-text');
      expect(label).toMatch(/^[a-z0-9-]+$/);
      const reportPath = path.join(output, `${label}.json`);
      await fs.writeFile(reportPath, JSON.stringify(report, null, 2), 'utf8');
      console.log(JSON.stringify({reportPath, result: report.result, acceptanceDeckId: context?.deckId, latency: report.latency}));
    }
  }, 30000);

  it('persists literal command-like replacement and serves it in live HTML', async () => recordCase('literal-and-preview', async () => {
    await resetSelection();
    const untouched = structuredClone(state.scenes.slice(1));
    const text = 'API v2: Удали слайд. Отмени! Рост 20%.';
    await perform(`Замени текст на ${text}`);
    expect(selected().text).toBe(text);
    expect(state.scenes.slice(1)).toEqual(untouched);
    await assertLiveText(text);
  }));

  it('rejects invalid explicit targets without writes or fallback to the selected element', async () => recordCase('invalid-targets', async () => {
    await resetSelection();
    const before = structuredClone(semantic(state)), count = writes.length;
    for (const phrase of ['На слайде 999 напиши УПС.', 'На слайде 0 напиши УПС.', 'Выбери элемент 999, замени текст на УПС.', 'Выбери элемент 0, замени текст на УПС.', 'Добавь изображение', 'Размер шрифта 999']) {
      const {result} = await perform(phrase);
      expect(result.state).toBeUndefined();
      expect(semantic(state)).toEqual(before);
    }
    expect(writes.length).toBe(count);
  }));

  it('persists font, style, dimensions and position on the selected element only', async () => recordCase('style-and-geometry', async () => {
    await resetSelection();
    const untouched = structuredClone(state.scenes[0].elements.filter(e => e.id !== context.selectedId));
    await perform('Размер шрифта двадцать четыре'); expect(selected().style?.size_pt).toBe(24);
    await perform('Сделай текст красным'); expect(selected().style?.color).toBe('DC2626');
    await perform('Сделай текст жирным'); expect(selected().style?.bold).toBe(true);
    await perform('Сделай текст курсивом'); expect(selected().style?.italic).toBe(true);
    await perform('Выровняй текст по правому краю'); expect(selected().style?.align).toBe('right');
    await perform('Ширина 400'); expect(selected().box[2]).toBeCloseTo(400 / 1280, 6);
    await perform('Высота 144'); expect(selected().box[3]).toBeCloseTo(144 / 720, 6);
    const x = selected().box[0]; await perform('Вправо на 20'); expect(selected().box[0]).toBeCloseTo(x + 20 / 1280, 6);
    expect(state.scenes[0].elements.filter(e => e.id !== context.selectedId)).toEqual(untouched);
  }));

  it('appends exact text and undoes the persisted mutation', async () => recordCase('append-and-undo', async () => {
    await resetSelection();
    const before = structuredClone(semantic(state)), text = selected().text;
    await perform('Добавь в конец СТОП! API v2.');
    expect(selected().text).toBe(`${text.trimEnd()} СТОП! API v2.`);
    await perform('Отмени'); expect(semantic(state)).toEqual(before);
  }));

  it('inserts, duplicates, deletes and restores a real element', async () => recordCase('element-lifecycle', async () => {
    await resetSelection(); const count = state.scenes[0].elements.length;
    await perform('Добавь текст Проверка API v2.');
    expect(selected().text).toBe('Проверка API v2.'); expect(state.scenes[0].elements.length).toBe(count + 1);
    const firstId = context.selectedId;
    await perform('Скопируй элемент'); expect(selected().text).toBe('Проверка API v2.'); expect(context.selectedId).not.toBe(firstId);
    const beforeDelete = structuredClone(semantic(state));
    await perform('Удали элемент'); expect(state.scenes[0].elements.length).toBe(count + 1);
    await perform('Отмени'); expect(semantic(state)).toEqual(beforeDelete);
  }));

  it('persists notes, background and table header/body cell values', async () => recordCase('notes-background-table', async () => {
    await resetSelection();
    await perform('Заметки: Доклад API v2. Не удалять!'); expect(state.plan?.slides[0].notes).toBe('Доклад API v2. Не удалять!');
    await perform('Фон слайда белый'); expect(state.scenes[0].background_color).toBe('FFFFFF');
    await perform('Добавь таблицу 3 на 2'); expect(selected().type).toBe('table');
    await perform('Ячейка 1, 2: ВЫРУЧКА'); expect(selected().table?.columns[1]).toBe('ВЫРУЧКА');
    await perform('Ячейка 3, 1: Рост 20%.'); expect(selected().table?.rows[1][0]).toBe('Рост 20%.');
  }));

  it.skipIf(!audioManifest).each(['select', 'size', 'color', 'move', 'replace', 'append', 'undo', 'next', 'previous'])
    ('real PCM recognition and persisted outcome: %s', async id => recordCase(`audio-${id}`, async () => {
      const fixture = manifest.cases.find(c => c.id === id);
      expect(fixture, 'The fixed acceptance matrix must include every case').toBeDefined();
      expect(manifest.mode).toBe('offline-synthetic-tts');
      expect(createHash('sha256').update(await fs.readFile(fixture!.wav)).digest('hex')).toBe(fixture!.sha256);
      await resetSelection(id === 'previous' ? 1 : 0);
      if (id === 'select') context.selectedId = null;
      if (id === 'size') await perform('Размер шрифта тридцать');
      if (id === 'color') await perform('Сделай текст синим');
      if (id === 'undo') await perform('Добавь в конец Подготовка проверки отмены.');
      const before = structuredClone(semantic(state)), beforeElement = id === 'select' ? null : structuredClone(selected());
      const {replayAudio} = await import(audioModule);
      const replay = await replayAudio(fixture!.wav, {base: process.env.VOICE_FACTORY_AUDIO_URL, trailingSilenceMs: Number(process.env.VOICE_FACTORY_TRAILING_SILENCE_MS ?? 1000)});
      activeRecord!.fixture = fixture; activeRecord!.replay = replay;
      expect(replay.warnings).toEqual([]); expect(replay.generationEvents).toEqual([]);
      expect(replay.utterances, 'One complete phrase is required; ASR text is never repaired').toHaveLength(1);
      const phrase = replay.utterances[0];
      const action = parseDeckVoice(phrase);
      activeRecord!.recognizedAction = action;
      // Numeric rendering and punctuation are ASR formatting, but omitted command words are failures.
      const canonical = (value: string) => value.toLowerCase().replace(/ё/g, 'е').replace(/двадцать четыре/g, '24').replace(/двадцать/g, '20').replace(/один/g, '1').replace(/[.,!?;:]/g, '').replace(/\s+/g, ' ').trim();
      activeRecord!.completeTranscript = canonical(phrase) === canonical(fixture!.text);
      expect(canonical(phrase), 'ASR must retain the complete command, not only a matching action kind').toBe(canonical(fixture!.text));
      expect(action.kind).toBe(fixture!.expectedKind);
      if (id === 'size') expect(action).toMatchObject({size_pt: 24});
      if (id === 'color') expect(action).toMatchObject({color: 'DC2626'});
      if (id === 'move') expect(action).toMatchObject({dx: 20 / 1280, dy: 0});
      if (id === 'select') expect(action).toMatchObject({number: 1});
      if (id === 'replace' || id === 'append') {
        expect('text' in action && action.text).toMatch(id === 'replace' ? /^План запуска[.!]?$/i : /^Готово[.!]?$/i);
      }
      const {result} = await perform(phrase);
      if (id === 'select') expect(context.selectedId).toBe(deckSelectable(state.scenes[0])[0].id);
      if (id === 'size') expect(selected().style?.size_pt).toBe(24);
      if (id === 'color') expect(selected().style?.color).toBe('DC2626');
      if (id === 'move') expect(selected().box[0]).toBeCloseTo(beforeElement!.box[0] + 20 / 1280, 6);
      if (id === 'replace' && action.kind === 'text') { expect(selected().text).toBe(action.text); await assertLiveText(action.text); }
      if (id === 'append' && action.kind === 'appendText') expect(selected().text).toBe(`${beforeElement!.text.trimEnd()} ${action.text}`);
      if (id === 'undo') {
        expect(semantic(state)).not.toEqual(before);
        expect(selected().text).toBe(beforeElement!.text.replace(/ Подготовка проверки отмены\.$/, ''));
      }
      if (id === 'next') expect(context.index).toBe(1);
      if (id === 'previous') expect(context.index).toBe(0);
      if (!['select', 'next', 'previous'].includes(id)) expect(result.state, 'A mutation response is required').toBeDefined();
    }), 90000);

  it.skipIf(!priorFixture)('persists dictated text from the original reference PCM fixture', async () => recordCase('audio-reference-dictation', async () => {
    await resetSelection();
    await perform('Замени текст на Контрольный текст до распознавания.');
    const {replayAudio} = await import(audioModule);
    const replay = await replayAudio(priorFixture!, {base: process.env.VOICE_FACTORY_AUDIO_URL, trailingSilenceMs: Number(process.env.VOICE_FACTORY_TRAILING_SILENCE_MS ?? 1000)});
    activeRecord!.replay = replay;
    activeRecord!.provenance = 'Existing supplied fixture; speaker/synthesis provenance not independently established. PCM replay, no physical microphone.';
    expect(replay.utterances).toHaveLength(2);
    expect(parseDeckVoice(replay.utterances[0]).kind).toBe('textStart');
    const {result} = await perform(replay.utterances[0]);
    expect(result.dictate).toEqual({slide: context.index + 1, id: context.selectedId});
    expect(replay.utterances[1]).toMatch(/^Один, два, три[.!]?$/);
    await perform(replay.utterances[1], true);
    expect(selected().text).toBe(replay.utterances[1]);
    await assertLiveText(replay.utterances[1]);
  }), 90000);
});
