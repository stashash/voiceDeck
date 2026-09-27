import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {isValidElement, type DependencyList, type EffectCallback} from 'react';
import EditPage from '../pages/EditPage';
import * as api from '../designer/api';
import type {DeckStateResponse, DeckVariantState} from '../designer/api';
import {createWorklet, type FlushMessage} from '../pcm-worklet.test-helper';
import {useVoiceInput} from './useVoiceInput';

// No DOM renderer: run the actual component/hooks, JSX handlers and effects.
// Only React scheduling, browser devices and the remote designer are replaced.
const host = vi.hoisted(() => ({
  current: undefined as HookRunner<unknown> | undefined,
  runners: new Set<HookRunner<unknown>>(),
}));

vi.mock('react', async importOriginal => {
  const actual = await importOriginal<typeof import('react')>();
  const hooks = {
    useState: <T,>(initial: T | (() => T)) => host.current!.state(initial),
    useRef: <T,>(initial: T) => host.current!.ref(initial),
    useMemo: <T,>(factory: () => T, deps?: DependencyList) => host.current!.memo(factory, deps),
    useEffect: (effect: EffectCallback, deps?: DependencyList) => host.current!.effect(effect, deps),
  };
  return {...actual, ...hooks, default: {...actual, ...hooks}};
});

vi.mock('react-dom', () => ({flushSync: (action: () => void) => {
  action();
  for (const runner of host.runners) runner.flush();
}}));

vi.mock('../designer/api', async importOriginal => ({
  ...await importOriginal<typeof import('../designer/api')>(),
  getDeckState: vi.fn(), getSlidePatterns: vi.fn(),
  commitDeckDictation: vi.fn(), deckElementAction: vi.fn(),
}));

type Slot = {value?: unknown; deps?: DependencyList; cleanup?: () => void};
function sameDeps(a?: DependencyList, b?: DependencyList) {
  return !!a && !!b && a.length === b.length && a.every((value, i) => Object.is(value, b[i]));
}

class HookRunner<T> {
  value!: T;
  private slots: Slot[] = [];
  private cursor = 0;
  private effects: (() => void)[] = [];
  private dirty = true;
  private scheduled = false;
  private mounted = true;
  constructor(private render: () => T) { host.runners.add(this); this.flush(); }
  private slot() { const index = this.cursor++; return this.slots[index] ??= {}; }
  private schedule() {
    if (!this.mounted) return;
    this.dirty = true;
    if (this.scheduled) return;
    this.scheduled = true;
    queueMicrotask(() => { this.scheduled = false; this.flush(); });
  }
  state<V>(initial: V | (() => V)): [V, (value: V | ((previous: V) => V)) => void] {
    const slot = this.slot();
    if (!('value' in slot)) slot.value = typeof initial === 'function' ? (initial as () => V)() : initial;
    return [slot.value as V, value => {
      const next = typeof value === 'function' ? (value as (previous: V) => V)(slot.value as V) : value;
      if (!Object.is(slot.value, next)) { slot.value = next; this.schedule(); }
    }];
  }
  ref<V>(initial: V): {current: V} {
    const slot = this.slot();
    return (slot.value ??= {current: initial}) as {current: V};
  }
  memo<V>(factory: () => V, deps?: DependencyList): V {
    const slot = this.slot();
    if (!sameDeps(slot.deps, deps)) { slot.value = factory(); slot.deps = deps; }
    return slot.value as V;
  }
  effect(effect: EffectCallback, deps?: DependencyList) {
    const slot = this.slot();
    if (sameDeps(slot.deps, deps)) return;
    slot.deps = deps;
    this.effects.push(() => { slot.cleanup?.(); slot.cleanup = effect() || undefined; });
  }
  flush() {
    let renders = 0;
    while (this.mounted && this.dirty) {
      if (++renders > 100) throw new Error('Hook harness render loop');
      this.dirty = false; this.cursor = 0;
      const previous = host.current; host.current = this;
      try { this.value = this.render(); } finally { host.current = previous; }
      const effects = this.effects.splice(0);
      effects.forEach(effect => effect());
    }
  }
  unmount() {
    this.mounted = false;
    this.slots.forEach(slot => slot.cleanup?.());
    host.runners.delete(this);
  }
}

