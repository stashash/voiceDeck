import React from 'react';
import {Ruler,Sparkles} from 'lucide-react';
import {Scene,Finding,Box} from './api';

const findingIcon=(kind:Finding['kind'])=>kind==='deterministic'?<Ruler size={11}/>:<Sparkles size={11}/>;
const findingTitle=(kind:Finding['kind'])=>kind==='deterministic'?'Проверка по правилу':'Проверка по смыслу';

function styleFromBox([x,y,w,h]:Box):React.CSSProperties{
 return {left:`${x*100}%`,top:`${y*100}%`,width:`${w*100}%`,height:`${h*100}%`};
}

// Запасная вёрстка из элементов сцены: абсолютные блоки в процентах слайда.
function Fallback({scene,compact}:{scene:Scene;compact:boolean}){
 const bg=scene.background_color?`#${scene.background_color}`:undefined;
 return <div className="slide-fallback" style={{background:bg}}>
  {scene.elements.map(el=><div key={el.id} className={`slide-el slide-el-${el.type}`} style={{...styleFromBox(el.box),
    color:el.style?.color?`#${el.style.color}`:undefined,
    background:el.type!=='text'&&el.fill?`#${el.fill}`:undefined,
    textAlign:el.style?.align??undefined,
    fontWeight:el.style?.bold?700:undefined,
    fontStyle:el.style?.italic?'italic':undefined}}>
   {!compact&&el.type==='text'?el.text:null}
  </div>)}
 </div>;
}

export default function SlideFrame({imageUrl,scene,ratio=16/9,findings=[],activeFindingId=null,onSelectFinding,compact=false}:{
 imageUrl?:string|null;scene?:Scene|null;ratio?:number;
 findings?:Finding[];activeFindingId?:string|null;onSelectFinding?:(id:string)=>void;compact?:boolean;
}){
 return <div className="slide-frame" style={{aspectRatio:ratio}}>
  {imageUrl?<img className="slide-image" src={imageUrl} alt=""/>
   :scene?<Fallback scene={scene} compact={compact}/>
   :<div className="slide-empty">Нет предпросмотра</div>}
  {!compact&&findings.length>0&&<div className="slide-marks">
   {findings.filter(f=>f.box).map(f=><button key={f.id} type="button"
     className={`slide-mark ${f.severity} ${activeFindingId===f.id?'active':''}`}
     style={{left:`${f.box![0]*100}%`,top:`${f.box![1]*100}%`}}
     title={f.message} aria-label={f.message}
     onClick={()=>onSelectFinding?.(f.id)}>{findingIcon(f.kind)}</button>)}
  </div>}
 </div>;
}
export {findingIcon,findingTitle};
