import React,{useEffect,useState} from 'react';
import {Mic,Square,MonitorPlay,ArrowRight} from 'lucide-react';
import type {PageProps} from '../router';
import type {Slide} from '../store';
import {useSession} from './useSession';
import './stage.css';

const time=(ms:number)=>`${Math.floor(ms/60000).toString().padStart(2,'0')}:${Math.floor(ms/1000%60).toString().padStart(2,'0')}`;

function SlidePreview({slide}:{slide:Slide}){
 if(slide.html)return <div className="stage-frame-wrap"><iframe className="stage-frame" sandbox="" srcDoc={slide.html} title="Слайд"/></div>;
 return <div className="stage-sketch">{slide.title&&<h4>{slide.title}</h4>}<ul>{slide.bullets.map((b,i)=><li key={i}>{b}</li>)}</ul></div>;
}

export default function StagePage(_:PageProps){
 const s=useSession();
 const [draft,setDraft]=useState('');

 useEffect(()=>{
  function onKey(e:KeyboardEvent){
   const tag=(document.activeElement as HTMLElement|null)?.tagName;
   if(tag==='INPUT'||tag==='TEXTAREA')return;
   if(e.code==='Space'){e.preventDefault();s.fixDraft();}
   else if(e.code==='Backspace'){e.preventDefault();s.removeLast();}
  }
  window.addEventListener('keydown',onKey);
  return ()=>window.removeEventListener('keydown',onKey);
 },[s.fixDraft,s.removeLast]);

 function openHall(){
  if(!s.sessionId)return;
  window.open(`${location.pathname}${location.search}#/audience/${s.sessionId}`,'_blank');
 }

 const sentences=Object.values(s.state.sentences).sort((a,b)=>a.t0-b.t0),tail=sentences.slice(-6);

 return <div className="stage">
  <header className="stage-head">
   <div className="stage-connection"><span className={s.connection==='Подключено'?'on':''}/>{s.connection}</div>
   <select className="stage-select" title="Дизайн-система" value={s.designSystemId} onChange={e=>s.selectDesignSystem(e.target.value)} disabled={!s.designSystems.length}>
    <option value="">Дизайн-система по умолчанию</option>
    {s.designSystems.map(id=><option key={id} value={id}>{id}</option>)}
   </select>
   <button className="button outline" title="Открыть окно зала" disabled={!s.sessionId} onClick={openHall}><MonitorPlay size={16}/>Зал</button>
  </header>
  {s.error&&<div className="notice" role="alert">{s.error}<button onClick={s.clearError} aria-label="Закрыть сообщение">×</button></div>}
  <div className="stage-body">
   <section className="stage-slide"><h3>Текущий слайд</h3>{s.current?<SlidePreview slide={s.current}/>:<div className="stage-empty">Пока пусто</div>}</section>
   <section className="stage-slide"><h3>Черновик</h3>{s.draft?<SlidePreview slide={s.draft}/>:<div className="stage-empty">Ждём фрагмент</div>}</section>
  </div>
  <div className="stage-transcript">
   {tail.map(sent=><p key={sent.id}><time>{time(sent.t0)}</time>{sent.text}</p>)}
   {s.state.partial&&<p className="stage-partial">{s.state.partial}<span>▍</span></p>}
   {!tail.length&&!s.state.partial&&<p className="stage-empty-line">Транскрипт появится здесь</p>}
  </div>
  <footer className="stage-controls">
   {s.live
    ?<button className={`button ${s.recording?'stop':'primary'}`} disabled={s.busy} onClick={()=>void(s.recording?s.stopRecording():s.startRecording())}>{s.recording?<Square size={15}/>:<Mic size={16}/>}{s.recording?'Стоп':'Запись'}</button>
    :<form className="stage-composer" onSubmit={e=>{e.preventDefault();if(draft.trim()){void s.sendText(draft);setDraft('');}}}>
      <input value={draft} onChange={e=>setDraft(e.target.value)} placeholder="Текст вместо микрофона" maxLength={2000}/>
      <button className="button primary" disabled={!draft.trim()||s.busy} title="Отправить"><ArrowRight size={15}/></button>
     </form>}
   <span className="stage-keys"><kbd>Пробел</kbd>зафиксировать<kbd>Backspace</kbd>убрать</span>
  </footer>
 </div>;
}
