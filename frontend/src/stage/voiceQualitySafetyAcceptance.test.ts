import {describe, expect, it} from 'vitest';
import {VoiceContextTimeline, deletionStillValid} from './voiceContext';
import {editDictation} from './voiceDictation';
import {VoiceCommandQueue} from './voiceCommandQueue';

describe('independent V3 safety contract: audio context', () => {
  it('rejects a late final after manual target change, including switch away and back during speech', () => {
    const timeline = new VoiceContextTimeline();
    timeline.record(0, 320, 'deck-a/slide-a/element-a', 100);
    expect(timeline.resolve(0, 320, 'deck-a/slide-a/element-b', 110)).toBeUndefined();
    timeline.record(320, 640, 'deck-a/slide-a/element-b', 200);
    timeline.record(640, 960, 'deck-a/slide-a/element-a', 300);
    expect(timeline.resolve(200, 900, 'deck-a/slide-a/element-a', 310)).toBeUndefined();
    expect(timeline.resolve(640, 960, 'deck-a/slide-a/element-a', 310)).toEqual({key: 'deck-a/slide-a/element-a', lagMs: 10});
  });

  it('accepts contiguous current context but rejects capture gaps and spans with missing beginning/end', () => {
    const timeline = new VoiceContextTimeline();
    timeline.record(100, 200, 'a', 500); timeline.record(200, 300, 'a', 600);
    expect(timeline.resolve(100, 300, 'a', 620)).toEqual({key: 'a', lagMs: 20});
    expect(timeline.resolve(99, 300, 'a', 620)).toBeUndefined();
    expect(timeline.resolve(100, 302, 'a', 620)).toBeUndefined();
    timeline.record(400, 500, 'a', 700);
    expect(timeline.resolve(150, 450, 'a', 720)).toBeUndefined();
    expect(timeline.resolve(150, 350, 'a', 720)).toBeUndefined();
    timeline.clear();
    expect(timeline.resolve(400, 500, 'a', 720)).toBeUndefined();
  });

  it('rejects malformed timestamps and overly delayed finals', () => {
    const timeline = new VoiceContextTimeline(); timeline.record(0, 100, 'a', 100);
    for (const [start, end] of [[NaN, 100], [0, Infinity], [-1, 100], [100, 100], [0, '100'], [null, 100]]) {
      expect(timeline.resolve(start, end, 'a', 200)).toBeUndefined();
    }
    expect(timeline.resolve(0, 100, 'a', 10101)).toBeUndefined();
  });
});

describe('independent V3 safety contract: deletion identity', () => {
  const pending = {deckId: 'd', variant: 'a', revision: 'r1', slideId: 's2', index: 2, expiresAt: 500};
  const current = {deckId: 'd', variant: 'a', revision: 'r1', slideIds: ['s1', 's2', 's3']};
  it('expires at the deadline and binds document, variant, revision and slide position', () => {
    expect(deletionStillValid(pending, current, 499)).toBe(true);
    expect(deletionStillValid(pending, current, 500)).toBe(false);
    for (const changed of [{...current, deckId: 'other'}, {...current, variant: 'b'}, {...current, revision: 'r2'},
      {...current, slideIds: ['s2', 's1', 's3']}, {...current, slideIds: ['s1', 's3']}]) {
      expect(deletionStillValid(pending, changed, 400)).toBe(false);
    }
    expect(deletionStillValid({...pending, index: 0}, current, 400)).toBe(false);
  });
});

describe('independent V3 safety contract: dictation draft', () => {
  it('keeps command words literal, and combines phrases/paragraphs/correction without finishing implicitly', () => {
    let text = '';
    for (const phrase of ['План запуска', 'буквально Готово', 'новый абзац', 'Двадцать четыре', 'исправь последнее слово на пять']) {
      const result = editDictation(text, phrase);
      expect(result.kind).toBe('draft');
      if (result.kind === 'draft') text = result.text;
    }
    expect(text).toBe('План запуска Готово\n\nДвадцать пять');
    expect(editDictation(text, 'Готово.')).toEqual({kind: 'finish'});
    expect(editDictation(text, 'отмена диктовки')).toEqual({kind: 'cancel'});
    expect(editDictation('', 'буквально отмена диктовки')).toEqual({kind: 'draft', text: 'отмена диктовки'});
    expect(editDictation('', 'Стоп')).toEqual({kind: 'draft', text: 'Стоп'});
    expect(editDictation('', 'Удали слайд')).toEqual({kind: 'draft', text: 'Удали слайд'});
  });
});

function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>(done => { resolve = done; });
  return {promise, resolve};
}

describe('independent V3 safety contract: bounded queue', () => {
  it('rejects excess jobs without executing them and preserves ordered voice selection then edit', async () => {
    const hold = deferred(); const changes: string[] = [];
    const queue = new VoiceCommandQueue(undefined, {maxPending: 2});
    const select = queue.enqueue(async () => { await hold.promise; changes.push('select-b'); });
    const edit = queue.enqueue(async () => { expect(changes).toEqual(['select-b']); changes.push('edit-b'); });
    await expect(queue.enqueue(async () => { changes.push('unexpected'); })).rejects.toThrow();
    hold.resolve(); await Promise.all([select, edit]);
    expect(changes).toEqual(['select-b', 'edit-b']);
  });

  it('never executes a command whose queue age exceeds the limit', async () => {
    const hold = deferred(); let now = 0, executed = false;
    const queue = new VoiceCommandQueue(undefined, {maxAgeMs: 100, now: () => now});
    const active = queue.enqueue(() => hold.promise); await Promise.resolve();
    const stale = queue.enqueue(async () => { executed = true; });
    const rejected = expect(stale).rejects.toThrow();
    now = 101; hold.resolve(); await active; await rejected;
    expect(executed).toBe(false);
  });

  it('stop invalidates pending work without pretending to undo an already committed change', async () => {
    const hold = deferred(); const committed: string[] = [];
    const queue = new VoiceCommandQueue();
    const active = queue.enqueue(async () => { committed.push('already-saved'); await hold.promise; });
    await Promise.resolve();
    const pending = queue.enqueue(async () => { committed.push('must-not-run'); });
    queue.clear(); hold.resolve(); await Promise.all([active, pending]);
    expect(committed).toEqual(['already-saved']);
    await queue.enqueue(async () => { committed.push('new-command'); });
    expect(committed).toEqual(['already-saved', 'new-command']);
  });

  it('reset detaches a stuck task and old completion cannot corrupt the new pending count', async () => {
    const old = deferred(), fresh = deferred(); const counts: number[] = [];
    const queue = new VoiceCommandQueue(value => counts.push(value), {maxPending: 1});
    const active = queue.enqueue(() => old.promise); await Promise.resolve();
    queue.reset();
    const newer = queue.enqueue(() => fresh.promise); await Promise.resolve();
    old.resolve(); await active; await Promise.resolve(); await Promise.resolve();
    expect(queue.pending).toBe(1);
    fresh.resolve(); await newer; await Promise.resolve(); await Promise.resolve();
    expect(queue.pending).toBe(0); expect(counts.every(value => value >= 0)).toBe(true);
  });
});
