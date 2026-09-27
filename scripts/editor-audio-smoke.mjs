import fs from 'node:fs';
import assert from 'node:assert/strict';
const base=process.env.BASE_URL??'http://localhost:8088';
const wav=fs.readFileSync(process.argv[2]??'models/sherpa-onnx-nemo-ctc-punct-giga-am-v3-russian-2025-12-16/test_wavs/example.wav');
let pcm;
for(let i=12;i+8<wav.length;){const size=wav.readUInt32LE(i+4),id=wav.toString('ascii',i,i+4);if(id==='fmt '){assert.equal(wav.readUInt16LE(i+8),1);assert.equal(wav.readUInt16LE(i+10),1);assert.equal(wav.readUInt32LE(i+12),16000);assert.equal(wav.readUInt16LE(i+22),16);}if(id==='data')pcm=wav.subarray(i+8,i+8+size);i+=8+size+(size%2);}
assert.ok(pcm);
const c=await(await fetch(base+'/api/sessions',{method:'POST'})).json();assert.equal(c.mode,'live');
const ws=new WebSocket(base.replace('http','ws')+'/ws/session');
const events=[];let ready=false,ack=0;
ws.onopen=()=>ws.send(JSON.stringify({type:'auth',session_id:c.id,token:c.token,from:0}));
ws.onmessage=({data})=>{const e=JSON.parse(data);events.push(e);if(e.type==='ready')ready=true;if(e.type==='audio_ack')ack=e.audio_seq;};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function until(check,timeout=45000){const deadline=Date.now()+timeout;while(!check()){assert.ok(Date.now()<deadline,'Audio pipeline timed out');await sleep(50);}}
try{
 await until(()=>ready);ws.send(JSON.stringify({type:'editor_mode'}));
 // PCM enters exactly the same authenticated stream as the browser microphone.
 const input=Buffer.concat([pcm.subarray(0,16000*2*8),Buffer.alloc(16000*2)]),started=Date.now();let seq=0;
 for(let offset=0;offset<input.length;offset+=1024){const packet=Buffer.alloc(1040);packet.writeBigUInt64LE(BigInt(++seq));packet.writeBigUInt64LE(BigInt(offset/2),8);input.copy(packet,16,offset,Math.min(input.length,offset+1024));ws.send(packet);await sleep(Math.max(0,started+seq*32-Date.now()));}
 await until(()=>ack===seq);ws.send(JSON.stringify({type:'stop'}));await until(()=>events.some(e=>e.type==='editor_utterance'&&e.text?.trim()));
 assert.ok(!events.some(e=>['chunk','slide'].includes(e.type)),'Editor audio must not trigger presentation generation');
 console.log(JSON.stringify({result:'PASS',packetsAcknowledged:ack,partials:events.filter(e=>e.type==='partial').length,utterances:events.filter(e=>e.type==='editor_utterance').map(e=>e.text),warnings:events.filter(e=>e.type==='warning').map(e=>e.message),elapsedMs:Date.now()-started}));
}finally{ws.close();await fetch(`${base}/api/sessions/${c.id}/data`,{method:'DELETE',headers:{Authorization:`Bearer ${c.token}`}});}
