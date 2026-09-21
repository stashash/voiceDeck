import React,{useEffect,useState} from 'react';
import {ImageOff,Upload} from 'lucide-react';
import type {PageProps} from '../router';
import {DesignSystem,assetUrl,getManifest,listDesignSystems,uploadDesignSystem} from './api';
import './deck.css';

export default function TemplatePage({id}:PageProps){
 const [ids,setIds]=useState<string[]>([]);
 const [ds,setDs]=useState<DesignSystem|null>(null);
 const [error,setError]=useState('');
 const [busy,setBusy]=useState(false);

 useEffect(()=>{listDesignSystems().then(setIds).catch(()=>{});},[]);
 useEffect(()=>{
  if(!id){setDs(null);return;}
  setError('');setDs(null);
  getManifest(id).then(setDs).catch(e=>setError(String(e)));
 },[id]);

 async function upload(file:File){
  setBusy(true);setError('');
  try{const next=await uploadDesignSystem(file);setIds(v=>Array.from(new Set([...v,next.id])));window.location.hash=`#/template/${next.id}`;}
  catch(e){setError(String(e));}
  finally{setBusy(false);}
 }

 return <div className="deck-shell">
  <div className="template-picker">
   {ids.map(item=><a key={item} href={`#/template/${item}`} className={item===id?'active':''}>{item}</a>)}
   <label className="button outline small" title="Загрузить новый pptx для разбора">
    <Upload size={14}/>Загрузить
    <input type="file" accept=".pptx" hidden disabled={busy}
     onChange={e=>{const f=e.target.files?.[0];if(f)void upload(f);e.target.value='';}}/>
   </label>
  </div>
  {error&&<div className="notice" role="alert">{error}<button onClick={()=>setError('')} aria-label="Закрыть сообщение">×</button></div>}
  {!id&&!error&&<div className="empty-state">
   <h2>Шаблон не выбран</h2>
   <label className="button primary">
    <Upload size={16}/>Загрузить pptx
    <input type="file" accept=".pptx" hidden disabled={busy}
     onChange={e=>{const f=e.target.files?.[0];if(f)void upload(f);e.target.value='';}}/>
   </label>
  </div>}
  {ds&&<div className="template-body">
   <h1>{ds.source_file}</h1>
   <section className="template-section">
    <h2>Палитра</h2>
    <div className="swatch-row">
     {ds.tokens.colors.map((c,i)=><div key={i} className="swatch" title={`${c.role} · ${Math.round(c.share*100)}%`}>
      <span className="swatch-color" style={{background:`#${c.hex}`}}/>
      <span className="swatch-role">{c.role}</span>
     </div>)}
    </div>
   </section>
   <section className="template-section">
    <h2>Шрифты</h2>
    <ul className="token-list">
     {ds.tokens.fonts.map((f,i)=><li key={i}><strong>{f.family}</strong><span>{f.role} · {Math.round(f.share*100)}%</span></li>)}
    </ul>
   </section>
   <section className="template-section">
    <h2>Шкала кеглей</h2>
    <ul className="token-list">
     {ds.tokens.type_scale.map((t,i)=><li key={i}><strong>{t.size_pt} pt</strong><span>{t.role}</span></li>)}
    </ul>
   </section>
   <section className="template-section">
    <h2>Слайды-образцы <span className="count">{ds.patterns.length}</span></h2>
    <div className="pattern-grid">
     {ds.patterns.map(p=>{
      const bg=p.background_asset?ds.assets.find(a=>a.id===p.background_asset):undefined;
      const previewSrc=p.preview??(bg?assetUrl(ds.id,bg.path):null);
      return <div key={p.id} className={`pattern-card ${p.needs_images?'skip':''}`}>
       <div className="pattern-thumb">
        {previewSrc?<img src={previewSrc} alt=""/>:<ImageOff size={20}/>}
       </div>
       <div className="pattern-meta">
        <strong>{p.kind}</strong>
        <span>{p.purpose||'назначение не определено'}</span>
       </div>
       {p.needs_images&&<span className="pattern-flag" title="Нужны фото, которых нет: сервис этот образец не подберёт">не используется</span>}
      </div>;
     })}
    </div>
   </section>
  </div>}
 </div>;
}
