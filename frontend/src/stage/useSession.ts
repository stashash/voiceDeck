/// <reference types="vite/client" />
import {useEffect,useRef,useState} from 'react';
import {initial,reduce,Chunk,Event,Slide,State} from '../store';
import {Credentials,Microphone,Transport} from '../transport';

const DEFAULT_DESIGNER_URL='http://localhost:8090';

export function channelName(sessionId:string){return `voicedeck-stage-${sessionId}`;}

export type ChannelMessage=
 |{kind:'slide';slide:Slide|null}
 |{kind:'subtitle';final:string;partial:string}
 |{kind:'hello'};

export type TransportLike=Pick<Transport,'ready'|'credentials'|'send'|'close'|'audio'>;
export type CreateTransport=(c:Credentials,cursor:()=>number,event:(e:Event)=>void,status:(s:string)=>void,failure:(s:string)=>void)=>TransportLike;
const realTransport:CreateTransport=(c,cursor,event,status,failure)=>new Transport(c,cursor,event,status,failure);

/**
 * Ядро пульта спикера: применяет события транспорта к состоянию и решает, какой слайд уходит
 * в канал зала. Не зависит от React, поэтому решение о фиксации слайда проверяется без рендера.
 */
export class SessionEngine{
 state:State=initial();credentials:Credentials|null=null;connection='Нет сессии';error='';
 currentId:string|null=null;fixedId?:string;suppressed?:string;
 private history:(string|null)[]=[];
 transport?:TransportLike;channel?:BroadcastChannel;
 constructor(private createTransport:CreateTransport,private onChange:()=>void){}
 reset(){this.state=initial();this.currentId=null;this.fixedId=undefined;this.suppressed=undefined;}
 connect(c:Credentials){
  this.transport?.close();this.channel?.close();
  this.credentials=c;this.channel=new BroadcastChannel(channelName(c.id));
  // Окно зала, открытое посреди речи, спрашивает текущий слайд: иначе ждёт следующего.
  this.channel.onmessage=(e:MessageEvent<ChannelMessage>)=>{if(e.data.kind==='hello'){this.broadcastSlide();this.broadcastSubtitle();}};
  this.transport=this.createTransport(c,()=>this.state.seq,e=>this.event(e),s=>{this.connection=s;this.onChange();},m=>{this.error=m;this.onChange();});
  this.onChange();
 }
 close(){this.transport?.close();this.channel?.close();}
 send(command:object){try{this.transport?.send(command);}catch(e){this.error=String(e);this.onChange();}}
 event(e:Event){
  if(e.type==='warning'){this.error=String(e.message);this.onChange();return;}
  if(e.type==='metrics')return;
  this.state=reduce(this.state,e);
  const before=this.currentId;
  this.settle();
  if(this.currentId!==before)this.broadcastSlide();
  this.broadcastSubtitle();
  this.onChange();
 }
 private latest():Chunk|null{
  const withSlide=Object.values(this.state.chunks).filter(c=>this.state.slides[c.id]).sort((a,b)=>a.t0-b.t0);
  return withSlide.at(-1)??null;
 }
 /** Последний фрагмент со слайдом, который ещё не стал текущим. */
 draft():Chunk|null{const l=this.latest();return l&&l.id!==this.currentId?l:null;}
 private settle(){
  const l=this.latest();
  if(!l||l.id===this.suppressed||l.id===this.currentId)return;
  if(l.status==='confirmed'||l.id===this.fixedId){this.history.push(this.currentId);this.currentId=l.id;}
 }
 /** «Вернуть прошлый»: залу снова показывается слайд, который был текущим до этого. */
 revertPrevious(){
  if(!this.history.length)return;
  this.currentId=this.history.pop()??null;
  this.broadcastSlide();this.onChange();
 }
 private broadcastSlide(){
  const slide=this.currentId?this.state.slides[this.currentId]??null:null;
  this.channel?.postMessage({kind:'slide',slide} satisfies ChannelMessage);
 }
 private broadcastSubtitle(){
  const sentences=Object.values(this.state.sentences).sort((a,b)=>a.t0-b.t0);
  this.channel?.postMessage({kind:'subtitle',final:sentences.at(-1)?.text??'',partial:this.state.partial} satisfies ChannelMessage);
 }
 /** Пробел: фиксирует черновик как текущий слайд раньше подтверждения границы сервером. */
 fixDraft(){
  const d=this.draft();if(!d)return;
  this.suppressed=undefined;this.fixedId=d.id;
  const before=this.currentId;this.settle();
  if(this.currentId!==before)this.broadcastSlide();
  this.onChange();
 }
 /** Backspace: убирает последний слайд с экрана зала, не трогая состояние фрагментов. */
 removeCurrent(){
  if(!this.currentId)return;
  this.suppressed=this.currentId;this.currentId=null;
  this.broadcastSlide();this.onChange();
 }
}

