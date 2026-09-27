import type {Element, Scene, VoiceBatchOperation} from '../designer/api';
import type {AtomicVoiceStep, LayoutOperation} from './voiceOperations';

export type VoiceBatchPlan = {operations:VoiceBatchOperation[]}|{notice:string};
const epsilon=1e-8;
const boxValid=([x,y,w,h]:Element['box'])=>[x,y,w,h].every(Number.isFinite)&&x>=-epsilon&&y>=-epsilon&&w>0&&h>0&&x+w<=1+epsilon&&y+h<=1+epsilon;
function layout(elements:Element[],operation:LayoutOperation):string|undefined {
  if(elements.length<2)return 'Выберите хотя бы два объекта';
  const minX=Math.min(...elements.map(e=>e.box[0])), minY=Math.min(...elements.map(e=>e.box[1]));
  const maxX=Math.max(...elements.map(e=>e.box[0]+e.box[2])),maxY=Math.max(...elements.map(e=>e.box[1]+e.box[3]));
  if(operation==='distributeX'||operation==='distributeY'){
    if(elements.length<3)return 'Для равных отступов выберите хотя бы три объекта';
    const axis=operation==='distributeX'?0:1,size=axis+2;
    const sorted=[...elements].sort((a,b)=>a.box[axis]-b.box[axis]||a.id.localeCompare(b.id));
    const start=sorted[0].box[axis],end=sorted.at(-1)!.box[axis]+sorted.at(-1)!.box[size];
    const gap=(end-start-sorted.reduce((sum,e)=>sum+e.box[size],0))/(sorted.length-1);
    if(gap<-epsilon)return 'Недостаточно места для равных отступов без наложения';
    let offset=start;
    for(const el of sorted){el.box[axis]=offset;offset+=el.box[size]+Math.max(0,gap);}
    return;
  }
  const reference=[...elements[0].box];
  for(const el of elements){
    const b=el.box;
    switch(operation){
      case 'alignLeft':b[0]=minX;break;
      case 'alignRight':b[0]=maxX-b[2];break;
      case 'alignTop':b[1]=minY;break;
      case 'alignBottom':b[1]=maxY-b[3];break;
      case 'alignCenterX':b[0]=(minX+maxX-b[2])/2;break;
      case 'alignCenterY':b[1]=(minY+maxY-b[3])/2;break;
      case 'sameWidth':b[2]=reference[2];break;
      case 'sameHeight':b[3]=reference[3];break;
      case 'sameSize':b[2]=reference[2];b[3]=reference[3];break;
    }
  }
}

/** Compile a bounded macro in memory; never persist a successful prefix of a failed command. */
export function planVoiceBatch(scene:Scene,selectedIds:readonly string[],steps:readonly AtomicVoiceStep[]):VoiceBatchPlan {
  if(!selectedIds.length)return {notice:'Объекты не выбраны'};
  if(selectedIds.length>64||new Set(selectedIds).size!==selectedIds.length)return {notice:'Выберите не более 64 разных объектов'};
  if(!steps.length||steps.length>6)return {notice:'В составной команде допустимо от одной до шести операций'};
  const originals=selectedIds.map(id=>scene.elements.find(e=>e.id===id));
  if(originals.some(e=>!e))return {notice:'Выбор устарел. Выберите объекты заново'};
  const elements=originals.map(e=>({...e!,box:[...e!.box] as Element['box'],style:e!.style?{...e!.style}:undefined}));
  for(const step of steps){
    if(step.kind==='layout'){
      const notice=layout(elements,step.operation);if(notice)return {notice};
    }else if(step.kind==='move'){
      const left=Math.min(...elements.map(e=>e.box[0])),top=Math.min(...elements.map(e=>e.box[1]));
      const right=Math.max(...elements.map(e=>e.box[0]+e.box[2])),bottom=Math.max(...elements.map(e=>e.box[1]+e.box[3]));
      let dx=step.dx,dy=step.dy;
      if(step.align==='left')dx=.02-left;
      if(step.align==='right')dx=.98-right;
      if(step.align==='top')dy=.02-top;
      if(step.align==='bottom')dy=.98-bottom;
      if(step.align==='center'){dx=(1-right-left)/2;dy=(1-bottom-top)/2;}
      // Clamp the group as one body, keeping relative distances intact.
      dx=Math.max(-left,Math.min(1-right,dx));dy=Math.max(-top,Math.min(1-bottom,dy));
      for(const el of elements){el.box[0]+=dx;el.box[1]+=dy;}
    }else{
      if(step.slide!==undefined||step.elementNumber!==undefined)return {notice:'Групповая правка ограничена текущим выбором'};
      const textStyle=step.size_pt!==undefined||step.scale!==undefined||step.bold!==undefined||step.italic!==undefined||step.color!==undefined||step.text_align!==undefined;
      if(textStyle&&elements.some(el=>el.type!=='text'))return {notice:'Для оформления текста выберите только текстовые объекты'};
      if(step.fill!==undefined&&elements.some(el=>el.type!=='shape'))return {notice:'Для заливки выберите только фигуры'};
      for(const el of elements){
        if(step.width!==undefined)el.box[2]=step.width;
        if(step.height!==undefined)el.box[3]=step.height;
        if(step.fill!==undefined)el.fill=step.fill;
        if(textStyle){
          const style=el.style??={};
          if(step.size_pt!==undefined)style.size_pt=step.size_pt;
          if(step.scale!==undefined)style.size_pt=(style.size_pt??24)*step.scale;
          if(style.size_pt!=null&&(!Number.isFinite(style.size_pt)||style.size_pt<6||style.size_pt>144))return {notice:'Размер шрифта должен быть от 6 до 144 пунктов'};
          if(step.bold!==undefined)style.bold=step.bold;
          if(step.italic!==undefined)style.italic=step.italic;
          if(step.color!==undefined)style.color=step.color;
          if(step.text_align!==undefined)style.align=step.text_align;
        }
      }
    }
    if(elements.some(el=>!boxValid(el.box)))return {notice:'Правка выходит за границы слайда. Документ не изменён'};
  }
  const operations:VoiceBatchOperation[]=[];
  elements.forEach((el,index)=>{
    const old=originals[index]!,op:VoiceBatchOperation={element_id:el.id};
    if(el.box.some((v,i)=>Math.abs(v-old.box[i])>epsilon))op.box=el.box.map(v=>Math.max(0,v)) as Element['box'];
    for(const key of ['size_pt','bold','italic','color','align'] as const){
      if(el.style?.[key]!==old.style?.[key]&&el.style?.[key]!=null)op.style={...op.style,[key]:el.style[key]};
    }
    if(el.fill!==old.fill&&el.fill!=null)op.fill=el.fill;
    if(op.box||op.style||op.fill!==undefined)operations.push(op);
  });
  return operations.length?{operations}:{notice:'Объекты уже имеют нужные параметры'};
}
