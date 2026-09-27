import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {Microphone,Transport} from './transport';
import {createWorklet,type FlushMessage} from './pcm-worklet.test-helper';

class Socket{
  static OPEN=1;static instances:Socket[]=[];
  readyState=0;bufferedAmount=0;
  onopen:(()=>void)|null=null;
  onmessage:(({data}:{data:string})=>void)|null=null;
  onclose:(({code}:{code:number})=>void)|null=null;
  onerror:(()=>void)|null=null;
  send=vi.fn();close=vi.fn(()=>{this.readyState=2;});
  constructor(_url:string){Socket.instances.push(this);}
  ready(audioSeq=0){this.readyState=1;this.onopen?.();this.message({type:'ready',seq:0,audio_seq:audioSeq,audio_offset:audioSeq*512});}
  message(data:object){this.onmessage?.({data:JSON.stringify(data)});}
  disconnect(code=1006){this.readyState=3;this.onclose?.({code});}
}

function microphoneHarness(){
  const tracks=[{stop:vi.fn(),onended:null as (()=>void)|null}];
  const stream={getTracks:()=>tracks,getAudioTracks:()=>tracks};
  const media=vi.fn().mockResolvedValue(stream);
  const source={connect:vi.fn()};
  const context={
    state:'running',audioWorklet:{addModule:vi.fn().mockResolvedValue(undefined)},
    createGain:()=>({gain:{value:1},connect:vi.fn()}),createMediaStreamSource:()=>source,
    destination:{},onstatechange:null as (()=>void)|null,
    resume:vi.fn().mockResolvedValue(undefined),close:vi.fn().mockResolvedValue(undefined),
  };
  const outgoing:(ArrayBuffer|FlushMessage)[]=[];
  const worklet=createWorklet(48000,data=>outgoing.push(data));
  const port={
    onmessage:null as (({data}:{data:ArrayBuffer|FlushMessage})=>void)|null,
    postMessage:vi.fn((data:FlushMessage)=>worklet.receive(data)),close:vi.fn(),
  };
  const node={port,connect:(destination:unknown)=>destination,disconnect:vi.fn()};
  vi.stubGlobal('navigator',{mediaDevices:{getUserMedia:media}});
  vi.stubGlobal('AudioContext',class{constructor(){return context;}});
  vi.stubGlobal('AudioWorkletNode',class{constructor(){return node;}});
  return {tracks,stream,media,source,context,node,worklet,outgoing,deliver:()=>{
    while(outgoing.length){const data=outgoing.shift()!;port.onmessage?.({data});}
  }};
}

beforeEach(()=>{
  vi.useFakeTimers();Socket.instances=[];
  vi.stubGlobal('WebSocket',Socket);vi.stubGlobal('location',{protocol:'http:',host:'localhost'});
});
afterEach(()=>{vi.useRealTimers();vi.unstubAllGlobals();vi.restoreAllMocks();});
const transport=()=>new Transport({id:'test',token:'test',mode:'live'},()=>0,vi.fn(),vi.fn(),vi.fn());
const pcm=()=>new Int16Array(512).buffer;