class Socket {
  static OPEN = 1;
  static instances: Socket[] = [];
  readyState = 0;
  bufferedAmount = 0;
  offset = 0;
  seq = 0;
  onopen?: () => void;
  onmessage?: (event: {data: string}) => void;
  onclose?: (event: {code: number}) => void;
  onerror?: () => void;
  commands: {type: string}[] = [];
  constructor(_url: string) {
    Socket.instances.push(this);
    queueMicrotask(() => { if (this.readyState === 0) { this.readyState = 1; this.onopen?.(); } });
  }
  send(data: string | ArrayBuffer) {
    if (this.readyState !== Socket.OPEN) throw new Error('send on closed socket');
    if (typeof data === 'string') {
      const command = JSON.parse(data); this.commands.push(command);
      if (command.type === 'auth') queueMicrotask(() => this.message({
        type: 'ready', seq: command.from, audio_seq: 0, audio_offset: 0, mode: 'live',
      }));
    } else {
      const packet = new DataView(data), seq = Number(packet.getBigUint64(0, true));
      this.offset = Number(packet.getBigUint64(8, true)) + (data.byteLength - 16) / 2;
      queueMicrotask(() => this.message({type: 'audio_ack', audio_seq: seq}));
    }
  }
  close() { this.readyState = 3; this.onclose?.({code: 1000}); }
  // Deliberately permit a queued message after close to exercise production guards.
  message(event: object) { this.onmessage?.({data: JSON.stringify(event)}); }
  phrase(text: string, span = {t0: 0, t1: 32}) {
    this.message({type: 'editor_utterance', seq: ++this.seq, utterance_id: `u-${this.seq}`, text, ...span});
  }
  flushed() { this.message({type: 'stopped', seq: ++this.seq}); this.message({type: 'flushed'}); }
}

class AudioNode {
  static instances: AudioNode[] = [];
  autoFlush = true;
  private outgoing: (ArrayBuffer | FlushMessage)[] = [];
  readonly worklet = createWorklet(48000, data => this.outgoing.push(data));
  readonly port = {
    onmessage: null as ((event: {data: ArrayBuffer | FlushMessage}) => void) | null,
    postMessage: vi.fn((message: FlushMessage) => {
      this.worklet.receive(message);
      if (this.autoFlush) queueMicrotask(() => this.deliver());
    }),
    close: vi.fn(),
  };
  disconnect = vi.fn();
  constructor() { AudioNode.instances.push(this); }
  connect(destination: unknown) { return destination; }
  deliver() {
    while (this.outgoing.length) {
      const data = this.outgoing.shift()!;
      this.port.onmessage?.({data});
    }
  }
}

const track = {label: 'Test microphone', stop: vi.fn(), onended: null as (() => void) | null};
class AudioContextMock {
  state = 'running';
  destination = {};
  onstatechange: (() => void) | null = null;
  audioWorklet = {addModule: vi.fn().mockResolvedValue(undefined)};
  createGain() { return {gain: {value: 1}, connect: vi.fn()}; }
  createMediaStreamSource() { return {connect: vi.fn()}; }
  resume = vi.fn().mockResolvedValue(undefined);
  close = vi.fn().mockResolvedValue(undefined);
}

