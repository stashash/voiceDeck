import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {isolatedUrl,readPcmWav} from './voice-factory-audio.mjs';
const base=process.env.VOICE_FACTORY_AUDIO_URL??'http://127.0.0.1:8089';
isolatedUrl(base,8089);
const audioIndex=process.argv.indexOf('--audio'),file=audioIndex<0?undefined:process.argv[audioIndex+1];
assert.ok(audioIndex<0||file,'--audio requires a 16kHz mono PCM16 WAV path');
const wav=file?await fs.readFile(file):undefined,pcm=wav?readPcmWav(wav):undefined;
const health=await (await fetch(base+'/health')).json();
assert.equal(health.mode,'live');assert.equal(health.asr,'sherpa-onnx');
const response=await fetch(base+'/api/sessions',{method:'POST'});
assert.ok(response.ok);
const session=await response.json(),events=[],started=performance.now();
const ws=new WebSocket(base.replace('http','ws')+'/ws/session');
let failure,packetCount=0;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const wait=async predicate=>{const deadline=Date.now()+65000;while(!predicate()){if(failure)throw failure;if(Date.now()>deadline)throw Error('Live timed out: '+JSON.stringify(events.filter(e=>e.type==='warning')));await sleep(100);}};
ws.onopen=()=>ws.send(JSON.stringify({type:'auth',session_id:session.id,token:session.token,from:0}));
ws.onmessage=({data})=>events.push(JSON.parse(data));
ws.onerror=()=>{failure=Error('Live WebSocket error');};
ws.onclose=event=>{failure??=Error(`Live WebSocket closed ${event.code}`);};
try{
 await wait(()=>events.some(e=>e.type==='ready'));
 ws.send(JSON.stringify({type:'design_system',id:'vk-tech-shablon'}));
 if(pcm){
  const audioStarted=performance.now();
  for(let offset=0;offset<pcm.length;offset+=1024){
   if(failure)throw failure;
   const packet=Buffer.alloc(1040);packet.writeBigUInt64LE(BigInt(++packetCount));packet.writeBigUInt64LE(BigInt(offset/2),8);
   pcm.copy(packet,16,offset,Math.min(pcm.length,offset+1024));ws.send(packet);
   await sleep(Math.max(0,audioStarted+packetCount*32-performance.now()));
  }
  await wait(()=>events.some(e=>e.type==='audio_ack'&&e.audio_seq===packetCount));
 }else ws.send(JSON.stringify({type:'text',text:'Курс длится четыре недели. Для участников подготовлены занятия, практика и итоговый проект.'}));
 ws.send(JSON.stringify({type:'stop'}));
 await wait(()=>events.some(e=>e.type==='flushed'));
 const chunkIds=[...new Set(events.filter(e=>e.type==='chunk').map(e=>e.chunk.id))];
 assert.ok(chunkIds.length,'No semantic chunk was created');
 await wait(()=>chunkIds.every(id=>events.some(e=>e.type==='slide'&&e.slide.chunk_id===id&&e.slide.source==='designer')));
 const rendered=events.filter(e=>e.type==='slide'&&e.slide.source==='designer'&&e.slide.html?.includes('<'));
 assert.ok(rendered.length,'No rendered designer slide was created');
 if(pcm)assert.ok(events.some(e=>e.type==='final'&&e.sentence?.text),'No final speech transcript');
 const slide=rendered[0].slide;
 assert.ok(slide.html?.includes('<'));
 assert.ok(!events.some(e=>['warning','audio_resync','editor_utterance'].includes(e.type)),'Unexpected generation warning or editor event');
 console.log(JSON.stringify({result:'PASS',scope:pcm?'existing-live-generation-from-pcm':'existing-live-generation-from-transcript',audioCaptureTested:false,source:slide.source,title:slide.title,elapsedMs:Math.round(performance.now()-started),timings:slide.timings,
  processedChunks:chunkIds.length,renderedSlides:rendered.length,
  ...(pcm?{file,sha256:createHash('sha256').update(wav).digest('hex'),sourceAudioMs:pcm.length/32,packetsSent:packetCount,packetsAcknowledged:Math.max(...events.filter(e=>e.type==='audio_ack').map(e=>e.audio_seq)),
   events:events.filter(e=>!['metrics','audio_ack'].includes(e.type)).map(e=>e.type==='slide'?{type:e.type,seq:e.seq,slide:{title:e.slide.title,source:e.slide.source,chunk_id:e.slide.chunk_id,rev:e.slide.rev,htmlLength:e.slide.html?.length,timings:e.slide.timings}}:e)}:{}),warnings:events.filter(e=>e.type==='warning')},null,2));
}finally{
 ws.onclose=null;ws.close();
 const cleanup=await fetch(base+`/api/sessions/${session.id}/data`,{method:'DELETE',headers:{Authorization:`Bearer ${session.token}`}});
 assert.ok(cleanup.ok,'Test session cleanup failed');
}
