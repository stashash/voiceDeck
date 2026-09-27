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

it('rejects excess backlog without dropping the already accepted commands',async()=>{
 let release!:()=>void;const ran:string[]=[];
 const q=new VoiceCommandQueue(()=>{},{maxPending:2});
 const first=q.enqueue(()=>new Promise<void>(r=>{release=r;}));
 const second=q.enqueue(async()=>{ran.push('second');});
 await expect(q.enqueue(async()=>{ran.push('overflow');})).rejects.toThrow('Очередь заполнена');
 release();await Promise.all([first,second]);expect(ran).toEqual(['second']);
});

it('rejects a command that ages out while waiting, without executing its mutation',async()=>{
 let time=0,release!:()=>void,mutated=false;
 const q=new VoiceCommandQueue(()=>{},{maxAgeMs:100,now:()=>time});
 const first=q.enqueue(()=>new Promise<void>(r=>{release=r;}));await Promise.resolve();
 const second=q.enqueue(async()=>{mutated=true;});const rejected=expect(second).rejects.toThrow('устарела');
 time=101;release();await first;await rejected;expect(mutated).toBe(false);
});
