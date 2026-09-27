import {expect, it} from 'vitest';
import {VoiceCommandQueue} from './voiceCommandQueue';

it('recovery detaches a hung task and its late completion cannot corrupt the new count', async()=>{
  const counts:number[]=[];
  const queue=new VoiceCommandQueue(n=>counts.push(n));
  let release!:()=>void;
  const hung=queue.enqueue(()=>new Promise<void>(r=>{release=r;}));
  await Promise.resolve();
  const cancelled=queue.enqueue(async()=>{throw Error('must not execute');});
  queue.reset();
  let executed=false;
  await queue.enqueue(async()=>{executed=true;});
  expect(executed).toBe(true);
  release();await Promise.all([hung,cancelled]);
  await Promise.resolve();
  expect(queue.pending).toBe(0);
  expect(counts.every(n=>n>=0)).toBe(true);
});

it('keeps rapid commands ordered across a slow save', async () => {
  const queue = new VoiceCommandQueue();
  let release!: () => void;
  const save = new Promise<void>(resolve => { release = resolve; });
  const events: string[] = [];
  const first = queue.enqueue(async () => { events.push('select'); await save; events.push('saved'); });
  const second = queue.enqueue(async () => { events.push('move'); });
  await Promise.resolve();
  expect(events).toEqual(['select']);
  release();
  await Promise.all([first, second]);
  expect(events).toEqual(['select', 'saved', 'move']);
});

it('stop cancels pending work and new commands still run after a failure', async () => {
  const queue = new VoiceCommandQueue();
  const events: string[] = [];
  const cancelled = queue.enqueue(async () => { events.push('wrong'); });
  queue.clear();
  const failed = queue.enqueue(async () => { throw Error('save failed'); });
  const next = queue.enqueue(async () => { events.push('next'); });
  await Promise.allSettled([cancelled, failed, next]);
  expect(events).toEqual(['next']);
});
