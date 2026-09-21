import React,{useEffect,useState} from 'react';
import type {PageProps} from '../router';
import type {Slide} from '../store';
import {channelName,ChannelMessage} from './useSession';
import './stage.css';

function Frame({slide}:{slide:Slide}){
 if(slide.html)return <iframe className="audience-frame" sandbox="" srcDoc={slide.html} title="Слайд"/>;
 return <div className="audience-sketch">{slide.title&&<h1>{slide.title}</h1>}<ul>{slide.bullets.map((b,i)=><li key={i}>{b}</li>)}</ul></div>;
}

function FadeSlide({slideKey,children}:{slideKey:string;children:React.ReactNode}){
 const [visible,setVisible]=useState(false);
 useEffect(()=>{
  setVisible(false);
  const id=requestAnimationFrame(()=>setVisible(true));
  return ()=>cancelAnimationFrame(id);
 },[slideKey]);
 return <div className={`audience-fade${visible?' visible':''}`}>{children}</div>;
}

export default function AudiencePage({id}:PageProps){
 const [slide,setSlide]=useState<Slide|null>(null);
 const [final,setFinal]=useState(''),[partial,setPartial]=useState('');

 useEffect(()=>{
  if(!id)return;
  const ch=new BroadcastChannel(channelName(id));
  ch.onmessage=(e:MessageEvent<ChannelMessage>)=>{
   const data=e.data;
   if(data.kind==='slide')setSlide(data.slide);
   else{setFinal(data.final);setPartial(data.partial);}
  };
  return ()=>ch.close();
 },[id]);

 useEffect(()=>{
  function onKey(e:KeyboardEvent){
   if(e.key!=='f'&&e.key!=='F')return;
   if(document.fullscreenElement)void document.exitFullscreen();
   else void document.documentElement.requestFullscreen();
  }
  window.addEventListener('keydown',onKey);
  return ()=>window.removeEventListener('keydown',onKey);
 },[]);

 if(!id)return <div className="audience-page"><div className="audience-empty">Нет сессии</div></div>;

 const slideKey=slide?`${slide.chunk_id}:${slide.rev}`:'empty';
 return <div className="audience-page">
  <FadeSlide slideKey={slideKey}>{slide?<Frame slide={slide}/>:<div className="audience-empty">Ждём первый слайд</div>}</FadeSlide>
  <div className="audience-subtitle"><span>{final}</span>{partial&&<span className="tail"> {partial}</span>}</div>
 </div>;
}