export type Session={
 state:State;connection:string;error:string;recording:boolean;busy:boolean;live:boolean;
 designSystems:string[];designSystemId:string;selectDesignSystem:(id:string)=>void;
 sessionId:string|null;current:Slide|null;draft:Slide|null;
 startRecording:()=>Promise<void>;stopRecording:()=>Promise<void>;sendText:(text:string)=>Promise<void>;
 fixDraft:()=>void;removeLast:()=>void;revertPrevious:()=>void;clearError:()=>void;
};

export function useSession():Session{
 const [,tick]=useState(0),force=()=>tick(n=>n+1);
 const engine=useRef<SessionEngine|undefined>(undefined);
 if(!engine.current)engine.current=new SessionEngine(realTransport,force);
 const eng=engine.current;
 const [live,setLive]=useState(false);
 const [designSystems,setDesignSystems]=useState<string[]>([]);
 const [designSystemId,setDesignSystemId]=useState('');
 const [recording,setRecording]=useState(false);
 const [busy,setBusy]=useState(false);
 const mic=useRef<Microphone|undefined>(undefined);

 useEffect(()=>{
  fetch('/health').then(r=>r.json()).then(h=>setLive(h.mode==='live')).catch(()=>{});
  const designerUrl=(import.meta.env.VITE_DESIGNER_URL as string|undefined)??DEFAULT_DESIGNER_URL;
  fetch(`${designerUrl}/design-systems`).then(r=>r.json()).then(d=>setDesignSystems(d.ids??[])).catch(()=>{});
  return ()=>{eng.close();void mic.current?.stop();};
 },[]);

 useEffect(()=>{
  if(eng.connection==='Подключено'&&designSystemId)eng.send({type:'design_system',id:designSystemId});
 },[eng.connection,designSystemId]);

 async function create(){
  setBusy(true);
  try{
   const res=await fetch('/api/sessions',{method:'POST'});
   if(!res.ok)throw new Error(`Не удалось создать сессию (${res.status})`);
   eng.reset();eng.connect(await res.json());
  }catch(e){eng.error=String(e);force();}
  finally{setBusy(false);}
 }
 async function startRecording(){
  setBusy(true);
  try{
   if(!eng.credentials||eng.credentials.mode!=='live'){await create();setBusy(true);}
   const deadline=Date.now()+8000;
   while(!eng.transport?.ready&&Date.now()<deadline)await new Promise(r=>setTimeout(r,50));
   if(!eng.transport?.ready)throw new Error('Нет соединения с сервером распознавания. Попробуйте ещё раз.');
   mic.current=new Microphone();
   await mic.current.start(
    pcm=>{try{eng.transport?.audio(pcm);}catch(e){eng.error=String(e);force();void stopRecording();}},
    message=>{eng.error=message;force();void stopRecording();},
   );
   setRecording(true);
  }catch(e){eng.error=`Не удалось начать запись: ${String(e)}`;force();}
  finally{setBusy(false);}
 }
 async function stopRecording(){await mic.current?.stop();setRecording(false);eng.send({type:'stop'});}
 async function sendText(text:string){
  setBusy(true);
  try{
   if(!eng.credentials)await create();
   const deadline=Date.now()+8000;
   while(eng.connection!=='Подключено'&&Date.now()<deadline)await new Promise(r=>setTimeout(r,50));
   if(eng.connection!=='Подключено')throw new Error('Нет соединения с сервером. Попробуйте ещё раз.');
   eng.send({type:'text',text});
  }catch(e){eng.error=String(e);force();}
  finally{setBusy(false);}
 }

 const draftChunk=eng.draft();
 return {
  state:eng.state,connection:eng.connection,error:eng.error,recording,busy,live,
  designSystems,designSystemId,selectDesignSystem:setDesignSystemId,
  sessionId:eng.credentials?.id??null,
  current:eng.currentId?eng.state.slides[eng.currentId]??null:null,
  draft:draftChunk?eng.state.slides[draftChunk.id]??null:null,
  startRecording,stopRecording,sendText,
  fixDraft:()=>{eng.fixDraft();force();},removeLast:()=>{eng.removeCurrent();force();},
  revertPrevious:()=>{eng.revertPrevious();force();},
  clearError:()=>{eng.error='';force();},
 };
}