let deck: DeckStateResponse;
let nextRevision: number;
function fixture(): DeckStateResponse {
  const variant: DeckVariantState = {
    revision: 'r1', status: 'done', design_system_id: 'test', error: null, findings: [], slide_images: [],
    plan: {title: 'Safety', purpose: '', audience: '', language: 'ru', slides: [
      {id: 'slide-1', kind: 'bullets', title: 'Safety', key_message: '', notes: ''},
    ]},
    scenes: [{slide_id: 'slide-1', pattern_id: 'test', variant: 'a', theme: 'light', elements: [
      {id: 'a', type: 'text', role: 'title', text: 'Alpha', box: [.1, .1, .7, .2]},
      {id: 'b', type: 'text', role: 'body', text: 'Beta', box: [.1, .4, .7, .2]},
    ]}],
  };
  return {...structuredClone(variant), variants: {a: variant}};
}
function mutate(action: (variant: DeckVariantState) => void) {
  deck = structuredClone(deck);
  action(deck.variants.a); deck.variants.a.revision = `r${++nextRevision}`;
  return structuredClone(deck.variants.a);
}

async function settle() { for (let i = 0; i < 60; i++) await Promise.resolve(); }
async function tick(ms: number) { await vi.advanceTimersByTimeAsync(ms); await settle(); }
function deferred() { let resolve!: () => void; const promise = new Promise<void>(done => { resolve = done; }); return {promise, resolve}; }

type Props = {
  children?: unknown; className?: string; disabled?: boolean; value?: string;
  'aria-label'?: string; onClick?: () => unknown;
  onChange?: (event: {target: {value: string}}) => void;
  onSubmit?: (event: {preventDefault: () => void}) => void;
};
function nodes(tree: unknown): {type: unknown; key: string | null; props: Props}[] {
  if (Array.isArray(tree)) return tree.flatMap(nodes);
  if (!isValidElement<Props>(tree)) return [];
  return [tree, ...nodes(tree.props.children)];
}
function named(page: HookRunner<unknown>, label: string) {
  const node = nodes(page.value).find(node => node.props['aria-label'] === label);
  if (!node) throw new Error(`Missing control: ${label}`);
  return node;
}
async function click(page: HookRunner<unknown>, label: string) {
  const control = named(page, label); expect(control.props.disabled).not.toBe(true);
  control.props.onClick!(); await settle();
}
async function typeCommand(page: HookRunner<unknown>, command: string) {
  named(page, 'Команда редактирования').props.onChange!({target: {value: command}});
  await settle();
  const input = named(page, 'Команда редактирования');
  const form = nodes(page.value).find(node => node.type === 'form' && nodes(node.props.children).includes(input));
  if (!form) throw new Error('Missing command form');
  form.props.onSubmit!({preventDefault() {}}); await settle();
}
function selected(page: HookRunner<unknown>) {
  return nodes(page.value).find(node => node.props.className === 'edit-el-box active')?.key;
}
async function pageHarness() {
  const page = new HookRunner(() => EditPage({deckId: 'deck', variant: 'a'}));
  await settle();
  const first = nodes(page.value).find(node => node.key === 'a' && node.props.className === 'edit-el-box ');
  if (!first) throw new Error('Missing first slide element');
  first.props.onClick!(); await settle(); expect(selected(page)).toBe('a');
  return page;
}
async function startPageMicrophone(page: HookRunner<unknown>) {
  nodes(page.value).find(node => node.props.className?.includes('deck-mic-button'))!.props.onClick!();
  await settle(); await tick(50);
  expect(AudioNode.instances).toHaveLength(1);
  return Socket.instances[0];
}
function capture(socket = Socket.instances.at(-1)!) {
  const t0 = socket.offset / 16, node = AudioNode.instances.at(-1)!;
  node.worklet.feed(512 * 3); node.deliver();
  expect(socket.offset / 16).toBe(t0 + 32);
  return {t0, t1: socket.offset / 16};
}
async function say(text: string, socket = Socket.instances.at(-1)!) {
  socket.phrase(text, capture(socket)); await settle();
}
async function voiceHarness(contextKey?: () => string) {
  const onPhrase = vi.fn();
  const hook = new HookRunner(() => useVoiceInput(onPhrase, contextKey));
  const started = hook.value.start(); await settle(); await tick(50); await started;
  expect(hook.value.recording).toBe(true);
  return {hook, onPhrase, socket: Socket.instances[0], node: AudioNode.instances[0]};
}

