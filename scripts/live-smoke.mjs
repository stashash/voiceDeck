import fs from 'node:fs';
import assert from 'node:assert/strict';
const base=process.env.BASE_URL??'http://localhost:8088';
const health=await(await fetch(base+'/health')).json();assert.equal(health.mode,'live');
const wav=fs.readFileSync(process.argv[2]??'models/sherpa-onnx-nemo-ctc-punct-giga-am-v3-russian-2025-12-16/test_wavs/example.wav');
assert.equal(wav.toString('ascii',0,4),'RIFF');let pcm;
for(let i=12;i+8<wav.length;){const id=wav.toString('ascii',i,i+4),size=wav.readUInt32LE(i+4);if(id==='fmt '){assert.equal(wav.readUInt16LE(i+8),1);assert.equal(wav.readUInt16LE(i+10),1);assert.equal(wav.readUInt32LE(i+12),16000);assert.equal(wav.readUInt16LE(i+22),16);}if(id==='data')pcm=wav.subarray(i+8,i+8+size);i+=8+size+(size%2);}
assert.ok(pcm);
const c=await(await fetch(base+'/api/sessions',{method:'POST'})).json(),events=[],chunks=new Map(),sketches=new Map();
const ws=new WebSocket(base.replace('http','ws')+'/ws/session');
let ready=false,ack=0;
ws.onopen=()=>ws.send(JSON.stringify({type:'auth',session_id:c.id,token:c.token,from:0}));
ws.onmessage=({data})=>{const e=JSON.parse(data);events.push(e);if(e.type==='ready')ready=true;if(e.type==='audio_ack')ack=e.audio_seq;if(e.type==='final')console.log('FINAL',e.sentence.text);if(e.type==='warning')console.error('WARNING',e.message);if(e.type==='chunk')chunks.set(e.chunk.id,e.chunk.rev);if(e.type==='chunk_revise'){for(const id of e.replace_ids){chunks.delete(id);sketches.delete(id);}for(const c of e.chunks)chunks.set(c.id,c.rev);}if(e.type==='slide')sketches.set(e.slide.chunk_id,e.slide.rev);};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function until(check,timeout=30000){const start=Date.now();while(!check()){if(Date.now()-start>timeout)throw new Error('Audio pipeline timed out');await sleep(50);}}
try{
 await until(()=>ready);let seq=0;const input=Buffer.concat([pcm,Buffer.alloc(32000)]),started=Date.now();
 for(let offset=0;offset<input.length;offset+=1024){const packet=Buffer.alloc(1040);packet.writeBigUInt64LE(BigInt(++seq));packet.writeBigUInt64LE(BigInt(offset/2),8);input.copy(packet,16,offset,Math.min(input.length,offset+1024));ws.send(packet);await sleep(Math.max(0,started+seq*32-Date.now()));}
 await until(()=>ack===seq,60000);ws.send(JSON.stringify({type:'stop'}));await until(()=>events.some(e=>e.type==='flushed'));await until(()=>chunks.size>0&&[...chunks].every(([id,rev])=>sketches.get(id)===rev));
 assert.ok(events.some(e=>e.type==='partial'&&e.text.length));assert.ok(events.some(e=>e.type==='final'));assert.ok(events.some(e=>e.type==='chunk'));assert.ok(events.some(e=>e.type==='slide'&&['sketch','designer'].includes(e.slide.source)));
 console.log('PASS live audio:',JSON.stringify({partials:events.filter(e=>e.type==='partial').length,finals:events.filter(e=>e.type==='final').length,chunks:events.filter(e=>e.type==='chunk').length,sketches:events.filter(e=>e.type==='slide').length,elapsedMs:Date.now()-started,embeddings:health.embeddings}));
}finally{ws.close();await fetch(base+`/api/sessions/${c.id}/data`,{method:'DELETE',headers:{Authorization:`Bearer ${c.token}`}});}
