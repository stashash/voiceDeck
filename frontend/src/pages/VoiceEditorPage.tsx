import React,{useEffect,useRef,useState} from 'react';
import {VoiceEditor} from '../stage/voiceEditor';
import {EditorCanvas} from '../stage/EditorCanvas';
import {downloadDeck} from '../stage/editorExport';
import {Microphone,Transport} from '../transport';
import {channelName} from '../stage/useSession';
import {getManifest,listDesignSystemItems,DesignSystemListItem} from '../designer/api';
export default function VoiceEditorPage(){
 const [editor]=useState(()=>{const e=new VoiceEditor();e.restore();return e;});
 const [audienceId]=useState(()=>crypto.randomUUID());
 const channel=useRef<BroadcastChannel|undefined>(undefined),showing=useRef(false);
 const [,tick]=useState(0);const refresh=()=>{tick(n=>n+1);if(editor.published)channel.current?.postMessage({kind:'slide',slide:editor.published});};
 const [text,setText]=useState(''),[partial,setPartial]=useState(''),[recording,setRecording]=useState(false),[busy,setBusy]=useState(false),[systems,setSystems]=useState<DesignSystemListItem[]>([]);
 const mic=useRef<Microphone|undefined>(undefined),transport=useRef<Transport|undefined>(undefined);const alive=useRef(true);
 const edit=(f:()=>void)=>{f();editor.save();refresh();};
 const execute=(value:string)=>{if(showing.current){if(/^(следующий|предыдущий) слайд[.!?]?$/i.test(value)){editor.command(value);editor.publish();refresh();}return;}editor.enqueue(value,refresh);};
 useEffect(()=>{const c=new BroadcastChannel(channelName(audienceId));channel.current=c;c.onmessage=e=>{if(e.data.kind==='hello'&&editor.published)c.postMessage({kind:'slide',slide:editor.published});};return()=>c.close();},[audienceId]);
 useEffect(()=>{listDesignSystemItems().then(setSystems).catch(()=>{});if(editor.document.designId)getManifest(editor.document.designId).then(ds=>{editor.design=ds;refresh();}).catch(()=>{});return()=>{alive.current=false;editor.cancel();transport.current?.close();void mic.current?.stop();};},[]);
 async function stop(){await mic.current?.stop();setRecording(false);if(transport.current?.ready)transport.current.send({type:'stop'});}
 async function start(){setBusy(true);try{
  if(!transport.current||transport.current.closed){const r=await fetch('/api/sessions',{method:'POST'});if(!r.ok)throw Error('Не удалось создать сессию распознавания');const credentials=await r.json();if(!alive.current)return;if(credentials.mode!=='live')throw Error('Распознавание речи недоступно: включите MODE=live');
  let seq=0;const seen=new Set<string>();
  const t=new Transport(credentials,()=>seq,event=>{if(!alive.current)return;if(event.seq){if(event.seq<=seq)return;seq=event.seq;}if(event.type==='partial')setPartial(event.text??'');if(event.type==='editor_utterance'&&typeof event.utterance_id==='string'&&!seen.has(event.utterance_id)){seen.add(event.utterance_id);setPartial('');execute(event.text??'');}if(event.type==='warning'){editor.notice=String(event.message);refresh();}},status=>{if(status==='Подключено')transport.current?.send({type:'editor_mode'});},message=>{editor.notice=message;refresh();});transport.current=t;} const t=transport.current;
  const deadline=Date.now()+8000;while(!t.ready&&Date.now()<deadline&&alive.current)await new Promise(r=>setTimeout(r,50));if(!alive.current)return;if(!t.ready)throw Error('Сервер распознавания не отвечает');
  t.send({type:'editor_mode'});const m=new Microphone();mic.current=m;await m.start(pcm=>{try{t.audio(pcm);}catch(e){editor.notice=String(e);refresh();void stop();}},message=>{editor.notice=message;refresh();void stop();});if(!alive.current){await m.stop();return;}setRecording(true);
 }catch(e){editor.notice=String(e);refresh();transport.current?.close();}finally{setBusy(false);}}
 return <main style={{padding:24}}><h1>Голосовой редактор</h1><p>Создавайте элементы, выбирайте их по номеру и редактируйте голосом. Документ автоматически сохраняется в этом браузере.</p>
 <div className="component-toolbar"><button className="button" disabled={busy} onClick={()=>void(recording?stop():start())}>{recording?'Остановить микрофон':'Включить микрофон'}</button><button className="button" onClick={()=>edit(()=>{editor.mode=editor.mode==='control'?'dictation':'control';})}>{editor.mode==='control'?'Управляю':'Диктую текст'}</button><button className="button" onClick={()=>edit(()=>editor.cancel())}>Стоп обработки</button><button className="button" onClick={()=>edit(()=>editor.undo())}>Отменить правку</button><button className="button" onClick={()=>edit(()=>editor.redo())}>Повторить</button><select aria-label="Дизайн-система" value={editor.document.designId??''} onChange={e=>void getManifest(e.target.value).then(ds=>edit(()=>editor.applyDesign(ds))).catch(err=>edit(()=>{editor.notice=String(err);}))}><option value="" disabled>Дизайн-система</option>{systems.map(ds=><option key={ds.id} value={ds.id}>{ds.name||ds.id}</option>)}</select><button className="button" onClick={()=>downloadDeck(editor,'html')}>Скачать HTML</button><button className="button" onClick={()=>downloadDeck(editor,'json')}>Скачать документ</button></div>
 <div className="component-toolbar">{editor.document.pages.map((p,i)=><button key={p.id} className="button" aria-pressed={i===editor.document.index} onClick={()=>edit(()=>{editor.document.index=i;editor.document.selected=null;})}>Слайд {i+1}</button>)}<button className="button" onClick={()=>edit(()=>editor.command('новый слайд'))}>+ Слайд</button></div>
 <div className="component-toolbar"><button className="button" onClick={()=>{editor.publish();refresh();window.open(`#/audience/${audienceId}`,'_blank');}}>Открыть экран зала</button><button className="button" aria-pressed={showing.current} onClick={()=>{showing.current=!showing.current;editor.cancel();refresh();}}>{showing.current?'Показываю: голосовые правки отключены':'Перейти к показу'}</button></div>
 <EditorCanvas editor={editor} edit={edit}/>
 <form onSubmit={e=>{e.preventDefault();if(text.trim()){execute(text);setText('');}}} style={{display:'flex',gap:12,marginTop:16}}><input aria-label="Голосовая команда текстом" style={{flex:1}} value={text} onChange={e=>setText(e.target.value)} placeholder="Добавь заголовок План запуска"/><button className="button" type="submit">Выполнить</button></form>
 <p aria-live="polite">{partial||editor.notice}{editor.thinking?' · Обрабатываю запрос…':''}</p>
 <div className="component-toolbar">{editor.imageResults.map((item,i)=><button className="button" key={item.url} onClick={()=>edit(()=>editor.pickImage(i+1))}><img src={item.url} alt={item.title} style={{width:140,height:90,objectFit:'cover'}}/>{i+1}. {item.title}</button>)}</div>
 </main>;
}



