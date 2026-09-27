import React,{useEffect,useRef,useState} from 'react';
import {Mic,MicOff,Square,Undo2,Redo2,Download,Save,Plus,Monitor,RefreshCw,Upload,Copy} from 'lucide-react';
import {VoiceEditor,Document} from '../stage/voiceEditor';
import {EditorCanvas} from '../stage/EditorCanvas';
import {downloadDeck} from '../stage/editorExport';
import {useVoiceInput} from '../stage/useVoiceInput';
import {EditorPersistence,openDocument,Draft} from '../stage/editorPersistence';
import {editorRequest} from '../stage/editorRequest';
import {prepareEditorModel,ModelStatus} from '../stage/editorModel';
import {channelName} from '../stage/useSession';
import {BASE_URL,getManifest,listDesignSystemItems,DesignSystemListItem} from '../designer/api';
import {mediaUrl} from '../stage/componentContent';

export default function FullEditorPage({source}:{source?:{deckId:string;variant:string}}){
 const [editor]=useState(()=>new VoiceEditor());
 const [audienceId]=useState(()=>crypto.randomUUID());
 const channel=useRef<BroadcastChannel|undefined>(undefined),showing=useRef(false),alive=useRef(true);
 const storage=useRef<EditorPersistence|undefined>(undefined);
 const opening=useRef(0);
 const [,tick]=useState(0);
 const refresh=()=>{if(!alive.current)return;tick(n=>n+1);if(editor.published)channel.current?.postMessage({kind:'slide',slide:editor.published});};
 const [text,setText]=useState(''),[title,setTitle]=useState('Презентация'),[ready,setReady]=useState(false),[error,setError]=useState(''),[exporting,setExporting]=useState(false);
 const [systems,setSystems]=useState<DesignSystemListItem[]>([]),[documents,setDocuments]=useState<{id:string;title:string}[]>([]);
 const [model,setModel]=useState<ModelStatus>();
 const titleRef=useRef(title);titleRef.current=title;
 const reloadList=()=>void editorRequest<{items:{id:string;title:string}[]}>('documents').then(r=>{if(alive.current)setDocuments(r.items);}).catch(()=>{});
 const edit=(f:()=>void)=>{try{f();editor.save();refresh();}catch(e){setError(String(e));}};

 async function exportPptx(){
  if(exporting)return;setExporting(true);setError('');
  try{
   const response=await fetch(BASE_URL+'/editor/export/pptx',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(editor.document),signal:AbortSignal.timeout(30000)});
   if(!response.ok){const data=await response.json();throw Error(typeof data.detail==='string'?data.detail:'Экспорт отклонён');}
   const url=URL.createObjectURL(await response.blob()),a=document.createElement('a');a.href=url;a.download=titleRef.current+'.pptx';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }catch(e){setError(String(e));}finally{setExporting(false);}
 }
 const execute=(value:string)=>{
  if(!ready)return;
  if(/^сохрани(?: презентацию)?[.!?]?$/i.test(value)){void storage.current?.flush().catch(e=>setError(String(e)));return;}
  if(/^скачай (?:презентацию|powerpoint|pptx)[.!?]?$/i.test(value)){void exportPptx();return;}
  if(showing.current){if(/^(следующий|предыдущий) слайд[.!?]?$/i.test(value)){editor.command(value);editor.publish();refresh();}return;}
  editor.enqueue(value,refresh);
 };
 const voice=useVoiceInput(execute);
 useEffect(()=>{
  const controller=new AbortController();
  void prepareEditorModel(controller.signal,setModel).catch(e=>{if(!controller.signal.aborted)setModel({state:'error',model:'',message:String(e)});});
  return()=>controller.abort();
 },[]);

 async function attach(draft:Draft){
  if(!alive.current)return;
  editor.cancel();editor.document=draft.document;editor.undoStack=[];editor.redoStack=[];editor.ensureNumbers();
  titleRef.current=draft.title;setTitle(draft.title);
  const persistence=new EditorPersistence(draft,refresh);storage.current=persistence;
  editor.onSave=()=>persistence.schedule(editor.document,titleRef.current);
  localStorage.setItem('voice-editor-document-id',draft.id);
  if(draft.document.designId)void getManifest(draft.document.designId).then(ds=>{if(alive.current&&storage.current===persistence){editor.design=ds;refresh();}}).catch(()=>{});
  editor.notice='Документ открыт';setReady(true);refresh();
  if(draft.dirty||draft.attempt)void persistence.flush().catch(()=>{});
 }
 async function open(id?:string){
  const version=++opening.current;setError('');
  try{
   if(storage.current?.draft.dirty)await storage.current.flush();
   if(version!==opening.current)return;
   setReady(false);
   if(id){const draft=await openDocument(id);if(version!==opening.current)return;await attach(draft);}
   else {const fresh=new VoiceEditor();await attach({id:crypto.randomUUID(),revision:0,title:'Новая презентация',document:fresh.document,dirty:true});}
   reloadList();
  }catch(e){if(version===opening.current){setError(String(e));setReady(!!storage.current);}}
 }
 useEffect(()=>{
  const version=++opening.current;
  alive.current=true;void listDesignSystemItems().then(setSystems).catch(()=>{});reloadList();
  void (async()=>{
   try{
    if(source){const imported=await editorRequest<Draft>(`documents/from-deck/${source.deckId}/${source.variant}`,{});const draft=await openDocument(imported.id);if(version===opening.current)await attach(draft);return;}
    const id=localStorage.getItem('voice-editor-document-id');
    if(id){const draft=await openDocument(id);if(version===opening.current)await attach(draft);return;}
    const legacy=new VoiceEditor();legacy.restore();await attach({id:crypto.randomUUID(),revision:0,title:'Презентация',document:legacy.document,dirty:true});
   }catch(e){if(alive.current&&version===opening.current)setError(String(e));}
  })();
  const unload=(event:BeforeUnloadEvent)=>{if(storage.current?.draft.dirty){event.preventDefault();event.returnValue='';}};
  window.addEventListener('beforeunload',unload);
  return()=>{alive.current=false;opening.current++;editor.cancel();editor.onSave=undefined;storage.current?.close();window.removeEventListener('beforeunload',unload);};
 },[]);
 useEffect(()=>{const c=new BroadcastChannel(channelName(audienceId));channel.current=c;c.onmessage=e=>{if(e.data.kind==='hello'&&editor.published)c.postMessage({kind:'slide',slide:editor.published});};return()=>c.close();},[audienceId]);

 async function importJson(file?:File){
  if(!file)return;
  try{
   if(file.size>16_000_000)throw Error('Документ больше 16 МБ');
   const document=await editorRequest<Document>('documents/validate',JSON.parse(await file.text()));
   if(storage.current?.draft.dirty)await storage.current.flush();
   await attach({id:crypto.randomUUID(),revision:0,title:file.name.replace(/\.json$/i,''),document,dirty:true});reloadList();
  }catch(e){setError(String(e));}
 }

 return <section className="full-editor" aria-label="Редактор элементов">
  <div className="component-toolbar editor-document-bar">
   <input aria-label="Название документа" value={title} disabled={!ready} maxLength={200} onChange={e=>{titleRef.current=e.target.value;setTitle(e.target.value);editor.save();}}/>
   <select aria-label="Документ" value={storage.current?.draft.id??''} onChange={e=>void open(e.target.value)}><option value="" disabled>Документы</option>{storage.current&&!documents.some(d=>d.id===storage.current?.draft.id)&&<option value={storage.current.draft.id}>{title}</option>}{documents.map(d=><option value={d.id} key={d.id}>{d.title}</option>)}</select>
   <button className="button" title="Новый документ" aria-label="Новый документ" onClick={()=>void open()}><Plus size={18}/></button>
   <label className="button" title="Открыть JSON"><Upload size={18}/><input aria-label="Импорт JSON" type="file" accept=".json" className="editor-file-input" onChange={e=>void importJson(e.target.files?.[0])}/></label>
  </div>
  {(error||voice.error)&&<p role="alert" className="editor-error">{error||voice.error}</p>}
  {!ready?<p role="status">{error?'Документ не открыт':'Загрузка документа…'}</p>:<>
   {source&&<details className="editor-import-note"><summary>Редактируемая версия · исходник сохранён</summary><p>Версия построена по объектам слайда. Сложное оформление, анимации и эффекты шаблона могут отличаться. Исходные файлы доступны в редакторе шаблона.</p></details>}
   <div className="component-toolbar">
    <button className="button" disabled={voice.starting} aria-pressed={voice.recording} onClick={()=>void(voice.recording?voice.stop():voice.start())}>{voice.recording?<MicOff size={18}/>:<Mic size={18}/>} {voice.recording?'Выключить':'Микрофон'}</button>
    <div className="editor-segmented" role="group" aria-label="Режим ввода">{(['control','dictation'] as const).map(mode=><button key={mode} aria-pressed={editor.mode===mode} onClick={()=>edit(()=>{editor.mode=mode;})}>{mode==='control'?'Команды':'Диктовка'}</button>)}</div>
    <button className="button" title="Стоп обработки" aria-label="Стоп обработки" onClick={()=>edit(()=>editor.cancel())}><Square size={17}/></button>
    <button className="button" title="Отменить правку" aria-label="Отменить правку" disabled={!editor.undoStack.length} onClick={()=>edit(()=>editor.undo())}><Undo2 size={18}/></button>
    <button className="button" title="Повторить правку" aria-label="Повторить правку" disabled={!editor.redoStack.length} onClick={()=>edit(()=>editor.redo())}><Redo2 size={18}/></button>
    <select aria-label="Дизайн-система" value={editor.document.designId??''} onChange={e=>void getManifest(e.target.value).then(ds=>edit(()=>editor.applyDesign(ds))).catch(err=>setError(String(err)))}><option value="" disabled>Оформление</option>{systems.map(ds=><option key={ds.id} value={ds.id}>{ds.name||ds.id}</option>)}</select>
    <button className="button" title="Сохранить" aria-label="Сохранить" onClick={()=>void storage.current?.retry().then(reloadList).catch(e=>setError(String(e)))}><Save size={18}/></button>
    <button className="button" disabled={exporting} onClick={()=>void exportPptx()}><Download size={18}/>PPTX</button>
    <button className="button" onClick={()=>downloadDeck(editor,'html')}><Download size={18}/>HTML</button>
    <button className="button" onClick={()=>downloadDeck(editor,'json')}><Download size={18}/>JSON</button>
   </div>
   <div className="editor-state"><span role="status">{storage.current?.status}</span>{editor.thinking&&<span>Обработка · очередь {editor.queued}</span>}{voice.recording&&<><meter aria-label="Уровень микрофона" min={0} max={100} value={voice.level}/><span>{voice.connection}</span><button className="button" aria-label="Переподключить микрофон" title="Переподключить микрофон" onClick={()=>void voice.restart()}><RefreshCw size={16}/></button></>}</div>
   {storage.current?.error&&<div role="alert" className="editor-error"><p>{storage.current.error}</p><button className="button" onClick={()=>void attach({id:crypto.randomUUID(),revision:0,title:titleRef.current+' (копия)',document:structuredClone(editor.document),dirty:true})}><Copy size={18}/>Сохранить отдельную копию</button></div>}
   <div className="component-toolbar editor-slides" role="tablist" aria-label="Слайды">{editor.document.pages.map((p,i)=><button key={p.id} role="tab" aria-selected={i===editor.document.index} onClick={()=>edit(()=>{editor.document.index=i;editor.document.selected=null;editor.document.selectedIds=[];})}>{i+1}</button>)}<button title="Добавить слайд" aria-label="Добавить слайд" onClick={()=>edit(()=>editor.command('новый слайд'))}><Plus size={18}/></button><button title="Экран зала" aria-label="Экран зала" onClick={()=>{editor.publish();refresh();window.open(`#/audience/${audienceId}`,'_blank');}}><Monitor size={18}/></button><button aria-pressed={showing.current} onClick={()=>{showing.current=!showing.current;editor.cancel();refresh();}}>{showing.current?'Показ':'Редактирование'}</button></div>
   {voice.heard&&<p className="editor-heard">Распознано: {voice.heard}</p>}
   <p aria-live="polite">{voice.partial||editor.notice}</p>
   {editor.waitingForText&&<button className="button" aria-label="Отменить ввод текста" onClick={()=>edit(()=>editor.cancelText())}><Square size={16}/>Отменить ввод текста</button>}
   <EditorCanvas editor={editor} edit={edit}/>
   <form className="editor-command" onSubmit={e=>{e.preventDefault();if(text.trim()){execute(text);setText('');}}}><input aria-label="Голосовая команда текстом" value={text} onChange={e=>setText(e.target.value)} placeholder="Команда"/><button className="button" type="submit">Выполнить</button></form>
   {model&&<p role="status">{model.state==='ready'?`Модель готова: ${model.model}`:model.state==='error'?model.message:`Загрузка модели: ${model.model}`}</p>}
   <div className="component-toolbar">{editor.imageResults.map((item,i)=><button className="button editor-image-choice" key={item.url} onClick={()=>edit(()=>editor.pickImage(i+1))}><img src={mediaUrl(item.url)} alt={item.title}/>{i+1}. {item.title}</button>)}</div>
  </>}
 </section>;
}
