import {describe,expect,it} from 'vitest';
import {createWorklet} from './pcm-worklet.test-helper';

describe('actual PCM worklet flush',()=>{
  for(const rate of [16000,44100,48000,96000]){
    it.each([0,1,127,128,255,511,512,513,1023,1024])(`pads only a residual frame at ${rate} Hz (%i samples)`,samples=>{
      const inputSamples=Math.ceil(samples*rate/16000);
      const worklet=createWorklet(rate);
      worklet.feed(inputSamples);
      const before=worklet.messages.length;
      const reference=createWorklet(rate);
      reference.feed(inputSamples);
      // Continue the same real processor with silence to obtain its buffered prefix.
      reference.processor.process([[new Float32Array(Math.ceil(512*rate/16000))]]);
      worklet.receive({type:'flush',requestId:7});
      const frames=worklet.messages.filter((message):message is ArrayBuffer=>message instanceof ArrayBuffer);
      expect(before).toBe(Math.floor(samples/512));
      expect(frames).toHaveLength(Math.ceil(samples/512));
      expect(frames.every(frame=>frame.byteLength===1024)).toBe(true);
      expect(worklet.messages.at(-1)).toEqual({type:'flush_ack',requestId:7});
      const tail=samples%512;
      if(tail){
        const final=new Int16Array(frames.at(-1)!);
        const expected=new Int16Array(reference.messages[before] as ArrayBuffer);
        expect([...final.slice(0,tail)]).toEqual([...expected.slice(0,tail)]);
        expect([...final.slice(tail)]).toEqual(Array(512-tail).fill(0));
      }
      const delivered=frames.map(frame=>[...new Int16Array(frame)]);
      worklet.receive({type:'flush',requestId:7});
      worklet.receive({type:'flush',requestId:8});
      expect(worklet.processor.process([[new Float32Array(4096).fill(1)]])).toBe(false);
      expect(worklet.messages.filter(message=>message instanceof ArrayBuffer).map(frame=>[...new Int16Array(frame)])).toEqual(delivered);
      expect(worklet.messages.slice(-2)).toEqual([{type:'flush_ack',requestId:7},{type:'flush_ack',requestId:8}]);
    });
  }

  it('acknowledges a flush before any input or after empty input without creating silence',()=>{
    const worklet=createWorklet();
    expect(worklet.processor.process([])).toBe(true);
    worklet.receive({type:'flush',requestId:1});
    expect(worklet.messages).toEqual([{type:'flush_ack',requestId:1}]);
  });
});
