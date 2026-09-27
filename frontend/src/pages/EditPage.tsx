import React, { useEffect, useMemo, useRef, useState } from 'react';
import {flushSync} from 'react-dom';
import {VoiceCommandQueue} from '../stage/voiceCommandQueue';
import './voiceWorkspace.css';
import {useVoiceInput} from '../stage/useVoiceInput';
import {parseDeckVoice} from '../stage/deckVoice';
import { Mic, Square, Pencil, Undo2, Copy, Trash2, Plus, Download, Send, AlertTriangle } from 'lucide-react';
import {
  DeckStateResponse, Finding, SlidePatternOption, absoluteUrl, askSlide, fileUrl, fixFindings, getDeckState,
  getSlidePatterns, patchNotes, patchSlideText, renameDeck, revertVariant, rewriteFinding, setSlidePattern, slidesAction, moveDeckElement, deckElementAction, recoverEditor,
} from '../designer/api';
import { kindLabel } from '../designer/labels';
import type {Scene} from '../designer/api';

const selectable=(scene:Scene)=>[...scene.elements.filter(e=>e.type==='text'),...scene.elements.filter(e=>e.type!=='text')];

const ASK_CHIPS = ['Короче', 'Сделай диаграммой', 'Вынести вывод в заголовок'];
const FORMATS: { ext: string; label: string }[] = [
  { ext: 'pptx', label: 'для правки в PowerPoint' },
  { ext: 'pdf', label: 'для рассылки' },
  { ext: 'html', label: 'для показа в браузере' },
];

