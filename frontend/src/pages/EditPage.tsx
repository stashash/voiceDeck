import React, { useEffect, useMemo, useRef, useState } from 'react';
import {flushSync} from 'react-dom';
import {VoiceCommandQueue} from '../stage/voiceCommandQueue';
import {deletionStillValid,type DeleteConfirmation,type VoicePhrase} from '../stage/voiceContext';
import {editDictation,type DictationDraft} from '../stage/voiceDictation';
import {voiceRewriteConstraints} from '../stage/voiceRewriteConstraints';
import './voiceWorkspace.css';
import {useVoiceInput} from '../stage/useVoiceInput';
import {joinPrefix,type PendingPrefix} from '../stage/voicePrefix';
import {parseVoiceOperation,VOICE_OPERATIONS} from '../stage/voiceOperations';
import {resolveVoiceSelection} from '../stage/voiceSelection';
import {planVoiceBatch} from '../stage/voiceBatch';
import {executeDeckVoice,deckSelectable,type DeckVoiceResult} from '../stage/deckVoiceExecutor';
import {deckRewriteTarget} from '../stage/deckVoiceTarget';
import {editorRequest} from '../stage/editorRequest';
import {prepareEditorModel} from '../stage/editorModel';
import { Mic, Square, Pencil, Undo2, Copy, Trash2, Plus, Download, Send, AlertTriangle, RefreshCw, ArrowLeft, ArrowRight, ArrowUp, ArrowDown, AlignCenter, X, Check, TextCursorInput } from 'lucide-react';
import {
  DeckStateResponse, Finding, SlidePatternOption, absoluteUrl, askSlide, fileUrl, fixFindings, getDeckState,
  getSlidePatterns, patchNotes, patchSlideText, renameDeck, revertVariant, rewriteFinding, setSlidePattern, slidesAction, recoverEditor, rewriteDeckVoice, commitDeckDictation, commitVoiceBatch,
} from '../designer/api';
import { kindLabel } from '../designer/labels';

const selectable=deckSelectable;

const ASK_CHIPS = ['Короче', 'Сделай диаграммой', 'Вынести вывод в заголовок'];
const FORMATS: { ext: string; label: string }[] = [
  { ext: 'pptx', label: 'для правки в PowerPoint' },
  { ext: 'pdf', label: 'для рассылки' },
  { ext: 'html', label: 'для показа в браузере' },
];

