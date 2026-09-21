import React,{useEffect,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {useVirtualizer} from '@tanstack/react-virtual';
import {Mic,Square,Download,Plus,ArrowRight,Check,Layers,FileText,Presentation,Radio,ChevronDown,Scissors,Combine,Play,Trash2,ArrowDown,MonitorPlay} from 'lucide-react';
import {initial,reduce,State,Chunk,Event} from './store';
import {Credentials,Transport,Microphone} from './transport';
import {Router} from './router';
import './style.css';

const time=(ms:number)=>`${Math.floor(ms/60000).toString().padStart(2,'0')}:${Math.floor(ms/1000%60).toString().padStart(2,'0')}`;
const demo=[
 'Сегодня мы обсудим, как превратить устный доклад в понятную презентацию. Во время выступления важно сохранить ход мысли, а не пытаться записать каждое слово на слайд. Поэтому сначала мы выделяем законченные предложения. Затем объединяем близкие по смыслу фразы в тематические фрагменты. Такой подход помогает слушателю следить за рассказом и видеть его структуру.',
 'Теперь перейдём к архитектуре решения. Аудио обрабатывается на локальном компьютере и не покидает нашу сеть. Java-сервер принимает звук из браузера и передаёт его распознавателю речи. Отдельная модель формирует слайды из готовых фрагментов. Если генерация временно недоступна, транскрипт продолжает поступать, а презентация дополняется после восстановления модели. История изменений сохраняется в базе данных.',
 'Наконец, поговорим о проверке качества. Нам важно измерять задержку от последнего слова до появления смыслового фрагмента. Недостаточно проверить только среднее время ответа, потому что редкие длинные паузы тоже мешают выступлению. Для проверки понадобится запись реального доклада с несколькими темами. Мы сравним полученную структуру с планом выступающего и проверим восстановление после обрыва соединения.'
];
function VirtualList<T>({items,render,estimate=180}:{items:T[];render:(item:T,index:number)=>React.ReactNode;estimate?:number}){
 const ref=useRef<HTMLDivElement>(null),[follow,setFollow]=useState(true);
 const virtual=useVirtualizer({count:items.length,getScrollElement:()=>ref.current,estimateSize:()=>estimate,overscan:4});
 useEffect(()=>{if(follow&&items.length)virtual.scrollToIndex(items.length-1,{align:'end'});},[items.length,follow]);
 return <div className="list-wrap"><div ref={ref} className="scroll-list" onScroll={()=>{const el=ref.current;if(el)setFollow(el.scrollHeight-el.scrollTop-el.clientHeight<100);}}><div style={{height:virtual.getTotalSize(),position:'relative'}}>{virtual.getVirtualItems().map(row=><div key={row.key} data-index={row.index} ref={virtual.measureElement} style={{position:'absolute',top:0,left:0,width:'100%',transform:`translateY(${row.start}px)`}}>{render(items[row.index],row.index)}</div>)}</div></div>{!follow&&<button className="follow" onClick={()=>{setFollow(true);virtual.scrollToIndex(items.length-1,{align:'end'});}}><ArrowDown size={14}/>К текущему</button>}</div>;
}
function App(){
 const [state,setState]=useState<State>(initial),current=useRef(state);current.current=state;
 const [credentials,setCredentials]=useState<Credentials|null>(null),[connection,setConnection]=useState('Нет сессии'),[health,setHealth]=useState<Record<string,string>>({});
 const [error,setError]=useState(''),[recording,setRecording]=useState(false),[busy,setBusy]=useState(false),[draft,setDraft]=useState(''),[tab,setTab]=useState('chunks');
 const [metrics,setMetrics]=useState({current_ms:0,p95_ms:0}),[selected,setSelected]=useState<string|null>(null);
 const transport=useRef<Transport|undefined>(undefined),mic=useRef<Microphone|undefined>(undefined),demoStep=useRef(0);
 const chunks=Object.values(state.chunks).sort((a,b)=>a.t0-b.t0),sentences=Object.values(state.sentences);
 const deck=chunks.filter(c=>state.slides[c.id]?.title),duration=sentences.at(-1)?.t1??0;
 function onEvent(e:Event){
   if(e.type==='warning'){setError(String(e.message));return;}
   if(e.type==='metrics'){setMetrics(e as unknown as typeof metrics);return;}
   // Apply synchronously to the cursor ref: a replay can deliver many frames in one React batch.
   const next=reduce(current.current,e);current.current=next;setState(next);
 }
 function connect(c:Credentials){transport.current?.close();transport.current=new Transport(c,()=>current.current.seq,onEvent,setConnection,setError);setCredentials(c);sessionStorage.setItem('voicedeck-session',JSON.stringify(c));}
 useEffect(()=>{
   fetch('/health').then(r=>r.json()).then(setHealth).catch(()=>setError('Сервер недоступен. Проверьте запуск Java-сервиса.'));
   const saved=sessionStorage.getItem('voicedeck-session');if(saved){try{connect(JSON.parse(saved));}catch{sessionStorage.removeItem('voicedeck-session');}}
   return ()=>{transport.current?.close();void mic.current?.stop();};
 },[]);
 async function create(){
   setBusy(true);setError('');
   try{await mic.current?.stop();setRecording(false);transport.current?.close();const res=await fetch('/api/sessions',{method:'POST'});if(!res.ok)throw new Error(`Не удалось создать сессию (${res.status})`);const c=await res.json();current.current=initial();setState(current.current);demoStep.current=0;setSelected(null);connect(c);}catch(e){setError(String(e));}finally{setBusy(false);}
 }
 async function stop(){await mic.current?.stop();setRecording(false);try{transport.current?.send({type:'stop'});}catch(e){setError(String(e));}}
 async function start(){
   setBusy(true);setError('');mic.current=new Microphone();
   try{
     if(!credentials||credentials.mode!=='live'){await create();setBusy(true);}
     const deadline=Date.now()+8000;while(!transport.current?.ready&&Date.now()<deadline)await new Promise(r=>setTimeout(r,50));
     if(!transport.current?.ready||transport.current.credentials.mode!=='live')throw new Error('Нет соединения с сервером распознавания. Попробуйте ещё раз.');
     mic.current=new Microphone();
     await mic.current.start(pcm=>{try{transport.current?.audio(pcm);}catch(e){setError(String(e));void stop();}},message=>{setError(message);void stop();});setRecording(true);
   }catch(e){setError(`Не удалось начать запись: ${String(e)}`);}finally{setBusy(false);}
 }
 function send(text:string){try{transport.current?.send({type:'text',text});setDraft('');}catch(e){setError(String(e));}}
 function revise(c:Chunk,operation:string){try{transport.current?.send({type:'revise',operation,chunk_id:c.id,rev:c.rev+1,split_at:Math.floor(c.sentence_ids.length/2)});}catch(e){setError(String(e));}}
 async function download(format:string){if(!credentials)return;try{const r=await fetch(`/api/sessions/${credentials.id}/export?format=${format}`,{headers:{Authorization:`Bearer ${credentials.token}`}});if(!r.ok)throw new Error('Экспорт недоступен');const url=URL.createObjectURL(await r.blob()),a=document.createElement('a');a.href=url;a.download=`voicedeck.${format}`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(e){setError(String(e));}}
 async function remove(){if(!credentials||!window.confirm('Удалить транскрипт, фрагменты и слайды этой сессии?'))return;try{await mic.current?.stop();const r=await fetch(`/api/sessions/${credentials.id}/data`,{method:'DELETE',headers:{Authorization:`Bearer ${credentials.token}`}});if(!r.ok)throw new Error('Удаление не выполнено');transport.current?.close();sessionStorage.removeItem('voicedeck-session');setCredentials(null);current.current=initial();setState(current.current);setConnection('Нет сессии');setRecording(false);}catch(e){setError(String(e));}}
 const active=chunks.find(c=>c.id===selected)??deck.at(-1)??chunks.at(-1),slide=active?state.slides[active.id]:null;
 return <div className="app">
   <aside className="rail"><div className="brand-mark"><Radio size={24}/></div><button className="rail-active" title="Рабочая сессия"><Layers size={22}/></button><a className="rail-link" href="#/deck" title="Колода"><Presentation size={22}/></a><a className="rail-link" href="#/stage" title="Сцена"><MonitorPlay size={22}/></a><div className="rail-bottom">VD</div></aside>
   <div className="workspace">
    <header><a className="brand" href="/">voice<span>deck</span><i>LOCAL STUDIO</i></a><div className="private"><span className="dot"/>Ваши мысли остаются здесь</div><div className="avatar">Я</div></header>
    <main>
      <div className="heading"><div><div className="eyebrow">РАБОЧЕЕ ПРОСТРАНСТВО <span>/</span> НОВАЯ ИДЕЯ</div><h1>Говорите. Мы сохраним смысл<span>.</span></h1><p>Живая транскрипция и смысловые фрагменты — прямо во время разговора.</p></div><button className="button outline" onClick={create} disabled={busy||recording}><Plus size={17}/>Новая сессия</button></div>
      <section className="session-bar">
       <div className={`session-icon ${recording?'recording':''}`}><Mic size={24}/></div><div className="session-title"><strong>{recording?'Слушаю вас…':credentials?'Сессия открыта':'Начните с вашей идеи'}</strong><span>{credentials?`Сессия ${credentials.id.slice(0,8)} · ${time(duration)}`:'Подключите микрофон или исследуйте пример'}</span></div>
       <div className="wave" aria-hidden="true">{Array.from({length:28},(_,i)=><i key={i} style={{height:recording?`${10+(i*17%30)}px`:'5px',animationDelay:`${i*.06}s`}}/>)}</div>
       <div className="session-actions">{health.mode==='live'?<button className={`button ${recording?'stop':'primary'}`} disabled={busy} onClick={recording?stop:start}>{recording?<Square size={15}/>:<Mic size={16}/>} {recording?'Завершить запись':'Начать запись'}</button>:<button className="button primary" disabled={busy||!!credentials&&connection!=='Подключено'} onClick={()=>{if(!credentials)void create();else send(demo[demoStep.current++%demo.length]);}}><Play size={16}/>{credentials?'Следующий фрагмент':'Открыть демосессию'}</button>}<button className="button icon" title="Удалить данные сессии" disabled={!credentials||recording} onClick={remove}><Trash2 size={17}/></button></div>
      </section>
      <div className="status-bar"><span className={connection==='Подключено'?'connected':''}><span className="dot"/>{connection}</span><span>{health.mode==='live'?'Локальное распознавание':'Демонстрация · текст вместо микрофона'}</span><div className="latency"><span>Кусок <b>{metrics.current_ms} мс</b></span><span>p95 <b>{metrics.p95_ms} мс</b></span><span className="mode-tag">{health.storage==='postgres'?'POSTGRESQL':'ПАМЯТЬ · БЕЗ СОХРАНЕНИЯ'}</span></div></div>
      {error&&<div className="notice" role="alert">{error}<button onClick={()=>setError('')} aria-label="Закрыть сообщение">×</button></div>}
      <nav className="mobile-tabs">{[['transcript','Транскрипт'],['chunks','Фрагменты'],['deck','Макеты']].map(([id,title])=><button key={id} className={tab===id?'active':''} onClick={()=>setTab(id)}>{title}</button>)}</nav>
      <div className="panes">
       <section className={`pane transcript ${tab==='transcript'?'mobile-active':''}`}><div className="pane-heading"><FileText size={18}/><h2>Транскрипт</h2><span className="count">{sentences.length}</span></div><div className="pane-subtitle">Ваш рассказ, слово за словом</div>
        {sentences.length?<VirtualList items={sentences} estimate={120} render={s=><div className="sentence"><time>{time(s.t0)}</time><p>{s.text}</p></div>}/>:<div className="empty"><div className="empty-icon"><FileText size={28}/></div><h3>Здесь появится ваш голос</h3><p>Речь превращается в текст,<br/>пока вы продолжаете говорить.</p></div>}
        {state.partial&&<p className="partial">{state.partial}<span>▍</span></p>}
        {health.mode!=='live'&&<form className="composer" onSubmit={e=>{e.preventDefault();send(draft);}}><label htmlFor="draft">ПОПРОБУЙТЕ СВОЙ ТЕКСТ</label><textarea id="draft" value={draft} onChange={e=>setDraft(e.target.value)} placeholder="Вставьте фрагмент выступления…" maxLength={16000}/><button className="button" disabled={!draft.trim()||!credentials||connection!=='Подключено'}>В поток <ArrowRight size={15}/></button></form>}
       </section>
       <section className={`pane chunks ${tab==='chunks'?'mobile-active':''}`}><div className="pane-heading"><Layers size={18}/><h2>Смысловые фрагменты</h2><span className="count">{chunks.length}</span></div><div className="pane-subtitle">Из потока речи — в структуру мысли</div>
        {chunks.length?<VirtualList items={chunks} estimate={310} render={(c,i)=><article className={`chunk-card ${c.status} ${selected===c.id?'selected':''}`} onClick={()=>setSelected(c.id)}><div className="card-top"><span>ФРАГМЕНТ {String(i+1).padStart(2,'0')}</span><time>{time(c.t0)} — {time(c.t1)}</time></div><p>{c.text}</p><div className="chunk-footer"><span className="badge">{c.status==='confirmed'?<Check size={12}/>:<span className="tiny-dot"/>}{c.status==='confirmed'?'Подтверждён':'Уточняется'}</span><span>{c.sentence_ids.length} предл. · v{c.rev}</span></div><div className="revision-actions"><button title="Подтвердить границу" onClick={e=>{e.stopPropagation();revise(c,'confirm');}}><Check size={13}/>Подтвердить</button><button disabled={c.sentence_ids.length<2} title="Разделить пополам по предложениям" onClick={e=>{e.stopPropagation();revise(c,'split');}}><Scissors size={13}/></button><button disabled={i===chunks.length-1} title="Объединить со следующим" onClick={e=>{e.stopPropagation();revise(c,'merge');}}><Combine size={13}/></button></div></article>}/>:<div className="empty"><div className="empty-icon"><Layers size={28}/></div><h3>Одна мысль — один фрагмент</h3><p>Законченные идеи соберутся<br/>в последовательную историю.</p><div className="skeleton-card"><i/><i/><i/></div></div>}
        <div className="pane-note"><span className="tiny-dot"/>Границы можно уточнить в течение 3 минут</div>
       </section>
       <section className={`pane deck ${tab==='deck'?'mobile-active':''}`}><div className="pane-heading"><Presentation size={19}/><h2>Макеты по смыслу</h2><span className="count">{deck.length}</span><button className="small-icon" title="Скачать HTML-презентацию" disabled={!deck.length} onClick={()=>download('html')}><Download size={17}/></button></div><div className="pane-subtitle">Лёгкое превью идеи. Генерация презентации — позже.</div>
        <div className="deck-content"><div className="slide-preview"><div className="slide-label">VOICEDECK <span>01 / {String(Math.max(1,deck.length)).padStart(2,'0')}</span></div>{slide?.title?<><h3>{slide.title}</h3><ul>{slide.bullets.map((b,i)=><li key={i}>{b}</li>)}</ul></>:slide?.source==='quota'?<><div className="slide-line"/><h3 className="quota-title">Пропущено по квоте</h3><p>Не более одного слайда в 45 секунд. Содержание фрагмента сохранено в транскрипте и во фрагментах.</p></>:<><div className="slide-line"/><h3>{active?'Собираем главное':'Ваша следующая большая идея'}</h3><p>{active?active.text.slice(0,180):'Хорошая история начинается с первой мысли.'}</p></>}<div className="slide-bottom"><span/>{slide?.source==='sketch'?'МАКЕТ · ФРАГМЕНТ ИСХОДНОЙ РЕЧИ':slide?.source==='extractive-demo'?'ДЕМО · ЦИТАТЫ ИЗ ТЕКСТА':slide?.source==='quota'?'ПРОПУЩЕН ПО КВОТЕ':slide?'ЛОКАЛЬНАЯ МОДЕЛЬ':active?'ОЖИДАНИЕ ГЕНЕРАЦИИ':'МЕСТО ДЛЯ ВАШЕЙ ИСТОРИИ'}</div></div>
        {slide?.notes&&<details className="speaker-notes"><summary>Заметки докладчика <ChevronDown size={14}/></summary><p>{slide.notes}</p></details>}
        {deck.length>0&&<div className="thumbnails">{deck.map((c,i)=><button key={c.id} onClick={()=>setSelected(c.id)} className={active?.id===c.id?'active':''}><span>{String(i+1).padStart(2,'0')}</span>{state.slides[c.id].title}</button>)}</div>}
        <div className="export"><div><strong>Набросок вашей идеи</strong><p>Пока это визуальная заглушка, без генеративной модели.</p></div><button className="button outline" disabled={!deck.length} onClick={()=>download('html')}><Download size={15}/>Сохранить макеты</button><button className="text-button" disabled={!credentials} onClick={()=>download('json')}>Скачать данные JSON</button></div></div>
       </section>
      </div>
      <footer><span><span className="dot"/>Локальная обработка · Аудио не сохраняется</span><span>Голос <ArrowRight size={12}/> Смысл <ArrowRight size={12}/> Презентация</span></footer>
    </main>
   </div>
 </div>;
}
createRoot(document.getElementById('root')!).render(<Router home={<App/>}/>);


