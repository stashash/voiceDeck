// Run against an already running application. Only test-created sessions are deleted.
import assert from 'node:assert/strict';
const base=process.env.BASE_URL??'http://localhost:8088';
const health=await (await fetch(base+'/health')).json();assert.equal(health.mode,'demo');
const c=await (await fetch(base+'/api/sessions',{method:'POST'})).json();
const headers={Authorization:`Bearer ${c.token}`};
const events=[];
const wait=(predicate,timeout=12000)=>new Promise((resolve,reject)=>{const start=Date.now();const timer=setInterval(()=>{if(predicate()){clearInterval(timer);resolve();}else if(Date.now()-start>timeout){clearInterval(timer);reject(new Error('Timed out waiting for event'));}},25);});
async function connect(from){const ws=new WebSocket(base.replace('http','ws')+'/ws/session');let ready=false;ws.onopen=()=>ws.send(JSON.stringify({type:'auth',session_id:c.id,token:c.token,from}));ws.onmessage=({data})=>{const e=JSON.parse(data);events.push(e);if(e.type==='ready')ready=true;};await wait(()=>ready);return ws;}
try{
 assert.equal((await fetch(base+`/api/sessions/${c.id}/snapshot`)).status,401);
 const foreign=await (await fetch(base+'/api/sessions',{method:'POST'})).json();
 assert.equal((await fetch(base+`/api/sessions/${c.id}/snapshot`,{headers:{Authorization:`Bearer ${foreign.token}`}})).status,401);
 await fetch(base+`/api/sessions/${foreign.id}/data`,{method:'DELETE',headers:{Authorization:`Bearer ${foreign.token}`}});
 const unauth=new WebSocket(base.replace('http','ws')+'/ws/session');let rejected=false;unauth.onopen=()=>unauth.send(JSON.stringify({type:'auth',session_id:c.id,token:'bad',from:0}));unauth.onclose=e=>rejected=e.code===1008;await wait(()=>rejected); 
 let ws=await connect(0);
 ws.send(JSON.stringify({type:'text',text:'Архитектура работает локально. Аудио остаётся на устройстве. Слайды появляются из готовых фрагментов.'}));
 await wait(()=>events.some(e=>e.type==='slide'));
 const chunk=events.find(e=>e.type==='chunk').chunk;
 assert.equal(chunk.sentence_ids.length,3);
 ws.send(JSON.stringify({type:'revise',operation:'split',chunk_id:chunk.id,rev:2,split_at:1}));
 await wait(()=>events.some(e=>e.type==='chunk_revise'));
 const snapshot=await(await fetch(base+`/api/sessions/${c.id}/snapshot`,{headers})).json();assert.equal(snapshot.chunks.length,2);
 const html=await(await fetch(base+`/api/sessions/${c.id}/export?format=html`,{headers})).text();assert.ok(html.includes('<!doctype html>'));
 ws.close();await new Promise(r=>setTimeout(r,150));events.length=0;
 ws=await connect(0);assert.equal(events.filter(e=>e.type==='final').length,3);assert.equal(events.filter(e=>e.type==='chunk_revise').length,1);
 const seq=events.filter(e=>e.seq&&e.type!=='ready').map(e=>e.seq);assert.deepEqual(seq,seq.map((_,i)=>i+1));ws.close();
 console.log('PASS: auth, session isolation, transcript, chunk deadline, slide, split, export, replay');
}finally{await fetch(base+`/api/sessions/${c.id}/data`,{method:'DELETE',headers});}
