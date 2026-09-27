import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';

export type FlushMessage={type:'flush'|'flush_ack';requestId:number};
type Processor={
  port:{onmessage:(({data}:{data:FlushMessage})=>void)|null};
  process:(inputs:Float32Array[][])=>boolean;
};

export function createWorklet(sampleRate=48000,deliver?:(data:ArrayBuffer|FlushMessage)=>void){
  let Registered!:new()=>Processor;
  const messages:(ArrayBuffer|FlushMessage)[]=[];
  runInNewContext(readFileSync(new URL('../public/pcm-worklet.js',import.meta.url),'utf8'),{
    sampleRate,
    AudioWorkletProcessor:class{
      port={onmessage:null,postMessage:(data:ArrayBuffer|FlushMessage,transfer:Transferable[]=[])=>{
        const copy=structuredClone(data,{transfer});messages.push(copy);deliver?.(copy);
      }};
    },
    registerProcessor:(name:string,processor:new()=>Processor)=>{
      if(name!=='pcm16')throw new Error(`Unexpected processor ${name}`);
      Registered=processor;
    },
  });
  const processor=new Registered();
  return {
    processor,messages,
    receive:(data:FlushMessage)=>processor.port.onmessage?.({data}),
    feed:(samples:number)=>{
      for(let offset=0;offset<samples;offset+=128){
        const input=new Float32Array(Math.min(128,samples-offset));
        for(let i=0;i<input.length;i++)input[i]=.6*Math.sin((offset+i)*2*Math.PI*440/sampleRate);
        processor.process([[input]]);
      }
    },
  };
}
