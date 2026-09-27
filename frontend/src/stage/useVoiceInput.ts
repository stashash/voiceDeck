import {useEffect,useRef,useState} from 'react';
import {Microphone,Transport} from '../transport';
import {VoiceContextTimeline,type VoicePhrase} from './voiceContext';

export function useVoiceInput(onPhrase:(text:string,phrase?:VoicePhrase)=>void,contextKey?:()=>string){
 const callback=useRef(onPhrase);callback.current=onPhrase;
 const context=useRef(contextKey);context.current=contextKey;
 const timeline=useRef(new VoiceContextTimeline());
 const mic=useRef<Microphone|undefined>(undefined),transport=useRef<Transport|undefined>(undefined),alive=useRef(true);
 const [recording,setRecording]=useState(false),[starting,setStarting]=useState(false),[stopping,setStopping]=useState(false);
 const [partial,setPartial]=useState(''),[error,setError]=useState(''),[connection,setConnection]=useState('');
 const seen=useRef(new Set<string>());
 const [heard,setHeard]=useState(''),[level,setLevel]=useState(0),[device,setDevice]=useState('');
 const meterTime=useRef(0),startingRef=useRef(false),stoppingRef=useRef(false),run=useRef(0);
 const finalization=useRef<{finish:(error?:Error)=>void}|null>(null);
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;run.current++;finalization.current?.finish(Error('Запись закрыта'));transport.current?.close();void mic.current?.stop().catch(()=>{});};},[]);
 function invalidate(){timeline.current.clear();}
 async function stop(flush=true){
  const t=transport.current,m=mic.current;
  if(!flush){
   run.current++;invalidate();t?.close();finalization.current?.finish(Error('Завершение фразы прервано'));
   if(stoppingRef.current){await m?.stop().catch(()=>{});return;}
  }else if(stoppingRef.current)return;
  stoppingRef.current=true;setStopping(true);
  try{
   await m?.stop(flush?{flush:true}:undefined);
   if(flush&&t&&!t.closed){
    await t.drain();
    // Keep restart disabled until the server has emitted the tail's final text.
    await new Promise<void>((resolve,reject)=>{
     const timer=setTimeout(()=>waiter.finish(Error('Сервер не завершил последнюю фразу вовремя')),8000);
     const waiter={finish:(error?:Error)=>{clearTimeout(timer);if(finalization.current===waiter)finalization.current=null;if(error)reject(error);else resolve();}};
     finalization.current=waiter;
     try{t.send({type:'stop'});}catch(e){waiter.finish(e instanceof Error?e:Error(String(e)));}
    });
   }
  }catch(e){invalidate();t?.close();if(alive.current)setError(`Запись остановлена без завершения фразы: ${String(e)}`);}
  finally{if(alive.current){setRecording(false);setStopping(false);setLevel(0);}stoppingRef.current=false;}
 }
 async function restart(){
  if(startingRef.current||stoppingRef.current)return;
  run.current++;transport.current?.close();transport.current=undefined;
  await mic.current?.stop();invalidate();setRecording(false);setPartial('');seen.current.clear();await start(true);
 }
 async function start(force=false){
  if(startingRef.current||stoppingRef.current||(recording&&!force))return;
  startingRef.current=true;setStarting(true);setError('');setPartial('');setLevel(0);
  const generation=++run.current;
  const current=()=>alive.current&&run.current===generation;
  try{
   // New recording sessions cannot receive a previous session's delayed phrase.
   transport.current?.close();invalidate();seen.current.clear();
   const r=await fetch('/api/sessions',{method:'POST',signal:AbortSignal.timeout(10000)});
   if(!r.ok)throw Error('Не удалось создать сессию');
   const credentials=await r.json();if(!current())return;
   if(credentials.mode!=='live')throw Error('Сервер распознавания не включён');
   let seq=0;
   const t=new Transport(credentials,()=>seq,event=>{
    if(!current())return;
    if(event.seq){if(event.seq<=seq)return;seq=event.seq;}
    if(event.type==='stopped'||event.type==='flushed')finalization.current?.finish();
    if(event.type==='partial')setPartial(event.text??'');
    if(event.type==='editor_utterance'){
     const id=String(event.utterance_id??'');if(id&&seen.current.has(id))return;
     if(id){seen.current.add(id);if(seen.current.size>1024)seen.current.delete(seen.current.values().next().value!);}
     const text=event.text??'';setPartial('');setHeard(text);
     const key=context.current?.()??'';
     const resolved=timeline.current.resolve(event.t0,event.t1,key);
     if(context.current&&!resolved){setError('Контекст или связь изменились. Фраза не выполнена; повторите команду.');return;}
     setError('');callback.current(text,resolved?{utteranceId:id,contextKey:key,receivedAt:performance.now(),recognitionLagMs:resolved.lagMs}:undefined);
    }
    if(event.type==='warning'){setError(String(event.message));invalidate();}
   },status=>{
    if(!current())return;
    setConnection(status);
    if(status==='Подключено')transport.current?.send({type:'editor_mode'});
    else invalidate();
   },message=>{if(current()){invalidate();finalization.current?.finish(Error(message));setConnection('Ошибка соединения');setError(message);}});
   transport.current=t;
   const deadline=Date.now()+8000;
   while(!t.ready&&Date.now()<deadline&&current())await new Promise(r=>setTimeout(r,50));
   if(!current())return;if(!t.ready)throw Error('Нет связи с распознаванием');t.send({type:'editor_mode'});
   const m=new Microphone();mic.current=m;
   await m.start(pcm=>{
    if(!current())return;
    try{
     const now=performance.now();
     if(now-meterTime.current>120){meterTime.current=now;const samples=new Int16Array(pcm);let energy=0;for(const sample of samples)energy+=(sample/32768)**2;setLevel(Math.min(100,Math.round(Math.sqrt(energy/samples.length)*500)));}
     if(t.ready)timeline.current.record(t.offset/16,(t.offset+pcm.byteLength/2)/16,context.current?.()??'',now);
     t.audio(pcm);
    }catch(e){setError(String(e));invalidate();void stop(false);}
   },message=>{if(current()){setError(message);invalidate();void stop(false);}});
   if(!current()){await m.stop();return;}
   setDevice(m.stream?.getAudioTracks()[0]?.label??'Микрофон');setRecording(true);
  }catch(e){if(current()){setError(String(e));transport.current?.close();}}
  finally{startingRef.current=false;if(alive.current)setStarting(false);}
 }
 return {recording,starting,stopping,partial,error,connection,heard,level,device,start,stop,restart,invalidate};
}
