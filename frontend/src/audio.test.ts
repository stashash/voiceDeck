import {it,expect} from 'vitest';
import fs from 'node:fs';
import vm from 'node:vm';
it.each([44100,48000,96000])('resamples %i Hz continuously into exact 32ms PCM frames',rate=>{
 let Processor:any;const frames:Int16Array[]=[];
 const context={sampleRate:rate,AudioWorkletProcessor:class{port={postMessage:(b:ArrayBuffer)=>frames.push(new Int16Array(b))}},registerProcessor:(_name:string,cls:any)=>Processor=cls};
 vm.runInNewContext(fs.readFileSync('public/pcm-worklet.js','utf8'),context);
 const processor=new Processor();
 for(let offset=0;offset<rate;offset+=128){const input=new Float32Array(Math.min(128,rate-offset));for(let i=0;i<input.length;i++)input[i]=2*Math.sin((offset+i)*2*Math.PI*440/rate);processor.process([[input]]);}
 expect(frames.length).toBe(31);expect(frames.every(f=>f.length===512)).toBe(true);expect(processor.index).toBe(128);expect(Math.max(...frames[3])).toBe(32767);expect(Math.min(...frames[3])).toBe(-32768);
});
