import React,{lazy,Suspense,useEffect,useState} from 'react';
import {Layers,Presentation,MonitorPlay} from 'lucide-react';

// Страницы сервиса designer и сцены живого режима. Адрес после решётки: #/deck, #/template/<id>, #/stage, #/audience/<сессия>.
const DeckPage=lazy(()=>import('./designer/DeckPage'));
const TemplatePage=lazy(()=>import('./designer/TemplatePage'));
const StagePage=lazy(()=>import('./stage/StagePage'));
const AudiencePage=lazy(()=>import('./stage/AudiencePage'));

export type PageProps={id?:string};

function useHash(){
 const [hash,setHash]=useState(window.location.hash);
 useEffect(()=>{const on=()=>setHash(window.location.hash);window.addEventListener('hashchange',on);return ()=>window.removeEventListener('hashchange',on);},[]);
 return hash;
}

function Tabs({route}:{route:string}){
 const tabs:[string,string,React.ReactNode][]=[['deck','Колода',<Presentation size={16}/>],['stage','Сцена',<MonitorPlay size={16}/>],['','Речь',<Layers size={16}/>]];
 return <nav className="page-tabs" aria-label="Разделы">{tabs.map(([id,title,icon])=><a key={id} href={`#/${id}`} className={route===id?'active':''}>{icon}{title}</a>)}</nav>;
}

export function Router({home}:{home:React.ReactNode}){
 const [,route='',id]=useHash().split('/');
 if(route==='')return <>{home}</>;
 // Окно зала показывает только слайд и субтитры: разделов там нет.
 if(route==='audience')return <Suspense fallback={null}><AudiencePage id={id}/></Suspense>;
 const page=route==='deck'?<DeckPage/>:route==='template'?<TemplatePage id={id}/>:route==='stage'?<StagePage/>:null;
 if(!page){window.location.hash='#/';return null;}
 return <div className="page"><Tabs route={route}/><Suspense fallback={<div className="page-loading">Загрузка</div>}>{page}</Suspense></div>;
}