beforeEach(() => {
  vi.useFakeTimers({toFake: ['Date', 'performance', 'setTimeout', 'clearTimeout', 'setInterval', 'clearInterval']});
  vi.resetAllMocks(); Socket.instances = []; AudioNode.instances = []; track.onended = null;
  deck = fixture(); nextRevision = 1;
  vi.stubGlobal('WebSocket', Socket);
  vi.stubGlobal('location', {protocol: 'http:', host: 'test'});
  vi.stubGlobal('AudioContext', AudioContextMock);
  vi.stubGlobal('AudioWorkletNode', AudioNode);
  vi.stubGlobal('navigator', {mediaDevices: {getUserMedia: vi.fn().mockResolvedValue({
    getTracks: () => [track], getAudioTracks: () => [track],
  })}});
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (url === '/api/sessions') return {ok: true, json: async () => ({id: `session-${Socket.instances.length}`, token: 'test', mode: 'live'})};
    if (url.includes('/live?')) return {ok: true, text: async () => '<main>Slide</main>'};
    throw new Error(`Unexpected fetch: ${url}`);
  }));
  vi.mocked(api.getDeckState).mockImplementation(async () => structuredClone(deck));
  vi.mocked(api.getSlidePatterns).mockResolvedValue([]);
  vi.mocked(api.commitDeckDictation).mockImplementation(async (_deck, _variant, slide, payload) => {
    const current = deck.variants.a;
    if (payload.expected_revision !== current.revision || payload.target_slide_id !== current.scenes[slide - 1].slide_id)
      throw Object.assign(new Error('Stale dictation'), {status: 409});
    return mutate(variant => { variant.scenes[slide - 1].elements.find(el => el.id === payload.element_id)!.text = payload.text; });
  });
  vi.mocked(api.deckElementAction).mockImplementation(async (_deck, _variant, slide, payload) => mutate(variant => {
    const scene = variant.scenes[slide - 1];
    if (payload.action === 'delete') scene.elements = scene.elements.filter(el => el.id !== payload.element_id);
    else if (payload.action === 'style') scene.elements.find(el => el.id === payload.element_id)!.style = {size_pt: 24};
    else throw new Error(`Unexpected mutation: ${payload.action}`);
  }));
});

afterEach(async () => {
  for (const runner of [...host.runners]) runner.unmount();
  await settle();
  vi.clearAllTimers(); vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks();
});