export default function EditPage({ deckId, variant, onVariantChange }: { deckId: string; variant: string; onVariantChange?: (variant: string) => void }) {
  const [state, setState] = useState<DeckStateResponse | null>(null);
  const [index, setIndex] = useState(0);
  const [selectedIds,setSelectedIds]=useState<string[]>([]);
  const [candidateIds,setCandidateIds]=useState<string[]>([]);
  const activeEl=selectedIds.length===1?selectedIds[0]:null;
  function setActiveEl(id:string|null){setSelectedIds(id?[id]:[]);setCandidateIds([]);}
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
  const manualContext=useRef(0);
  const manualAudioEpoch=useRef(0);
  const commandContextKey=()=>`${deckId}/${variant}/${manualContext.current}`;
  const voiceContextKey=()=>`${commandContextKey()}/${manualAudioEpoch.current}`;
  const [needsRecovery,setNeedsRecovery]=useState(false),[recovering,setRecovering]=useState(false);
  const [elapsed,setElapsed]=useState(0);
  const [pending,setPending]=useState(0);
  useEffect(()=>{if(!pending){setElapsed(0);return;}const started=Date.now();const timer=setInterval(()=>setElapsed(Math.floor((Date.now()-started)/1000)),1000);return()=>clearInterval(timer);},[pending>0]);
  const queue=useRef(new VoiceCommandQueue(setPending,{maxPending:4,maxAgeMs:2500}));
  const mutations=useRef(new VoiceCommandQueue());
  const commandHandler=useRef<(raw:string)=>Promise<void>>(async()=>{});
  const lastMove=useRef<{dx:number;dy:number;align?:'left'|'right'|'top'|'bottom'|'center'}|null>(null);
  const pendingPrefix=useRef<PendingPrefix>(null);
  const dictation = useRef<Omit<DictationDraft,'text'>|null>(null);
  const longDictation=useRef<DictationDraft|null>(null);
  const [dictationText,setDictationText]=useState('');
  const [waitingText,setWaitingText]=useState(false);
  const [previewVersion,setPreviewVersion]=useState(0);
  const [livePreview,setLivePreview]=useState<{key:string;html:string}|null>(null);
  const [previewError,setPreviewError]=useState('');
  const [previewLoaded,setPreviewLoaded]=useState('');
  const [voiceNotice,setVoiceNotice]=useState('Ожидание команды');
  const [confirmDelete,setConfirmDelete]=useState<DeleteConfirmation|null>(null);
  const [thinking,setThinking]=useState(false);
  const modelJob=useRef<{id:string;controller:AbortController}|null>(null);
  function cancelModel(){const job=modelJob.current;if(!job)return;modelJob.current=null;job.controller.abort();setThinking(false);void editorRequest(`intent/${job.id}/cancel`,{}, {timeout:2000}).catch(()=>{});}

  useEffect(() => {let cancelled=false;setState(null);getDeckState(deckId).then(next=>{if(!cancelled)setState(next);}).catch(e=>{if(!cancelled)setError(String(e));});return()=>{cancelled=true;};}, [deckId]);
  useEffect(()=>{manualContext.current++;blocked.current=false;setSelectedIds([]);setCandidateIds([]);setNeedsRecovery(false);setRecovering(false);setBusy(false);operation.current=false;dictation.current=null;longDictation.current=null;setDictationText('');setWaitingText(false);setConfirmDelete(null);lastMove.current=null;return()=>{cancelModel();epoch.current++;queue.current.reset();mutations.current.reset();};},[deckId,variant]);

  const active = state?.variants[variant];
  const scenes = useMemo(() => active?.scenes ?? [], [active]);
  const scene = scenes[index];
  useEffect(()=>{if(!confirmDelete)return;const timer=setTimeout(()=>setConfirmDelete(null),Math.max(0,confirmDelete.expiresAt-performance.now()));return()=>clearTimeout(timer);},[confirmDelete]);
  useEffect(()=>{setConfirmDelete(null);},[active?.revision]);
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
  // Картинка pptx точнее HTML-предпросмотра (значки, логотип, фоны образца). HTML нужен только, пока
  // картинки после правки ещё рисуются; готовы картинки этой правки — показываем их.
  const imageFresh=!!active?.slide_images?.[index]&&(!active?.revision||active.images_revision===active.revision);
  useEffect(()=>{
    if(!active?.revision||active.images_revision===active.revision||!active.slide_images?.length)return;
    let stopped=false,tries=0;
    const timer=setInterval(()=>{
      if(stopped||++tries>60){clearInterval(timer);return;}
      const version=epoch.current;
      getDeckState(deckId).then(next=>{
        const v=next.variants[variant];
        if(stopped||version!==epoch.current||!v||v.revision!==active.revision||v.images_revision!==v.revision)return;
        stopped=true;clearInterval(timer);setState(next);
      }).catch(()=>{});
    },2000);
    return()=>{stopped=true;clearInterval(timer);};
  },[deckId,variant,active?.revision,active?.images_revision]);
  const freshImage=(url:string)=>`${absoluteUrl(url)}${url.includes('?')?'&':'?'}edit=${previewVersion}`;
  const findingsBySlide = useMemo(() => {
    const map = new Map<string, Finding[]>();
    for (const f of active?.findings ?? []) map.set(f.slide_id, [...(map.get(f.slide_id) ?? []), f]);
    return map;
  }, [active]);
  const sceneFindings = scene ? findingsBySlide.get(scene.slide_id) ?? [] : [];
  const [patterns, setPatterns] = useState<SlidePatternOption[]>([]);

  const planNotes = active?.plan?.slides[index]?.notes ?? '';
  useEffect(() => { setNotesDraft(planNotes); setEditingEl(null); }, [scene?.slide_id, planNotes]);
  useEffect(()=>{setSelectedIds(ids=>ids.filter(id=>scene?.elements.some(e=>e.id===id)));setCandidateIds([]);},[scene?.slide_id,active?.revision]);
  useEffect(() => {
    if (!scene) return;
    getSlidePatterns(deckId, variant, index + 1).then(setPatterns).catch(() => setPatterns([]));
  }, [deckId, variant, index, scene?.pattern_id]);

  async function refresh() { const version=epoch.current;const next=await getDeckState(deckId);if(version!==epoch.current)return;flushSync(()=>{setState(next);setPreviewVersion(v=>v+1);}); }
  function cancelDictation(){dictation.current=null;longDictation.current=null;setDictationText('');setWaitingText(false);}
  function manualChange(){manualContext.current++;queue.current.clear();cancelModel();cancelDictation();setConfirmDelete(null);setCandidateIds([]);lastMove.current=null;}
  async function recover(){
    if(recovering)return;
    cancelModel();manualContext.current++;voice.invalidate();
    epoch.current++;blocked.current=true;setRecovering(true);setNeedsRecovery(true);
    queue.current.reset();mutations.current.reset();cancelDictation();lastMove.current=null;
    setWaitingText(false);setConfirmDelete(null);setBusy(false);operation.current=false;
    setVoiceNotice('Сверяю сохранённый документ и останавливаю старые команды…');
    try{
      await recoverEditor(deckId,variant);await refresh();blocked.current=false;setNeedsRecovery(false);setError('');
      setVoiceNotice('Редактор готов. Проверьте последнюю правку на слайде; при необходимости скажите «Отмени».');
    }catch(e){setError(`Связь не восстановлена: ${String(e)}. Нажмите «Восстановить управление» повторно.`);}
    finally{setRecovering(false);}
  }
  async function guard(fn: () => Promise<unknown>,fromVoice=false) {
    if(!fromVoice)manualChange();
    cancelModel();
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

  function voiceCommand(raw:string,phrase?:VoicePhrase):Promise<void>{
    if(/^(стоп|остановись|восстанови управление|сбрось очередь)[.!]?$/i.test(raw.trim()))return recover();
    const joined=joinPrefix(raw,pendingPrefix.current,performance.now());
    pendingPrefix.current=joined.pending;
    if(joined.text===null){setVoiceNotice(`${raw.trim().replace(/[.!?…]+$/,'')}…`);return Promise.resolve();}
    raw=joined.text;
    if(blocked.current){setVoiceNotice('Нажмите «Восстановить управление» или скажите «Стоп».');return Promise.resolve();}
    const version=epoch.current,context=commandContextKey(),started=performance.now();
    return queue.current.enqueue(async()=>{
      if(context!==commandContextKey()||phrase&&phrase.contextKey!==voiceContextKey()){setVoiceNotice('Выбор изменился. Команда не выполнена.');return;}
      await commandHandler.current(raw);
      if(version===epoch.current)setLatency(Math.round(performance.now()-started));
    }).catch(e=>{if(version===epoch.current)setVoiceNotice(String(e));});
  }
  function manualVoiceCommand(raw:string){manualAudioEpoch.current++;return voiceCommand(raw);}
  const [latency,setLatency]=useState<number|null>(null);
  function applyVoiceResult(result:DeckVoiceResult){
    flushSync(()=>{
      if(result.state)setState(previous=>previous?{...previous,variants:{...previous.variants,[variant]:{...result.state!,slide_images:result.state!.slide_images?.length?result.state!.slide_images:previous.variants[variant]?.slide_images}}}:previous);
      if(result.state)setPreviewVersion(v=>v+1);
      if(result.index!==undefined){setIndex(result.index);if(result.index!==index&&result.selectedId===undefined)setActiveEl(null);}
      if(result.selectedId!==undefined)setActiveEl(result.selectedId);
      if(result.dictate){const target=scenes[result.dictate.slide-1];if(target){dictation.current={...result.dictate,slideId:target.slide_id,revision:active?.revision??''};setWaitingText(true);}}
      if(result.confirmDelete!==undefined){const n=result.confirmDelete;const slide=scenes[n-1];if(slide)setConfirmDelete({deckId,variant,revision:active?.revision??'',slideId:slide.slide_id,index:n,expiresAt:performance.now()+10000});}
    });
    if(result.movement)lastMove.current=result.movement;
    else if(result.selectedId!==undefined||result.index!==undefined)lastMove.current=null;
    if(result.notice)setVoiceNotice(result.notice);
  }
  async function modelRewrite(instruction:string,explicitSlide?:number){
    if(modelJob.current){setVoiceNotice('Локальная модель занята. Быстрые команды доступны.');return;}
    const target=deckRewriteTarget(instruction,scenes,index,activeEl,explicitSlide);
    if('notice' in target){setVoiceNotice(target.notice);return;}
    const job={id:crypto.randomUUID(),controller:new AbortController()};modelJob.current=job;
    const version=epoch.current,started=performance.now();setThinking(true);setVoiceNotice('Локальная модель редактирует текст…');
    try{
      await prepareEditorModel(job.controller.signal,status=>{if(modelJob.current===job)setVoiceNotice(status.state==='ready'?'Локальная модель редактирует текст…':status.message??'Загрузка локальной модели…');});
      if(modelJob.current!==job||version!==epoch.current)return;
      const constraints=voiceRewriteConstraints(instruction);
      const result=await rewriteDeckVoice(deckId,variant,target.slide,{request_id:job.id,element_id:target.id,instruction,constraints},job.controller.signal);
      if(modelJob.current!==job||version!==epoch.current)return;
      applyVoiceResult(result);setLatency(Math.round(performance.now()-started));
    }catch(e){if(modelJob.current===job&&!job.controller.signal.aborted)setVoiceNotice(String(e));}
    finally{if(modelJob.current===job){modelJob.current=null;setThinking(false);}}
  }
  function startDictation(){
    const element=scene?.elements.find(el=>el.id===activeEl&&el.type==='text');
    if(!element){setVoiceNotice('Выберите текстовый элемент');return;}
    cancelModel();setConfirmDelete(null);dictation.current=null;
    longDictation.current={slide:index+1,slideId:scene.slide_id,id:element.id,revision:active?.revision??'',text:''};
    setDictationText('');setWaitingText(true);setVoiceNotice('Диктовка');
  }
  async function finishDictation(){
    const draft=longDictation.current;if(!draft)return;
    if(draft.slideId!==scene?.slide_id||draft.id!==activeEl||draft.revision!==(active?.revision??'')){cancelDictation();setVoiceNotice('Документ или выбор изменился. Черновик не применён.');return;}
    if(!draft.text.trim()){setVoiceNotice('Черновик пуст');return;}
    const saved=await guard(()=>commitDeckDictation(deckId,variant,draft.slide,{element_id:draft.id,text:draft.text.trim(),expected_revision:draft.revision,target_slide_id:draft.slideId}),true);
    if(saved)cancelDictation();
  }
  async function executeVoice(raw:string){
    if(!scene)return;
    if(longDictation.current){
      const change=editDictation(longDictation.current.text,raw);
      if(change.kind==='cancel'){cancelDictation();setVoiceNotice('Диктовка отменена');return;}
      if(change.kind==='finish'){await finishDictation();return;}
      if(change.text.length>12000){setVoiceNotice('Достигнут предел 12000 символов');return;}
      longDictation.current.text=change.text;setDictationText(change.text);return;
    }
    if(dictation.current){
      const bound=dictation.current;
      if(/^(стоп|отмена|отмени)[.!]?$/i.test(raw.trim())){dictation.current=null;setWaitingText(false);setVoiceNotice('Ввод текста отменён');return;}
      if(bound.slideId!==scene.slide_id||bound.slide!==index+1||bound.id!==activeEl||bound.revision!==(active?.revision??'')){dictation.current=null;setWaitingText(false);setVoiceNotice('Документ или выбор изменился. Скажите «Измени текст» для нового элемента.');return;}
      const saved=await guard(()=>commitDeckDictation(deckId,variant,bound.slide,{element_id:bound.id,text:raw.trim(),expected_revision:bound.revision,target_slide_id:bound.slideId}),true);
      if(saved){dictation.current=null;flushSync(()=>setWaitingText(false));}return;
    }
    if(/^(?:начни диктовку|режим диктовки)[.!?]?$/i.test(raw.trim())){startDictation();return;}
    if(confirmDelete!==null){
      const confirmation=confirmDelete;setConfirmDelete(null);
      if(/^да[.!]?$/i.test(raw.trim())){
        if(!deletionStillValid(confirmation,{deckId,variant,revision:active?.revision??'',slideIds:scenes.map(s=>s.slide_id)})){setVoiceNotice('Подтверждение удаления устарело. Повторите команду.');return;}
        const saved=await guard(()=>slidesAction(deckId,variant,{action:'delete',index:confirmation.index,expected_revision:confirmation.revision,target_slide_id:confirmation.slideId}),true);
        if(saved)setIndex(i=>Math.max(0,i-1));return;
      }
      if(/^(нет|отмена|стоп)[.!]?$/i.test(raw.trim()))return;
    }
    const selection=resolveVoiceSelection(raw,scene,selectedIds);
    if(selection){
      cancelModel();lastMove.current=null;
      flushSync(()=>{setSelectedIds(selection.kind==='selection'?selection.ids:[]);setCandidateIds(selection.kind==='clarify'?selection.candidateIds:[]);});
      setVoiceNotice(selection.notice);return;
    }
    let resolved=parseVoiceOperation(raw);setVoiceNotice(raw);
    if(resolved.kind==='repeat'){if(!lastMove.current){setVoiceNotice('Сначала переместите выбранный объект.');return;}resolved={kind:'move',...lastMove.current,dx:lastMove.current.dx*resolved.factor,dy:lastMove.current.dy*resolved.factor};}
    const a=resolved;
    if(a.kind==='cancel'){cancelModel();setConfirmDelete(null);return;}
    if(a.kind==='unsupported'){setVoiceNotice(a.text);return;}
    if(VOICE_OPERATIONS[a.kind].target==='single'&&selectedIds.length>1&&(!('elementNumber' in a)||a.elementNumber===undefined)){
      setVoiceNotice('Для этой команды выберите один объект');return;
    }
    if(a.kind==='ask'){void modelRewrite(a.text,a.slide);return;}
    if(a.kind==='unknown'){setVoiceNotice('Команда не распознана. Документ не изменён.');return;}
    const batchSteps=a.kind==='macro'?a.steps:a.kind==='layout'?[a]:(a.kind==='style'||a.kind==='move')&&selectedIds.length>1&&a.elementNumber===undefined?[a]:null;
    if(batchSteps){
      if('slide' in a&&a.slide!==undefined){setVoiceNotice('Групповая правка ограничена текущим слайдом');return;}
      const plan=planVoiceBatch(scene,selectedIds,batchSteps);
      if('notice' in plan){setVoiceNotice(plan.notice);return;}
      cancelModel();
      const version=epoch.current,context=commandContextKey();
      await mutations.current.enqueue(async()=>{
        if(version!==epoch.current||blocked.current||context!==commandContextKey())return;
        setBusy(true);setError('');
        try{
          const next=await commitVoiceBatch(deckId,variant,index+1,{expected_revision:active?.revision??'',target_slide_id:scene.slide_id,operations:plan.operations});
          if(version!==epoch.current)return;
          applyVoiceResult({state:next,notice:context===commandContextKey()?`Сохранено объектов: ${plan.operations.length}`:undefined});
          if(context===commandContextKey())lastMove.current=a.kind==='move'?{dx:a.dx,dy:a.dy,align:a.align}:null;
        }catch(e){
          if(version!==epoch.current)return;
          const status=(e as {status?:number}).status;
          if(status&&status>=400&&status<500){queue.current.clear();setVoiceNotice(String(e));return;}
          blocked.current=true;setNeedsRecovery(true);queue.current.clear();setError(`Не удалось подтвердить сохранение: ${String(e)}`);
        }finally{if(version===epoch.current)setBusy(false);}
      });
      return;
    }
    if(a.kind==='layout'||a.kind==='macro')return;
    cancelModel();
    const version=epoch.current,context=commandContextKey();
    await mutations.current.enqueue(async()=>{
      if(version!==epoch.current||blocked.current||context!==commandContextKey())return;
      setBusy(true);setError('');
      try{const result=await executeDeckVoice(a,{deckId,variant,scenes,index,selectedId:activeEl,patterns});if(version===epoch.current)applyVoiceResult(context===commandContextKey()?result:{state:result.state});}
      catch(e){if(version!==epoch.current)return;const status=(e as {status?:number}).status;if(status&&status>=400&&status<500){setVoiceNotice(String(e));return;}blocked.current=true;setNeedsRecovery(true);queue.current.clear();setError(`Не удалось подтвердить сохранение: ${String(e)}`);}
      finally{if(version===epoch.current)setBusy(false);}
    });
  }
  commandHandler.current=executeVoice;
  const voice=useVoiceInput((raw,phrase)=>void voiceCommand(raw,phrase),voiceContextKey);
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
            href={`#/decks/${deckId}/edit/${v}`} onClick={onVariantChange ? e => { e.preventDefault(); if (has){manualChange();onVariantChange(v);} } : undefined} aria-current={v === variant ? 'page' : undefined}
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
    <section className="deck-voice-bar voice-console" aria-label="Голосовое редактирование">
      <div className="voice-console-controls">
        <button className={`button deck-mic-button ${voice.recording?'is-recording':''}`} disabled={voice.starting||voice.stopping} onClick={()=>void(voice.recording?voice.stop():voice.start())}>
          {voice.recording?<Square size={18}/>:<Mic size={18}/>}{voice.stopping?'Завершение фразы…':voice.starting?'Подключение…':voice.recording?'Микрофон включён':'Включить микрофон'}
        </button>
        <button className="button-icon" title="Переподключить микрофон" aria-label="Переподключить микрофон" disabled={voice.starting||voice.stopping} onClick={()=>void voice.restart()}><RefreshCw size={18}/></button>
        <button className="button-icon" title="Остановить команды и сверить документ" aria-label="Остановить команды и сверить документ" disabled={recovering} onClick={()=>void recover()}><Square size={18}/></button>
        <button className="button-icon" title="Отменить последнюю правку" aria-label="Отменить последнюю правку" disabled={busy||waitingText} onClick={()=>void manualVoiceCommand('Отмени')}><Undo2 size={18}/></button>
        <button className="button-icon" title="Начать многофразовую диктовку" aria-label="Начать многофразовую диктовку" aria-pressed={!!longDictation.current} disabled={busy||waitingText||!activeEl} onClick={()=>{manualChange();startDictation();}}><TextCursorInput size={18}/></button>
        <span className="voice-console-state" role="status">{recovering?'Сверка документа':needsRecovery?'Сохранение не подтверждено':thinking?'Локальная модель':pending?`Сохранение · ${elapsed} с`:'Готово'}</span>
        {latency!==null&&<output className="voice-console-latency" title="Очередь и выполнение после распознавания; без ASR и отрисовки">Выполнение: {latency} мс</output>}
      </div>
      <div className="voice-console-feedback">
        <span className="deck-voice-status" aria-live="polite"><i className={`deck-connection-dot ${voice.recording?'live':''}`}/>{voice.error||voice.partial||voiceNotice}</span>
        <span className="voice-console-selection">Слайд {index+1}/{scenes.length} · {selectedIds.length>1?`Выбрано: ${selectedIds.length}`:activeEl?`Элемент ${selectable(scene).findIndex(e=>e.id===activeEl)+1}`:'Нет выделения'}</span>
      </div>
      {waitingText&&<div className="voice-console-dictation"><span role="status">{longDictation.current?'Черновик диктовки':'Ожидается новый текст'}</span>{longDictation.current&&<button className="button-icon" title="Сохранить диктовку" aria-label="Сохранить диктовку" disabled={!dictationText.trim()||busy} onClick={()=>void manualVoiceCommand('Готово')}><Check size={16}/></button>}<button className="button-icon" title="Отменить диктовку" aria-label="Отменить диктовку" onClick={()=>{manualChange();setVoiceNotice('Ввод текста отменён');}}><X size={16}/></button></div>}
      {longDictation.current&&<textarea className="voice-dictation-draft" aria-label="Черновик диктовки" maxLength={12000} value={dictationText} onChange={e=>{if(longDictation.current){longDictation.current.text=e.target.value;setDictationText(e.target.value);}}}/>}
      {voice.recording&&<div className="voice-console-device"><meter aria-label="Уровень микрофона" min={0} max={100} value={voice.level}/><span>{voice.device}</span><span>{voice.connection}</span></div>}
      {voice.heard&&<div className="voice-console-heard">Распознано: «{voice.heard}»</div>}
      <div className="voice-console-command">
        <form onSubmit={e=>{e.preventDefault();if(commandDraft.trim()){void manualVoiceCommand(commandDraft);setCommandDraft('');}}}><input aria-label="Команда редактирования" value={commandDraft} onChange={e=>setCommandDraft(e.target.value)} placeholder="Команда редактирования"/><button className="button-icon" title="Выполнить команду" aria-label="Выполнить команду" disabled={!commandDraft.trim()}><Send size={18}/></button></form>
        {activeEl&&<div className="voice-console-arrows" aria-label="Перемещение выбранного элемента">{[[ArrowLeft,'Влево'],[ArrowUp,'Вверх'],[ArrowDown,'Вниз'],[ArrowRight,'Вправо'],[AlignCenter,'В центр']].map(([Icon,command])=>{const Symbol=Icon as typeof ArrowLeft;return <button key={command as string} className="button-icon" disabled={busy||waitingText} title={command as string} aria-label={`Переместить ${(command as string).toLowerCase()}`} onClick={()=>void manualVoiceCommand(command as string)}><Symbol size={18}/></button>;})}</div>}
      </div>
      {confirmDelete!==null&&<div>Удалить слайд {confirmDelete.index}? <button className="button" onClick={()=>void manualVoiceCommand('да')}>Удалить</button><button className="button" onClick={()=>setConfirmDelete(null)}>Отмена</button></div>}
    </section>
    <div className="edit-body">
      <aside className="edit-rail" aria-label="Слайды">
        {scenes.map((s, i) => {
          const fs = findingsBySlide.get(s.slide_id) ?? [];
          const hasError = fs.some(f => f.severity === 'error');
          return <a key={s.slide_id} className={`edit-thumb-row ${i === index ? 'current' : ''}`}
            aria-label={`Слайд ${i + 1}`} aria-current={i === index ? 'true' : undefined}
            href={`#slide-${i + 1}`} onClick={e => { e.preventDefault(); manualChange();setActiveEl(null);setIndex(i); }}>
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
          {(imageFresh||previewLoaded!==previewRequestKey)&&<div style={{position:'absolute',inset:0}}>
            {active?.slide_images?.[index]?<img className="edit-slide-img" src={absoluteUrl(active.slide_images[index])} alt={`Слайд ${index+1}: сохранённый предпросмотр`}/>:<div role="status">Загружаю слайд…</div>}
          </div>}
          {!imageFresh&&livePreview?.key===previewRequestKey&&<iframe key={previewRequestKey} title="Живой слайд" className="edit-slide-img" sandbox="" onLoad={()=>setPreviewLoaded(previewRequestKey)} style={{position:'absolute',inset:0,width:'100%',height:'100%',border:0,pointerEvents:'none',visibility:previewLoaded===previewRequestKey?'visible':'hidden'}} srcDoc={livePreview.html}/>}
          {selectable(scene).map((el,elementIndex) => {
            const [x, y, w, h] = el.box;
            const style: React.CSSProperties = { left: `${x * 100}%`, top: `${y * 100}%`, width: `${w * 100}%`, height: `${h * 100}%` };
            return <div key={el.id} className={`edit-el-box ${selectedIds.includes(el.id) ? 'active' : ''} ${candidateIds.includes(el.id)?'voice-candidate':''}`} style={style}
              onClick={event => {manualChange();if(event.shiftKey){setSelectedIds(ids=>ids.includes(el.id)?ids.filter(id=>id!==el.id):[...ids,el.id]);}else setActiveEl(el.id);}}>
              <span style={{position:'absolute',top:y>.04?-22:0,left:x>.04?-22:0,background:'var(--accent)',color:'white',padding:'2px 6px',borderRadius:4}}>{elementIndex+1}</span>
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
              onClick={() => {manualChange();applyVoiceResult({confirmDelete:index+1});}}><Trash2 size={20} strokeWidth={1.5}/></button>
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





