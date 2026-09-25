import {describe,it,expect} from 'vitest';
import {SessionEngine,channelName,ChannelMessage} from './useSession';
import type {Chunk,Slide} from '../store';

const chunk=(id:string,rev:number,status:Chunk['status']):Chunk=>({id,rev,status,sentence_ids:['s'],text:'Тема',t0:0,t1:1000,updated_at:0});
const slide=(chunk_id:string,rev:number,html:string):Slide=>({chunk_id,rev,title:null,bullets:[],notes:'',source:'designer',html});

function makeEngine(sessionId:string){
 const engine=new SessionEngine(c=>({ready:true,credentials:c,send:()=>{},close:()=>{},audio:()=>{}}),()=>{});
 engine.connect({id:sessionId,token:'t',mode:'live'});
 return engine;
}
function listen(sessionId:string){
 const ch=new BroadcastChannel(channelName(sessionId));
 const messages:ChannelMessage[]=[];
 ch.onmessage=(e:MessageEvent<ChannelMessage>)=>messages.push(e.data);
 return {messages,close:()=>ch.close()};
}
const slidesOf=(msgs:ChannelMessage[]):(Slide|null)[]=>msgs.filter((m):m is Extract<ChannelMessage,{kind:'slide'}>=>m.kind==='slide').map(m=>m.slide);
const wait=()=>new Promise(r=>setTimeout(r,10));

describe('SessionEngine',()=>{
 it('answers a hall window opened mid-talk with the current slide',async()=>{
  const engine=makeEngine('s-hello');
  engine.event({type:'chunk',seq:1,chunk:chunk('a',1,'confirmed')});
  engine.event({type:'slide',seq:2,slide:slide('a',1,'<section>1</section>')});
  await wait();
  const hall=listen('s-hello');
  const ask=new BroadcastChannel(channelName('s-hello'));
  ask.postMessage({kind:'hello'} satisfies ChannelMessage);
  // Два перехода через канал: вопрос окна зала и ответ пульта.
  for(let i=0;i<50&&!slidesOf(hall.messages).length;i++)await wait();
  expect(slidesOf(hall.messages).at(-1)?.chunk_id).toBe('a');
  ask.close();hall.close();engine.close();
 });

 it('applies a designer slide with html to state',()=>{
  const engine=makeEngine('s-state');
  engine.event({type:'chunk',seq:1,chunk:chunk('a',1,'provisional')});
  engine.event({type:'slide',seq:2,slide:slide('a',1,'<section>1</section>')});
  expect(engine.state.slides.a.html).toBe('<section>1</section>');
  engine.close();
 });

 it('keeps a provisional draft out of the hall channel until it is fixed',async()=>{
  const engine=makeEngine('s-draft');
  const hall=listen('s-draft');
  engine.event({type:'chunk',seq:1,chunk:chunk('a',1,'provisional')});
  engine.event({type:'slide',seq:2,slide:slide('a',1,'<section>черновик</section>')});
  await wait();
  expect(slidesOf(hall.messages)).toHaveLength(0);
  expect(engine.draft()?.id).toBe('a');
  engine.fixDraft();
  await wait();
  const fixed=slidesOf(hall.messages);
  expect(fixed).toHaveLength(1);
  expect(fixed[0]?.chunk_id).toBe('a');
  hall.close();engine.close();
 });

 it('sends a confirmed slide to the hall channel without waiting for a key',async()=>{
  const engine=makeEngine('s-confirm');
  const hall=listen('s-confirm');
  engine.event({type:'chunk',seq:1,chunk:chunk('a',1,'confirmed')});
  engine.event({type:'slide',seq:2,slide:slide('a',1,'<section>подтверждён</section>')});
  await wait();
  const confirmed=slidesOf(hall.messages);
  expect(confirmed).toHaveLength(1);
  expect(confirmed[0]?.chunk_id).toBe('a');
  hall.close();engine.close();
 });

 it('keeps the hall slide when the service replaces its chunk',async()=>{
  // Показанный залу слайд не пропадает, когда сервис разбивает или склеивает фрагмент речи.
  const engine=makeEngine('s-revise');
  const hall=listen('s-revise');
  engine.event({type:'chunk',seq:1,chunk:chunk('a',1,'provisional')});
  engine.event({type:'slide',seq:2,slide:slide('a',1,'<section>в зале</section>')});
  engine.fixDraft();
  await wait();
  engine.event({type:'chunk_revise',seq:3,replace_ids:['a'],chunks:[chunk('b',1,'provisional')]});
  await wait();
  const sent=slidesOf(hall.messages);
  expect(sent.at(-1)?.chunk_id).toBe('a');
  expect(sent.some(s=>s===null)).toBe(false);
  expect(engine.shown?.html).toBe('<section>в зале</section>');
  hall.close();engine.close();
 });

 it('removes the current slide from the hall channel on backspace without touching chunk state',async()=>{
  const engine=makeEngine('s-remove');
  engine.event({type:'chunk',seq:1,chunk:chunk('a',1,'confirmed')});
  engine.event({type:'slide',seq:2,slide:slide('a',1,'<section>текущий</section>')});
  expect(engine.currentId).toBe('a');
  const hall=listen('s-remove');
  engine.removeCurrent();
  await wait();
  const after=slidesOf(hall.messages);
  expect(after).toHaveLength(1);
  expect(after[0]).toBeNull();
  expect(engine.state.chunks.a).toBeDefined();
  expect(engine.state.slides.a).toBeDefined();
  hall.close();engine.close();
 });
});