describe('EditPage voice integration safety', () => {
  it('typed-order: later typed commands preserve an earlier queued selection', async () => {
    const page = await pageHarness(), hold = deferred();
    const apply = vi.mocked(api.deckElementAction).getMockImplementation()!;
    vi.mocked(api.deckElementAction).mockImplementationOnce(async (...args) => { await hold.promise; return apply(...args); });
    await typeCommand(page, 'Сделай крупнее');
    await typeCommand(page, 'Элемент 2'); await typeCommand(page, 'Удали элемент');
    expect(api.deckElementAction).toHaveBeenCalledTimes(1);
    hold.resolve(); await settle();
    expect(api.deckElementAction).toHaveBeenCalledTimes(2);
    expect(api.deckElementAction).toHaveBeenLastCalledWith('deck', 'a', 1, {action: 'delete', element_id: 'b'});
    expect(deck.variants.a.scenes[0].elements.map(el => el.id)).toEqual(['a']);
  });

  it('queue-expiry: cancels the dependent edit when its selection expires, then accepts fresh commands', async () => {
    const page = await pageHarness(), hold = deferred();
    const apply = vi.mocked(api.deckElementAction).getMockImplementation()!;
    vi.mocked(api.deckElementAction).mockImplementationOnce(async (...args) => { await hold.promise; return apply(...args); });
    await typeCommand(page, 'Сделай крупнее');
    expect(api.deckElementAction).toHaveBeenCalledTimes(1);
    await tick(100); await typeCommand(page, 'Элемент 2');
    await tick(900); await typeCommand(page, 'Удали элемент');
    await tick(2000); hold.resolve(); await settle();
    expect(api.deckElementAction).toHaveBeenCalledTimes(1);
    expect(selected(page)).toBe('a');
    expect(deck.variants.a.scenes[0].elements.map(el => el.id)).toEqual(['a', 'b']);
    await typeCommand(page, 'Элемент 2'); await typeCommand(page, 'Удали элемент');
    expect(api.deckElementAction).toHaveBeenLastCalledWith('deck', 'a', 1, {action: 'delete', element_id: 'b'});
  });

  it('manual-finish: saves the draft but never executes a delayed dictated deletion', async () => {
    const page = await pageHarness(), socket = await startPageMicrophone(page);
    await click(page, 'Начать многофразовую диктовку');
    await say('Первый абзац');
    expect(named(page, 'Черновик диктовки').props.value).toBe('Первый абзац');
    const delayed = capture(socket);
    await click(page, 'Сохранить диктовку');
    expect(api.commitDeckDictation).toHaveBeenCalledExactlyOnceWith('deck', 'a', 1, {
      element_id: 'a', text: 'Первый абзац', expected_revision: 'r1', target_slide_id: 'slide-1',
    });
    socket.phrase('Удали элемент', delayed); await settle();
    expect(api.deckElementAction).not.toHaveBeenCalled();
    expect(deck.variants.a.scenes[0].elements[0].text).toBe('Первый абзац');
    await say('Элемент 2'); expect(selected(page)).toBe('b');
  });

  it('typed-selection: rejects earlier audio after a typed target change without disabling fresh voice', async () => {
    const page = await pageHarness(), socket = await startPageMicrophone(page);
    const delayed = capture(socket);
    await typeCommand(page, 'Элемент 2'); expect(selected(page)).toBe('b');
    socket.phrase('Удали элемент', delayed); await settle();
    expect(api.deckElementAction).not.toHaveBeenCalled();
    await say('Сделай крупнее');
    expect(api.deckElementAction).toHaveBeenLastCalledWith('deck', 'a', 1,
      expect.objectContaining({action: 'style', element_id: 'b'}));
  });

  it('queued-phrase: preserves ASR context through EditPage until execution after a typed command', async () => {
    const page = await pageHarness(); await startPageMicrophone(page);
    const hold = deferred(), apply = vi.mocked(api.deckElementAction).getMockImplementation()!;
    vi.mocked(api.deckElementAction).mockImplementationOnce(async (...args) => { await hold.promise; return apply(...args); });
    await typeCommand(page, 'Сделай крупнее');
    // The hook accepts this final now; only the later queue check can reject it.
    await say('Удали элемент');
    await typeCommand(page, 'Элемент 2');
    expect(api.deckElementAction).toHaveBeenCalledTimes(1);
    hold.resolve(); await settle();
    expect(api.deckElementAction).toHaveBeenCalledTimes(1);
    expect(selected(page)).toBe('b');
    expect(deck.variants.a.scenes[0].elements.map(el => el.id)).toEqual(['a', 'b']);
  });

  it('legacy-literal: keeps the one-shot alias and passes mode words literally to the guarded API', async () => {
    const page = await pageHarness(); await startPageMicrophone(page);
    await say('Диктую текст'); await say('начни диктовку');
    expect(api.commitDeckDictation).toHaveBeenCalledExactlyOnceWith('deck', 'a', 1, {
      element_id: 'a', text: 'начни диктовку', expected_revision: 'r1', target_slide_id: 'slide-1',
    });
    expect(nodes(page.value).some(node => node.props['aria-label'] === 'Черновик диктовки')).toBe(false);
  });
});