describe('Transport.drain',()=>{
  it('waits for the captured last sequence, not later audio, and never sends stop',async()=>{
    const t=transport(),ws=Socket.instances[0];ws.ready();
    await t.drain();t.audio(pcm());t.audio(pcm());
    const done=vi.fn(),drained=t.drain().then(done);t.audio(pcm());
    ws.message({type:'audio_ack',audio_seq:1});await Promise.resolve();expect(done).not.toHaveBeenCalled();
    ws.message({type:'audio_ack',audio_seq:2});await drained;
    expect(t.packets.size).toBe(1);expect(done).toHaveBeenCalledTimes(1);
    expect(ws.send.mock.calls.filter(([data])=>typeof data==='string').map(([data])=>JSON.parse(data).type)).toEqual(['auth']);
    expect(vi.getTimerCount()).toBe(0);t.close();
  });

  it('resolves when all audio was acknowledged before drain was called',async()=>{
    const t=transport(),ws=Socket.instances[0];ws.ready();t.audio(pcm());
    ws.message({type:'audio_ack',audio_seq:1});await t.drain();
    expect(vi.getTimerCount()).toBe(0);t.close();
  });

  it('bounds missing acknowledgements and cleans up independent waiters',async()=>{
    const t=transport();Socket.instances[0].ready();t.audio(pcm());
    const expired=expect(t.drain(25)).rejects.toThrow();const later=t.drain(100);
    await vi.advanceTimersByTimeAsync(25);await expired;
    Socket.instances[0].message({type:'audio_ack',audio_seq:1});await later;
    expect(vi.getTimerCount()).toBe(0);t.close();
  });

  it('replays outstanding audio after reconnect with the original drain deadline',async()=>{
    const t=transport(),first=Socket.instances[0];first.ready();
    t.audio(pcm());first.message({type:'audio_ack',audio_seq:1});t.audio(pcm());
    const drained=t.drain(2000),done=vi.fn();void drained.then(done);
    first.disconnect();await vi.advanceTimersByTimeAsync(700);
    const second=Socket.instances[1];second.ready(1);
    const packets=second.send.mock.calls.map(([data])=>data).filter(data=>data instanceof ArrayBuffer);
    expect(packets).toHaveLength(1);expect(new DataView(packets[0]).getBigUint64(0,true)).toBe(2n);
    first.message({type:'audio_ack',audio_seq:2});await Promise.resolve();expect(done).not.toHaveBeenCalled();
    second.message({type:'audio_ack',audio_seq:2});await drained;expect(done).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);t.close();
  });

  it('uses the reconnect ready cursor when the last acknowledgement was lost',async()=>{
    const t=transport(),first=Socket.instances[0];first.ready();t.audio(pcm());
    const drained=t.drain(2000);first.disconnect();await vi.advanceTimersByTimeAsync(700);
    Socket.instances[1].ready(1);await drained;expect(t.packets.size).toBe(0);t.close();
  });

  it('notifies the caller to restore editor mode before replaying audio',async()=>{
    const t=new Transport({id:'test',token:'test',mode:'live'},()=>0,vi.fn(),status=>{
      if(status==='Подключено')t.send({type:'editor_mode'});
    },vi.fn());
    Socket.instances[0].ready();t.audio(pcm());Socket.instances[0].disconnect();
    await vi.advanceTimersByTimeAsync(700);const ws=Socket.instances[1];ws.ready();
    expect(ws.send.mock.calls.map(([data])=>typeof data==='string'?JSON.parse(data).type:'audio')).toEqual(['auth','editor_mode','audio']);
    t.close();
  });

  it('can replay a first unacknowledged packet without mistaking it for lost prior audio',async()=>{
    const t=transport(),first=Socket.instances[0];first.ready();t.audio(pcm());
    const drained=t.drain(2000);first.disconnect();await vi.advanceTimersByTimeAsync(700);
    Socket.instances[1].ready(0);Socket.instances[1].message({type:'audio_ack',audio_seq:1});
    await drained;t.close();
  });

  it('rejects on server audio state loss instead of resolving against rebased sequences',async()=>{
    const t=transport(),first=Socket.instances[0];first.ready();t.audio(pcm());
    first.message({type:'audio_ack',audio_seq:1});t.audio(pcm());
    const rejected=expect(t.drain(2000)).rejects.toThrow();first.disconnect();
    await vi.advanceTimersByTimeAsync(700);Socket.instances[1].ready(0);await rejected;t.close();
  });

  it('times out while reconnection never becomes ready',async()=>{
    const t=transport();Socket.instances[0].ready();t.audio(pcm());
    const rejected=expect(t.drain(1000)).rejects.toThrow();Socket.instances[0].disconnect();
    await vi.advanceTimersByTimeAsync(1000);await rejected;t.close();expect(vi.getTimerCount()).toBe(0);
  });

  it('does not extend the timeout when an authenticated reconnect still has no acknowledgement',async()=>{
    const t=transport();Socket.instances[0].ready();t.audio(pcm());
    const rejected=expect(t.drain(1000)).rejects.toThrow();Socket.instances[0].disconnect();
    await vi.advanceTimersByTimeAsync(700);Socket.instances[1].ready();
    await vi.advanceTimersByTimeAsync(300);await rejected;t.close();expect(vi.getTimerCount()).toBe(0);
  });

  it('bounds the default timeout and rejects invalid timeouts',async()=>{
    const t=transport();Socket.instances[0].ready();t.audio(pcm());
    for(const timeout of [-1,NaN,Infinity,2147483648])await expect(t.drain(timeout)).rejects.toThrow(RangeError);
    const rejected=expect(t.drain()).rejects.toThrow();await vi.advanceTimersByTimeAsync(3000);await rejected;
    expect(vi.getTimerCount()).toBe(0);t.close();
  });

  it.each([1000,1002,1003,1007,1008,1009,1010])('rejects permanent closure %i without reconnect',async code=>{
    const t=transport();Socket.instances[0].ready();t.audio(pcm());
    const rejected=expect(t.drain()).rejects.toThrow();Socket.instances[0].disconnect(code);await rejected;
    expect(t.closed).toBe(true);await expect(t.drain()).rejects.toThrow();expect(vi.getTimerCount()).toBe(0);
  });

  it('close rejects all waiters immediately and prevents late events or new audio',async()=>{
    const t=transport(),ws=Socket.instances[0];ws.ready();t.audio(pcm());
    const a=expect(t.drain()).rejects.toThrow(),b=expect(t.drain()).rejects.toThrow();
    t.close();ws.message({type:'audio_ack',audio_seq:1});ws.message({type:'ready',seq:0,audio_seq:1,audio_offset:512});
    await a;await b;await expect(t.drain()).rejects.toThrow();expect(()=>t.audio(pcm())).toThrow();
    expect(t.ready).toBe(false);expect(vi.getTimerCount()).toBe(0);
  });
});

