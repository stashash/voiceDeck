import {useEffect,useRef,useState} from 'react';
import {Microphone,Transport} from '../transport';
/** Reuses one ASR session; callbacks always refer to the current slide. */
export function useVoiceInput(onPhrase:(text:string)=>void){
 const callback=useRef(onPhrase);callback.current=onPhrase;
 const mic=useRef<Microphone|undefined>(undefined),transport=useRef<Transport|undefined>(undefined),alive=useRef(true);
 const [recording,setRecording]=useState(false),[starting,setStarting]=useState(false),[partial,setPartial]=useState(''),[error,setError]=useState(''),[connection,setConnection]=useState('');
 const seen=useRef(new Set<string>());
 const [heard,setHeard]=useState(''),[level,setLevel]=useState(0),[device,setDevice]=useState('');
 const meterTime=useRef(0),startingRef=useRef(false);
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;transport.current?.close();void mic.current?.stop();};},[]);
 async function stop(){await mic.current?.stop();if(alive.current)setRecording(false);if(transport.current?.ready)transport.current.send({type:'stop'});}
 async function restart(){if(startingRef.current)return;transport.current?.close();transport.current=undefined;await mic.current?.stop();setRecording(false);setPartial('');seen.current.clear();await start(true);}
 async function start(force=false){if(startingRef.current||(recording&&!force))return;startingRef.current=true;setStarting(true);setError('');setPartial('');setLevel(0);try{
  if(!transport.current||transport.current.closed){const r=await fetch('/api/sessions',{method:'POST',signal:AbortSignal.timeout(10000)});if(!r.ok)throw Error('Не удалось создать сессию');const c=await r.json();if(!alive.current)return;if(c.mode!=='live')throw Error('Сервер распознавания не включён');let seq=0;
   transport.current=new Transport(c,()=>seq,e=>{if(!alive.current)return;if(e.seq){if(e.seq<=seq)return;seq=e.seq;}if(e.type==='partial'){setPartial(e.text??'');if(e.text)setError('');}if(e.type==='editor_utterance'){const id=String(e.utterance_id??'');if(id&&seen.current.has(id))return;if(id)seen.current.add(id);setPartial('');setHeard(e.text??'');setError('');callback.current(e.text??'');}if(e.type==='warning')setError(String(e.message));},s=>{if(!alive.current)return;setConnection(s);if(s==='Подключено')transport.current?.send({type:'editor_mode'});},message=>{if(alive.current){setConnection('Ошибка соединения');setError(message);}});
  }
  const t=transport.current;const deadline=Date.now()+8000;while(!t.ready&&Date.now()<deadline&&alive.current)await new Promise(r=>setTimeout(r,50));if(!alive.current)return;if(!t.ready)throw Error('Нет связи с распознаванием');t.send({type:'editor_mode'});
  const m=new Microphone();mic.current=m;await m.start(pcm=>{try{if(Date.now()-meterTime.current>120){meterTime.current=Date.now();const samples=new Int16Array(pcm);let energy=0;for(const sample of samples)energy+=(sample/32768)**2;setLevel(Math.min(100,Math.round(Math.sqrt(energy/samples.length)*500)));}t.audio(pcm);}catch(e){setError(String(e));void stop();}},e=>{setError(e);void stop();});if(!alive.current){await m.stop();return;}setDevice(m.stream?.getAudioTracks()[0]?.label??'Микрофон');setRecording(true);
 }catch(e){setError(String(e));transport.current?.close();}finally{startingRef.current=false;if(alive.current)setStarting(false);}}
 return {recording,starting,partial,error,connection,heard,level,device,start,stop,restart};
}