describe('useVoiceInput with actual microphone/worklet/transport', () => {
  it('forced-stop: microphone failure supersedes graceful flush and blocks late FullEditor callbacks', async () => {
    // FullEditor intentionally supplies no contextKey; generation must protect it.
    const {hook, onPhrase, socket, node} = await voiceHarness();
    const span = capture(socket); await settle(); node.autoFlush = false;
    const stopped = hook.value.stop(); await settle();
    expect(node.port.postMessage).toHaveBeenCalledWith(expect.objectContaining({type: 'flush'}));
    expect(hook.value.stopping).toBe(true);
    track.onended!(); await settle();
    socket.phrase('Удали элемент', span); await settle();
    expect(onPhrase).not.toHaveBeenCalled();
    expect(socket.readyState).toBe(3);
    expect(track.stop).toHaveBeenCalled();
    node.deliver(); await stopped;
    expect(hook.value.recording).toBe(false);
  });

  it('graceful-stop: blocks restart until the final and flushed arrive, preserving phrase metadata', async () => {
    const {hook, onPhrase, socket} = await voiceHarness(() => 'deck/a/context');
    const span = capture(socket); await settle();
    const stopped = hook.value.stop(); await settle();
    expect(socket.commands.at(-1)).toEqual({type: 'stop'});
    expect(hook.value.stopping).toBe(true);
    await hook.value.start(); await hook.value.restart(); await settle();
    expect(Socket.instances).toHaveLength(1);
    socket.phrase('Последняя фраза', span); await settle();
    expect(onPhrase).toHaveBeenCalledExactlyOnceWith('Последняя фраза', expect.objectContaining({
      utteranceId: 'u-1', contextKey: 'deck/a/context', receivedAt: expect.any(Number), recognitionLagMs: expect.any(Number),
    }));
    socket.flushed(); await stopped; await settle();
    expect(hook.value.stopping).toBe(false); expect(hook.value.recording).toBe(false);
    const restarted = hook.value.start(); await settle(); await tick(50); await restarted;
    expect(Socket.instances).toHaveLength(2); expect(hook.value.recording).toBe(true);
    socket.phrase('Stale previous session', span); await settle();
    expect(onPhrase).toHaveBeenCalledTimes(1);
  });

  it('empty-stop: flushed completes a silent recording without waiting for a nonexistent final', async () => {
    const {hook, onPhrase, socket} = await voiceHarness();
    const done = vi.fn(), stopped = hook.value.stop().then(done); await settle();
    expect(socket.commands.at(-1)).toEqual({type: 'stop'});
    expect(done).not.toHaveBeenCalled();
    socket.flushed(); await stopped; await settle();
    expect(done).toHaveBeenCalledTimes(1); expect(onPhrase).not.toHaveBeenCalled();
    expect(hook.value.stopping).toBe(false);
  });

  it('final-before-stop: an already delivered final does not require another final to complete stop', async () => {
    const {hook, onPhrase, socket} = await voiceHarness(() => 'context');
    await say('Already finalized', socket);
    expect(onPhrase).toHaveBeenCalledTimes(1);
    const done = vi.fn(), stopped = hook.value.stop().then(done); await settle();
    expect(socket.commands.at(-1)).toEqual({type: 'stop'});
    expect(done).not.toHaveBeenCalled();
    socket.message({type: 'flushed'}); await stopped; await settle();
    expect(done).toHaveBeenCalledTimes(1); expect(onPhrase).toHaveBeenCalledTimes(1);
    expect(hook.value.stopping).toBe(false);
  });

  it('flush-timeout: bounds missing server completion and suppresses its eventual final', async () => {
    const {hook, onPhrase, socket} = await voiceHarness();
    const span = capture(socket); await settle();
    const done = vi.fn(), stopped = hook.value.stop().then(done); await settle();
    expect(done).not.toHaveBeenCalled();
    await tick(7999); expect(done).not.toHaveBeenCalled();
    await tick(1);
    expect(done).toHaveBeenCalledTimes(1); await stopped;
    expect(hook.value.stopping).toBe(false); expect(hook.value.error).not.toBe('');
    expect(socket.readyState).toBe(3);
    socket.phrase('Late after timeout', span); await settle();
    expect(onPhrase).not.toHaveBeenCalled();
  });
});