export default function EditPage({ deckId, variant, onVariantChange }: { deckId: string; variant: string; onVariantChange?: (variant: string) => void }) {
  const [state, setState] = useState<DeckStateResponse | null>(null);
  const [index, setIndex] = useState(0);
  const [activeEl, setActiveEl] = useState<string | null>(null);
  const [editingEl, setEditingEl] = useState<string | null>(null);
  const [draftText, setDraftText] = useState('');
  const [ask, setAsk] = useState('');
  const [commandDraft,setCommandDraft]=useState('');
  const [notesDraft, setNotesDraft] = useState('');
  const [downloadOpen, setDownloadOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [titleDraft, setTitleDraft] = useState('');
  const [error, setError] = useState('');
  const operation = useRef(false);
  const epoch=useRef(0), blocked=useRef(false);
  const [needsRecovery,setNeedsRecovery]=useState(false),[recovering,setRecovering]=useState(false);
  const [elapsed,setElapsed]=useState(0);
  const [pending,setPending]=useState(0);
  useEffect(()=>{if(!pending){setElapsed(0);return;}const started=Date.now();const timer=setInterval(()=>setElapsed(Math.floor((Date.now()-started)/1000)),1000);return()=>clearInterval(timer);},[pending>0]);
  const queue=useRef(new VoiceCommandQueue(setPending));
  const mutations=useRef(new VoiceCommandQueue());
  const commandHandler=useRef<(raw:string)=>Promise<void>>(async()=>{});
  const lastMove=useRef<{dx:number;dy:number;align?:'left'|'right'|'top'|'bottom'|'center'}|null>(null);
  const dictation = useRef<{slide:number;id:string}|null>(null);
  const [waitingText,setWaitingText]=useState(false);
  const [previewVersion,setPreviewVersion]=useState(0);
  const [livePreview,setLivePreview]=useState<{key:string;html:string}|null>(null);
  const [previewError,setPreviewError]=useState('');
  const [previewLoaded,setPreviewLoaded]=useState('');
  const [voiceNotice,setVoiceNotice]=useState('Выберите текст на слайде или скажите «Выбери элемент два».');
  const [confirmDelete,setConfirmDelete]=useState<number|null>(null);

  useEffect(() => { getDeckState(deckId).then(setState).catch(e => setError(String(e))); }, [deckId]);
  useEffect(()=>{blocked.current=false;setNeedsRecovery(false);setRecovering(false);setBusy(false);operation.current=false;dictation.current=null;lastMove.current=null;return()=>{epoch.current++;queue.current.reset();mutations.current.reset();};},[deckId,variant]);

  const active = state?.variants[variant];
  const scenes = useMemo(() => active?.scenes ?? [], [active]);
  const scene = scenes[index];
  const previewKey=`${deckId}/${variant}/${scene?.slide_id}`;
  const previewRequestKey=`${previewKey}/${previewVersion}`;
  useEffect(()=>{
    if(!scene)return;
    setPreviewError('');
    const controller=new AbortController();
    fetch(absoluteUrl(`/decks/${deckId}/${variant}/slides/${index+1}/live?v=${previewVersion}`),{signal:AbortSignal.any([controller.signal,AbortSignal.timeout(10000)])})
      .then(r=>{if(!r.ok)throw Error('Не удалось загрузить живой слайд');return r.text();})
      .then(html=>{if(!controller.signal.aborted)setLivePreview({key:previewRequestKey,html});}).catch(e=>{if(!controller.signal.aborted)setPreviewError('Живой предпросмотр не загрузился. Показана последняя сохранённая картинка.');});
    return()=>controller.abort();
  },[previewKey,previewVersion,index]);
  const deckTitle = active?.plan?.title ?? state?.plan?.title ?? '';
  const freshImage=(url:string)=>`${absoluteUrl(url)}${url.includes('?')?'&':'?'}edit=${previewVersion}`;
  const findingsBySlide = useMemo(() => {
    const map = new Map<string, Finding[]>();
    for (const f of active?.findings ?? []) map.set(f.slide_id, [...(map.get(f.slide_id) ?? []), f]);
    return map;
  }, [active]);
  const sceneFindings = scene ? findingsBySlide.get(scene.slide_id) ?? [] : [];
  const [patterns, setPatterns] = useState<SlidePatternOption[]>([]);

  const planNotes = active?.plan?.slides[index]?.notes ?? '';
  useEffect(() => { setNotesDraft(planNotes); setActiveEl(id => scene?.elements.some(e => e.id === id) ? id : null); setEditingEl(null); }, [scene?.slide_id, planNotes]);
  useEffect(() => {
    if (!scene) return;
    getSlidePatterns(deckId, variant, index + 1).then(setPatterns).catch(() => setPatterns([]));
  }, [deckId, variant, index, scene?.pattern_id]);

  async function refresh() { const version=epoch.current;const next=await getDeckState(deckId);if(version!==epoch.current)return;flushSync(()=>{setState(next);setPreviewVersion(v=>v+1);}); }
  async function recover(){
    if(recovering)return;
    epoch.current++;blocked.current=true;setRecovering(true);setNeedsRecovery(true);
    queue.current.reset();mutations.current.reset();dictation.current=null;lastMove.current=null;
    setWaitingText(false);setConfirmDelete(null);setBusy(false);operation.current=false;
    setVoiceNotice('Сверяю сохранённый документ и останавливаю старые команды…');
    try{
      await recoverEditor(deckId,variant);await refresh();blocked.current=false;setNeedsRecovery(false);setError('');
      setVoiceNotice('Редактор готов. Проверьте последнюю правку на слайде; при необходимости скажите «Отмени».');
    }catch(e){setError(`Связь не восстановлена: ${String(e)}. Нажмите «Восстановить управление» повторно.`);}
    finally{setRecovering(false);}
  }
  async function guard(fn: () => Promise<unknown>) {
    const version=epoch.current;
    if(blocked.current)return false;
    let saved=false;
    await mutations.current.enqueue(async()=>{
    if(version!==epoch.current||blocked.current)return;
    operation.current=true;
    setBusy(true); setError('');
    try { await fn(); if(version!==epoch.current)return;await refresh();if(version!==epoch.current)return;setVoiceNotice('Правка сохранена. Экспорт обновляется в фоне.'); saved=true; }
    catch (e) { if(version!==epoch.current)return;queue.current.clear();blocked.current=true;setNeedsRecovery(true);setError(`Команда не завершилась: ${String(e)}. Нажмите «Восстановить управление», чтобы сверить документ. Повторять правку пока не нужно.`); }
    finally { if(version===epoch.current){setBusy(false);operation.current=false;} }
    });
    return saved;
  }

  function voiceCommand(raw:string):Promise<void>{
    if(/^(стоп|остановись|восстанови управление|сбрось очередь)[.!]?$/i.test(raw.trim()))return recover();
    if(blocked.current){setVoiceNotice('Нажмите «Восстановить управление» или скажите «Стоп».');return Promise.resolve();}
    const version=epoch.current;
    return queue.current.enqueue(async()=>{const started=performance.now();await commandHandler.current(raw);if(version===epoch.current)setLatency(Math.round(performance.now()-started));}).catch(e=>{if(version===epoch.current)setError(String(e));});
  }
  const [latency,setLatency]=useState<number|null>(null);
  async function executeVoice(raw:string){
    if(!scene)return;
    if(dictation.current){
      const bound=dictation.current;
      if(/^(стоп|отмена|отмени)[.!]?$/i.test(raw.trim())){dictation.current=null;setWaitingText(false);setVoiceNotice('Ввод текста отменён');return;}
      if(bound.slide!==index+1||bound.id!==activeEl){dictation.current=null;setWaitingText(false);setVoiceNotice('Выбор изменился. Скажите «Измени текст» для нового элемента.');return;}
      const saved=await guard(()=>patchSlideText(deckId,variant,bound.slide,bound.id,raw.trim()));
      if(saved){dictation.current=null;flushSync(()=>setWaitingText(false));}return;
    }
    if(confirmDelete!==null){if(/^да[.!]?$/i.test(raw.trim())){const n=confirmDelete;setConfirmDelete(null);const saved=await guard(()=>slidesAction(deckId,variant,{action:'delete',index:n}));if(saved)setIndex(i=>Math.max(0,i-1));return;}if(/^(нет|отмена|стоп)[.!]?$/i.test(raw.trim())){setConfirmDelete(null);return;}}
    let resolved=parseDeckVoice(raw);setVoiceNotice(raw);
    if(resolved.kind==='repeat'){if(!lastMove.current){setVoiceNotice('Сначала переместите выбранный объект.');return;}resolved={kind:'move',...lastMove.current,dx:lastMove.current.dx*resolved.factor,dy:lastMove.current.dy*resolved.factor};}
    const a=resolved;
    if(a.kind==='cancel'){setVoiceNotice(busy?'Правка уже сохраняется на сервере. После завершения её можно отменить.':'Ожидание команды');setConfirmDelete(null);return;}
    if(a.kind==='unknown'){setVoiceNotice('Не понял выбор. Скажите «Выбери один», «Выбери заголовок» или «Слайд два».');return;}
    if(a.kind==='next'||a.kind==='previous'||a.kind==='select'){const next=a.kind==='select'?a.number-1:index+(a.kind==='next'?1:-1);if(next<0||next>=scenes.length){setVoiceNotice(`В презентации ${scenes.length} слайдов. Сейчас слайд ${index+1}.`);return;}lastMove.current=null;flushSync(()=>{setActiveEl(null);setIndex(next);});setVoiceNotice(`Открыт слайд ${next+1} из ${scenes.length}.`);return;}
    const target=a.slide??index+1;
    if(target<1||target>scenes.length){setVoiceNotice(`Слайда ${target} нет. В презентации ${scenes.length} слайдов.`);return;}
    const targetScene=scenes[target-1];
    if(a.kind==='deleteElement'||a.kind==='duplicateElement'||a.kind==='style'){
      if(!activeEl||!targetScene.elements.some(e=>e.id===activeEl)){setVoiceNotice('Сначала выберите объект по номеру.');return;}
      const action=a.kind==='style'?'style':a.kind==='deleteElement'?'delete':'duplicate';
      const saved=await guard(()=>deckElementAction(deckId,variant,target,{action,element_id:activeEl,...(a.kind==='style'?{scale:a.scale,size_pt:a.size_pt,color:a.color}:{})}));
      if(saved&&action==='delete'){lastMove.current=null;flushSync(()=>setActiveEl(null));}return;
    }
    if(a.kind==='move'){
      if(!activeEl||!targetScene.elements.some(e=>e.id===activeEl)){setVoiceNotice('Выберите элемент: «Выбери один», затем «Вправо на двадцать».');return;}
      const movement=a;const saved=await guard(()=>moveDeckElement(deckId,variant,target,activeEl,movement.dx,movement.dy,movement.align));if(saved)lastMove.current=movement;return;
    }
    if(a.slide)flushSync(()=>setIndex(target-1));
    if(a.kind==='element'||a.kind==='title'){const elements=selectable(targetScene);const el=a.kind==='title'?elements.find(e=>/title|heading|заголовок/i.test(e.role)):elements[a.number-1];if(el){lastMove.current=null;flushSync(()=>setActiveEl(el.id));setVoiceNotice(`Слайд ${target}: выбран элемент ${elements.indexOf(el)+1}.`);}else setVoiceNotice(`Слайд ${target}: ${a.kind==='title'?'заголовок не найден':`элемента ${a.number} нет`}.`);return;}
    if(a.kind==='addElement'){
      const type=a.elementType??'text';
      if(type!=='title'&&type!=='text'&&type!=='shape'){setVoiceNotice('Прямое добавление пока поддерживает текст, заголовок и фигуру. Для картинки, таблицы и диаграммы используйте генерацию слайда.');return;}
      let addedId:string|undefined;
      const saved=await guard(async()=>{const result=await deckElementAction(deckId,variant,target,{action:'add',element_type:type,text:a.text||'Новый текст'});addedId=result.scenes[target-1].elements.at(-1)?.id;});
      if(saved&&addedId){flushSync(()=>setActiveEl(addedId!));lastMove.current=null;}return;
    }
    if(a.kind==='delete'){setConfirmDelete(index+1);setVoiceNotice('Удалить текущий слайд? Скажите «Да» или «Нет».');return;}
    if(a.kind==='text'||a.kind==='appendText'||a.kind==='textStart'){
      const el=a.elementNumber!==undefined?selectable(targetScene)[a.elementNumber-1]:targetScene.elements.find(e=>e.id===activeEl&&e.type==='text');
      if(!el||el.type!=='text'){setVoiceNotice('Сначала выберите текстовый элемент: «Выбери один».');return;}
      flushSync(()=>setActiveEl(el.id));
      if(a.kind==='textStart'){dictation.current={slide:target,id:el.id};setWaitingText(true);setVoiceNotice('Скажите новый текст одной фразой. «Стоп» — отменить.');return;}
      await guard(()=>patchSlideText(deckId,variant,target,el.id,a.kind==='appendText'?`${el.text.trimEnd()} ${a.text}`:a.text));return;
    }
    if(a.kind==='pattern'){const p=patterns[a.number-1];if(p)await guard(()=>setSlidePattern(deckId,variant,index+1,p.pattern_id));else setVoiceNotice('Такого образца нет');return;}
    if(a.kind==='undo'){await guard(()=>revertVariant(deckId,variant));return;}
    if(a.kind==='add'||a.kind==='copy'){const action=a.kind;await guard(()=>slidesAction(deckId,variant,{action,index:index+1}));return;}
    if(a.kind==='ask')await guard(()=>askSlide(deckId,variant,index+1,a.text));
  }
  commandHandler.current=executeVoice;
  const voice=useVoiceInput(raw=>void voiceCommand(raw));
  useEffect(()=>{if(scenes.length)setIndex(i=>Math.min(i,scenes.length-1));},[scenes.length]);

  if (!scene) return <div className="edit-shell"><div className="page-loading">{error || 'Загрузка'}</div></div>;

  return <div className="edit-shell">
    <div className="edit-topbar">
      <div className="edit-title-row">
        {renaming ? <input className="edit-title-input" aria-label="Название презентации" autoFocus value={titleDraft}
          onChange={e => setTitleDraft(e.target.value)}
          onKeyDown={e => { if (e.key === 'Escape') setRenaming(false); if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
          onBlur={() => { setRenaming(false); const t = titleDraft.trim(); if (t && t !== deckTitle) void guard(() => renameDeck(deckId, t)); }}/>
          : <h1 className="edit-title">{deckTitle}</h1>}
        <button type="button" className="button-icon" aria-label="Переименовать" title="Переименовать"
          onClick={() => { setTitleDraft(deckTitle); setRenaming(true); }}><Pencil size={20} strokeWidth={1.5}/></button>
      </div>
      <div role="group" aria-label="Варианты вёрстки" className="edit-variants">
        {['a', 'b', 'c'].map(v => {
          const has = state?.variants[v]?.status === 'done';
          return <a key={v} className={`edit-variant-tab ${v === variant ? 'active' : ''}`}
            href={`#/decks/${deckId}/edit/${v}`} onClick={onVariantChange ? e => { e.preventDefault(); if (has) onVariantChange(v); } : undefined} aria-current={v === variant ? 'page' : undefined}
            title={v === 'a' || !has ? undefined : 'Проверки смысла у этого варианта не было'}>
            Вариант {v === 'a' ? 1 : v === 'b' ? 2 : 3}
          </a>;
        })}
      </div>
      <div style={{ display: 'flex', gap: 8, position: 'relative' }}>
        <button type="button" className="button primary" aria-label="Скачать: pptx, pdf или html" onClick={() => setDownloadOpen(v => !v)}>
          <Download size={18} strokeWidth={1.5}/>Скачать
        </button>
        {downloadOpen && <ul role="menu" aria-label="Формат файла" className="download-menu">
          {FORMATS.map(f => <li key={f.ext} role="menuitem" tabIndex={0}>
            <a className="download-item" href={fileUrl(deckId, variant, `deck.${f.ext}`)} download onClick={() => setDownloadOpen(false)}>
              <span className="download-item-ext">{f.ext}</span><span className="download-item-sub">{f.label}</span>
            </a>
          </li>)}
        </ul>}
      </div>
    </div>
    {error && <div className="notice" role="alert">{error}<button onClick={() => setError('')} aria-label="Закрыть сообщение">×</button></div>}
    <div className="deck-voice-bar">
      <div style={{display:'flex',alignItems:'center',gap:12}}>
        <button className="button" disabled={recovering} onClick={()=>void recover()}>{recovering?'Восстанавливаю…':pending?'Остановить и восстановить':'Восстановить управление'}</button>
        <button className="button" disabled={voice.starting} onClick={()=>void voice.restart()}>Переподключить микрофон</button>
        <span role="status">{recovering?'Проверяю состояние сервера':needsRecovery?'Нужна проверка последней правки':pending?`Обработка · ${elapsed} с${elapsed>=5?' · можно остановить кнопкой слева':''}`:'Очередь свободна'}</span>
      </div>
      {waitingText && <div role="status">Диктуйте новый текст выбранного элемента. <button className="button" onClick={()=>{dictation.current=null;setWaitingText(false);setVoiceNotice('Ввод текста отменён');}}>Отменить диктовку</button></div>}
      <div aria-live="polite">Слайд {index+1} из {scenes.length} · {activeEl ? `Выбран элемент ${selectable(scene).findIndex(e=>e.id===activeEl)+1}` : 'Элемент не выбран'} · {pending ? `Команд в обработке: ${pending}` : 'Готов к команде'}{latency!==null&&` · Последняя команда: ${latency} мс`}</div>
      {voice.recording && <div>Микрофон: {voice.device} · <meter aria-label="Уровень микрофона" min={0} max={100} value={voice.level}/> {voice.level>1?'Звук поступает':'Тихо — проверьте выбранный микрофон'}</div>}
      {voice.heard && <div>Распознано: «{voice.heard}»</div>}
      {activeEl && <div className="component-toolbar" aria-label="Перемещение выбранного элемента">{[['←','Влево'],['↑','Вверх'],['↓','Вниз'],['→','Вправо'],['В центр','В центр']].map(([label,command])=><button key={command} className="button" disabled={busy||waitingText} aria-label={`Переместить ${command.toLowerCase()}`} onClick={()=>void voiceCommand(command)}>{label}</button>)}<span>Шаг 20 пикселей · голосом: «Вправо на двадцать», «В центр»</span></div>}
      <div className="deck-voice-row">
      <button className={`button deck-mic-button ${voice.recording ? 'is-recording' : ''}`} disabled={voice.starting} onClick={()=>void(voice.recording?voice.stop():voice.start())}>{voice.recording ? <Square size={16}/> : <Mic size={16}/>}{voice.recording?'Остановить микрофон':'Редактировать голосом'}</button>
      <span className="deck-voice-status" aria-live="polite"><i className={`deck-connection-dot ${voice.recording ? 'live' : ''}`}/>{voice.error||voice.partial||voiceNotice}{voice.connection ? ` · ${voice.connection}` : ''}</span></div>
      <details><summary>Что можно сказать?</summary><p>«Следующий слайд» · «Выбери элемент два» · «Замени текст на …» · «Сократи заголовок» · «Выбери образец два» · «Добавь слайд» · «Отмени»</p></details>
      <form onSubmit={e=>{e.preventDefault();if(commandDraft.trim()){void voiceCommand(commandDraft);setCommandDraft('');}}} style={{display:'flex',gap:8}}><input aria-label="Команда редактирования" value={commandDraft} onChange={e=>setCommandDraft(e.target.value)} placeholder="Команду можно ввести текстом"/><button className="button">Выполнить</button></form>
      {confirmDelete!==null&&<div>Удалить слайд {confirmDelete}? <button className="button" onClick={()=>void voiceCommand('да')}>Да, удалить слайд</button><button className="button" onClick={()=>setConfirmDelete(null)}>Нет</button></div>}
    </div>
    <div className="edit-body">
      <aside className="edit-rail" aria-label="Слайды">
        {scenes.map((s, i) => {
          const fs = findingsBySlide.get(s.slide_id) ?? [];
          const hasError = fs.some(f => f.severity === 'error');
          return <a key={s.slide_id} className={`edit-thumb-row ${i === index ? 'current' : ''}`}
            aria-label={`Слайд ${i + 1}`} aria-current={i === index ? 'true' : undefined}
            href={`#slide-${i + 1}`} onClick={e => { e.preventDefault(); setIndex(i); }}>
            <span className="edit-thumb-num">{i + 1}</span>
            <span className="edit-thumb-wrap">
              {active?.slide_images?.[i] ? <img className="edit-thumb" src={freshImage(active.slide_images[i])} alt=""/> : <div className="edit-thumb"/>}
              {fs.length > 0 && <span className={`edit-thumb-badge ${hasError ? 'error' : ''}`}>
                {hasError && <AlertTriangle size={12} strokeWidth={1.5}/>}{fs.length}
              </span>}
            </span>
          </a>;
        })}
        <button type="button" className="edit-add-slide" disabled={busy}
          onClick={() => guard(() => slidesAction(deckId, variant, { action: 'add', index }))}>
          <Plus size={16} strokeWidth={1.5}/>Слайд
        </button>
      </aside>
      <div className="edit-canvas">
        <div className="edit-slide-stage">
          {previewLoaded!==previewRequestKey&&<div style={{position:'absolute',inset:0}}>
            {active?.slide_images?.[index]?<img className="edit-slide-img" src={absoluteUrl(active.slide_images[index])} alt={`Слайд ${index+1}: сохранённый предпросмотр`}/>:<div role="status">Загружаю слайд…</div>}
          </div>}
          {livePreview?.key===previewRequestKey&&<iframe key={previewRequestKey} title="Живой слайд" className="edit-slide-img" sandbox="" onLoad={()=>setPreviewLoaded(previewRequestKey)} style={{position:'absolute',inset:0,width:'100%',height:'100%',border:0,pointerEvents:'none',visibility:previewLoaded===previewRequestKey?'visible':'hidden'}} srcDoc={livePreview.html}/>}
          {selectable(scene).map((el,elementIndex) => {
            const [x, y, w, h] = el.box;
            const style: React.CSSProperties = { left: `${x * 100}%`, top: `${y * 100}%`, width: `${w * 100}%`, height: `${h * 100}%` };
            return <div key={el.id} className={`edit-el-box ${activeEl === el.id ? 'active' : ''}`} style={style}
              onClick={() => setActiveEl(el.id)}>
              <span style={{position:'absolute',top:0,left:0,background:'var(--accent)',color:'white',padding:'2px 6px',borderRadius:4}}>{elementIndex+1}</span>
              {activeEl === el.id && editingEl !== el.id && <div className="edit-el-toolbar" role="toolbar" aria-label="Текст на слайде"
                style={{ left: 0, top: '100%', marginTop: 4 }}>
                {el.type==='text'&&<button type="button" className="button-icon" aria-label="Править текст" title="Править текст"
                  onClick={() => { setEditingEl(el.id); setDraftText(el.text); }}><Pencil size={20} strokeWidth={1.5}/></button>}
                <button type="button" className="button-icon" aria-label="Вернуть как было" title="Вернуть как было" disabled={busy}
                  onClick={() => guard(() => revertVariant(deckId, variant))}><Undo2 size={20} strokeWidth={1.5}/></button>
              </div>}
              {editingEl === el.id && <div className="edit-el-edit" style={{ position: 'absolute', left: 0, top: '100%', marginTop: 4, zIndex: 6 }}
                onClick={e => e.stopPropagation()}>
                <textarea value={draftText} onChange={e => setDraftText(e.target.value)} autoFocus/>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button type="button" className="button primary small" disabled={busy}
                    onClick={() => guard(() => patchSlideText(deckId, variant, index + 1, el.id, draftText)).then(() => setEditingEl(null))}>Сохранить</button>
                  <button type="button" className="button small" onClick={() => setEditingEl(null)}>Отмена</button>
                </div>
              </div>}
            </div>;
          })}
        </div>
        {previewError&&<div role="alert">{previewError} <button className="button" onClick={()=>setPreviewVersion(v=>v+1)}>Повторить загрузку слайда</button></div>}
        <div className="edit-notes">
          <label htmlFor="notes">Заметки докладчика</label>
          <textarea id="notes" rows={2} value={notesDraft} onChange={e => setNotesDraft(e.target.value)}
            onBlur={() => { if (notesDraft !== planNotes) void guard(() => patchNotes(deckId, variant, index + 1, notesDraft)); }}/>
        </div>
      </div>
      <aside className="edit-panel" aria-label={`Слайд ${index + 1}`}>
        <div className="edit-panel-head">
          <h2>Слайд {index + 1}</h2>
          <div className="edit-panel-head-actions">
            <button type="button" className="button-icon" aria-label="Копия слайда" title="Копия слайда" disabled={busy}
              onClick={() => guard(() => slidesAction(deckId, variant, { action: 'copy', index:index+1 }))}><Copy size={20} strokeWidth={1.5}/></button>
            <button type="button" className="button-icon" aria-label="Удалить слайд" title="Удалить слайд" disabled={busy}
              onClick={() => setConfirmDelete(index+1)}><Trash2 size={20} strokeWidth={1.5}/></button>
          </div>
        </div>
        <div>
          <div className="panel-section-head"><h3>Образец</h3></div>
          <div className="pattern-grid">
            {patterns.map((p, patternIndex) => <button key={p.pattern_id} type="button" className={`pattern-item ${p.current ? 'active' : ''}`}
              aria-pressed={p.current} aria-label={`Образец: ${kindLabel(p.kind)}`} disabled={busy}
              onClick={() => !p.current && guard(() => setSlidePattern(deckId, variant, index + 1, p.pattern_id))}>
              {p.preview ? <img src={absoluteUrl(p.preview)} alt=""/> : <div style={{ width: 148, height: 83, background: 'var(--surface-2)', borderRadius: 6 }}/>}
              <span>{patternIndex+1}. {p.current ? `Текущий: ${kindLabel(p.kind).toLowerCase()}` : kindLabel(p.kind)}</span>
            </button>)}
          </div>
        </div>
        <div className="ask-block">
          <label htmlFor="ask">Попросить агента</label>
          <div className="ask-row">
            <input id="ask" className="ask-input" type="text" value={ask} onChange={e => setAsk(e.target.value)}
              placeholder="Например: убери вводную фразу из заголовка"/>
            <button type="button" className="ask-send" aria-label="Отправить агенту" disabled={!ask.trim() || busy}
              onClick={() => guard(() => askSlide(deckId, variant, index + 1, ask)).then(() => setAsk(''))}>
              <Send size={18} strokeWidth={1.5}/>
            </button>
          </div>
          <div className="chip-row">
            {ASK_CHIPS.map(c => <button key={c} type="button" className="chip" disabled={busy}
              onClick={() => guard(() => askSlide(deckId, variant, index + 1, c))}>{c}</button>)}
          </div>
        </div>
        <div>
          <div className="panel-section-head"><h3>Замечания проверки</h3><span className="findings-count">{sceneFindings.length}</span></div>
          <ul className="findings-list">
            {sceneFindings.map(f => <li key={f.id} className="finding-item">
              <AlertTriangle size={18} strokeWidth={1.5} color={f.severity === 'error' ? 'var(--danger)' : 'var(--text-muted)'}/>
              <span className="finding-body">
                <span className={`finding-kind ${f.severity}`}>{f.severity === 'error' ? 'Ошибка' : 'Предупреждение'}</span>
                {f.message}
              </span>
              {f.fixable
                ? <button type="button" className="button small" disabled={busy}
                  onClick={() => guard(() => fixFindings(deckId, variant, [f.id]))}>Исправить</button>
                : <button type="button" className="button small" disabled={busy}
                  onClick={() => guard(() => rewriteFinding(deckId, variant, f.id))}>Переписать</button>}
            </li>)}
          </ul>
        </div>
      </aside>
    </div>
  </div>;
}