describe('Microphone.stop with the actual worklet',()=>{
  it('delivers the tail once before resolving, matches request IDs, and stops idempotently',async()=>{
    const h=microphoneHarness(),mic=new Microphone(),frame=vi.fn(),done=vi.fn();await mic.start(frame,vi.fn());
    h.worklet.feed(513*3);h.deliver();expect(frame).toHaveBeenCalledTimes(1);
    const stopped=mic.stop({flush:true}),duplicate=mic.stop({flush:true});void stopped.then(done);
    expect(duplicate).toBe(stopped);expect(h.node.port.postMessage).toHaveBeenCalledTimes(1);
    h.node.port.onmessage?.({data:{type:'flush_ack',requestId:999}});await Promise.resolve();expect(done).not.toHaveBeenCalled();
    const tail=h.outgoing.shift()!;expect(tail).toBeInstanceOf(ArrayBuffer);
    h.node.port.onmessage?.({data:tail});expect(frame).toHaveBeenCalledTimes(2);expect(done).not.toHaveBeenCalled();
    expect(h.context.close).not.toHaveBeenCalled();h.deliver();await stopped;
    await mic.stop({flush:true});await mic.stop();
    expect(h.tracks[0].stop).toHaveBeenCalledTimes(1);expect(h.context.close).toHaveBeenCalledTimes(1);
    expect(h.node.disconnect).toHaveBeenCalledTimes(1);expect(h.node.port.close).toHaveBeenCalledTimes(1);
    expect(mic.node).toBeUndefined();expect(mic.context).toBeUndefined();expect(mic.stream).toBeUndefined();
    expect(frame).toHaveBeenCalledTimes(2);expect(done).toHaveBeenCalledTimes(1);expect(vi.getTimerCount()).toBe(0);
  });

  it.each([0,512])('does not emit extra silence for an empty or exact %i-sample frame',async samples=>{
    const h=microphoneHarness(),mic=new Microphone(),frame=vi.fn();await mic.start(frame,vi.fn());
    h.worklet.feed(samples*3);h.deliver();const stopped=mic.stop({flush:true});h.deliver();await stopped;
    expect(frame).toHaveBeenCalledTimes(samples/512);
  });

  it('preserves legacy Live stop: discard queued frames and tail without requesting flush',async()=>{
    const h=microphoneHarness(),mic=new Microphone(),frame=vi.fn();await mic.start(frame,vi.fn());
    h.worklet.feed(600*3);const stale=h.node.port.onmessage!;await mic.stop();
    h.deliver();stale({data:pcm()});await mic.stop();await mic.stop({flush:true});
    expect(frame).not.toHaveBeenCalled();expect(h.node.port.postMessage).not.toHaveBeenCalled();
    expect(h.context.close).toHaveBeenCalledTimes(1);
  });

  it('cleanup cancels a pending flush and cannot deliver its queued final audio',async()=>{
    const h=microphoneHarness(),mic=new Microphone(),frame=vi.fn();await mic.start(frame,vi.fn());h.worklet.feed(100*3);
    const stale=h.node.port.onmessage!;
    const rejected=expect(mic.stop({flush:true})).rejects.toThrow();const cleanup=mic.stop();stale({data:pcm()});
    h.deliver();await cleanup;await rejected;expect(frame).not.toHaveBeenCalled();expect(vi.getTimerCount()).toBe(0);
  });

  it('times out a missing ack, releases resources, and ignores a late tail and ack',async()=>{
    const h=microphoneHarness(),mic=new Microphone(),frame=vi.fn();await mic.start(frame,vi.fn());h.worklet.feed(128*3);
    const rejected=expect(mic.stop({flush:true,timeoutMs:25})).rejects.toThrow();
    await vi.advanceTimersByTimeAsync(25);await rejected;h.deliver();
    expect(frame).not.toHaveBeenCalled();expect(h.tracks[0].stop).toHaveBeenCalledTimes(1);
    expect(h.context.close).toHaveBeenCalledTimes(1);expect(vi.getTimerCount()).toBe(0);
  });

  it('bounds the default flush timeout',async()=>{
    const h=microphoneHarness(),mic=new Microphone();await mic.start(vi.fn(),vi.fn());
    const rejected=expect(mic.stop({flush:true})).rejects.toThrow();await vi.advanceTimersByTimeAsync(1000);await rejected;
    expect(h.context.close).toHaveBeenCalledTimes(1);expect(vi.getTimerCount()).toBe(0);
  });

  it.each([-1,NaN,Infinity,2147483648])('cleans up for an invalid flush timeout %s',async timeoutMs=>{
    const h=microphoneHarness(),mic=new Microphone();await mic.start(vi.fn(),vi.fn());
    await expect(mic.stop({flush:true,timeoutMs})).rejects.toThrow(RangeError);
    expect(h.node.port.postMessage).not.toHaveBeenCalled();expect(h.context.close).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('rejects failed delivery instead of accepting the following flush ack',async()=>{
    const h=microphoneHarness(),mic=new Microphone(),fail=vi.fn();
    await mic.start(()=>{throw new Error('audio buffer full');},fail);h.worklet.feed(128*3);
    const rejected=expect(mic.stop({flush:true})).rejects.toThrow('audio buffer full');h.deliver();await rejected;
    expect(fail).toHaveBeenCalledTimes(1);expect(h.tracks[0].stop).toHaveBeenCalledTimes(1);
    expect(h.context.close).toHaveBeenCalledTimes(1);expect(vi.getTimerCount()).toBe(0);
  });

  it('cleans up if posting the flush request fails',async()=>{
    const h=microphoneHarness(),mic=new Microphone();await mic.start(vi.fn(),vi.fn());
    h.node.port.postMessage.mockImplementation(()=>{throw new Error('port unavailable');});
    await expect(mic.stop({flush:true})).rejects.toThrow('port unavailable');
    expect(h.tracks[0].stop).toHaveBeenCalledTimes(1);expect(h.context.close).toHaveBeenCalledTimes(1);
    expect(h.node.port.onmessage).toBeNull();expect(vi.getTimerCount()).toBe(0);
  });

  it('cleans up a failed worklet load and discards a microphone granted after stop',async()=>{
    const h=microphoneHarness(),mic=new Microphone();h.context.audioWorklet.addModule.mockRejectedValueOnce(new Error('load failed'));
    await expect(mic.start(vi.fn(),vi.fn())).rejects.toThrow('load failed');expect(h.tracks[0].stop).toHaveBeenCalledTimes(1);
    let grant!:(stream:unknown)=>void;h.media.mockReturnValueOnce(new Promise(resolve=>{grant=resolve;}));
    const starting=mic.start(vi.fn(),vi.fn());await mic.stop();grant(h.stream);await starting;
    expect(h.tracks[0].stop).toHaveBeenCalledTimes(2);expect(mic.stream).toBeUndefined();expect(mic.node).toBeUndefined();
  });

  it('stops all resources even when disconnect or context close fails',async()=>{
    const h=microphoneHarness(),mic=new Microphone();await mic.start(vi.fn(),vi.fn());
    h.node.disconnect.mockImplementation(()=>{throw new Error('disconnect failed');});
    h.context.close.mockRejectedValueOnce(new Error('close failed'));
    const rejected=expect(mic.stop({flush:true})).rejects.toThrow('disconnect failed');h.deliver();await rejected;
    expect(h.node.port.close).toHaveBeenCalledTimes(1);expect(h.tracks[0].stop).toHaveBeenCalledTimes(1);
    expect(h.context.close).toHaveBeenCalledTimes(1);expect(h.context.onstatechange).toBeNull();
    expect(mic.node).toBeUndefined();expect(mic.stream).toBeUndefined();expect(mic.context).toBeUndefined();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('bounds shutdown even when closing the audio context never settles',async()=>{
    const h=microphoneHarness(),mic=new Microphone();await mic.start(vi.fn(),vi.fn());
    h.context.close.mockReturnValueOnce(new Promise(()=>{}));
    const rejected=expect(mic.stop({flush:true})).rejects.toThrow();h.deliver();
    await vi.advanceTimersByTimeAsync(1000);await rejected;
    expect(h.tracks[0].stop).toHaveBeenCalledTimes(1);expect(h.node.port.onmessage).toBeNull();
    expect(mic.context).toBeUndefined();expect(vi.getTimerCount()).toBe(0);
  });

  it('allows a new recording after a completed stop',async()=>{
    const h=microphoneHarness(),mic=new Microphone(),frame=vi.fn();await mic.start(frame,vi.fn());await mic.stop();
    await mic.start(frame,vi.fn());h.node.port.onmessage?.({data:pcm()});expect(frame).toHaveBeenCalledTimes(1);await mic.stop();
  });

  it('supports the editor order: flush, audio acknowledgement, then caller-owned server stop',async()=>{
    const h=microphoneHarness(),mic=new Microphone(),t=transport(),ws=Socket.instances[0];ws.ready();
    await mic.start(frame=>t.audio(frame),vi.fn());h.worklet.feed(127*3);
    const stopped=mic.stop({flush:true});h.deliver();await stopped;
    const commands=()=>ws.send.mock.calls.map(([data])=>data).filter(data=>typeof data==='string').map(data=>JSON.parse(data).type);
    expect(commands()).toEqual(['auth']);expect(t.audioSeq).toBe(1);
    const drained=t.drain();ws.message({type:'audio_ack',audio_seq:1});await drained;
    expect(commands()).toEqual(['auth']);t.send({type:'stop'});expect(commands()).toEqual(['auth','stop']);t.close();
  });
});
