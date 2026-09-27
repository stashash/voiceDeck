import type {Component,VoiceEditor} from './voiceEditor';
export type Operation={op:string;targets?:string[];alias?:string;props?:Partial<Component>;value?:string;index?:number;row?:number;column?:number};
export type Plan={operations:Operation[];clarification:string;summary:string};
const kinds=['title','text','card','image','shape','table','chart'];
const numeric:Record<string,[number,number]>={x:[-1280,1280],y:[-720,720],width:[20,1280],height:[20,720],size:[10,160],rotation:[-360,360],opacity:[0,1],radius:[0,360],borderWidth:[0,20]};
function properties(raw:Partial<Component>={}){
 const props:Partial<Component>={};
 for(const [key,value] of Object.entries(raw)){
  if(value===null||value===undefined)continue;
  if(key in numeric){const [min,max]=numeric[key];if(typeof value!=='number'||!Number.isFinite(value)||value<min||value>max)throw Error(`Недопустимое значение ${key}`);}
  else if(['color','fill','borderColor'].includes(key)){if(typeof value!=='string'||!/^#[0-9a-f]{6}$|^transparent$/i.test(value))throw Error('Недопустимый цвет');}
  else if(key==='kind'){if(!kinds.includes(String(value)))throw Error('Неизвестный тип компонента');}
  else if(['text','font'].includes(key)){if(typeof value!=='string'||value.length>12000)throw Error('Недопустимый текст');}
  else if(['bold','italic','locked'].includes(key)){if(typeof value!=='boolean')throw Error('Недопустимый стиль');}
  else if(key==='align'){if(!['left','center','right'].includes(String(value)))throw Error('Недопустимое выравнивание');}
  else if(key==='fit'){if(!['cover','contain'].includes(String(value)))throw Error('Недопустимое кадрирование');}
  else if(key==='rows'){if(!Array.isArray(value)||value.length>20||value.some(r=>!Array.isArray(r)||r.length>12||r.some(x=>typeof x!=='string'||x.length>1000)))throw Error('Таблица: максимум 20 строк и 12 столбцов');}
  else if(key==='labels'){if(!Array.isArray(value)||value.length>20||value.some(x=>typeof x!=='string'))throw Error('Недопустимые подписи');}
  else if(key==='values'){if(!Array.isArray(value)||value.length>20||value.some(x=>typeof x!=='number'||!Number.isFinite(x)||x<0))throw Error('Диаграмма: до 20 неотрицательных чисел');}
  else throw Error(`Свойство ${key} не поддерживается`);
  Object.assign(props,{[key]:value});
 }
 return props;
}

/** All document operations are committed atomically with a single undo checkpoint. */
export function applyPlan(editor:VoiceEditor,plan:Plan){
 if(!Array.isArray(plan.operations)||plan.operations.length>80)throw Error('Недопустимый план');
 if(plan.clarification){editor.notice=plan.clarification;return;}
 const original=structuredClone(editor.document);const history=[...editor.undoStack],redo=[...editor.redoStack];
 const aliases=new Map<string,string>();
 const resolve=(op:Operation)=>{
  const list=(op.targets?.length?op.targets:['selected']).flatMap(id=>id==='all'?editor.current.components.map(x=>x.id):id==='selected'?editor.selectedIds:[aliases.get(id)??id]);
  if(!list.length)throw Error('Сначала выберите объекты');
  const expanded=new Set<string>();
  for(const id of list){const c=editor.current.components.find(x=>x.id===id);if(!c)throw Error('Объект не найден. Уточните, какой элемент изменить.');expanded.add(c.id);if(c.group)for(const other of editor.current.components)if(other.group===c.group)expanded.add(other.id);}
  return [...expanded].map(id=>editor.current.components.find(c=>c.id===id)!);
 };
 const pageIndex=(op:Operation)=>{const byId=op.targets?.length?editor.document.pages.findIndex(p=>p.id===op.targets![0]):-1;const i=op.index!==undefined?op.index-1:byId>=0?byId:editor.document.index;if(i<0||i>=editor.document.pages.length)throw Error('Такого слайда нет');return i;};
 try{
  for(const op of plan.operations){
   const props=properties(op.props);
   if(op.op==='add'){if(editor.current.components.length>=100)throw Error('Лимит 100 элементов на слайде');const c=editor.add(props.kind??'text',props.text??'');editor.update(c.id,props,false);if(!props.color)editor.ensureContrast(c);if(op.alias)aliases.set(op.alias,c.id);continue;}
   if(op.op==='background'){if(!props.fill)throw Error('Укажите цвет фона');editor.current.background=props.fill;continue;}
   if(op.op==='notes'){editor.current.notes=op.value??'';continue;}
   if(op.op.startsWith('slide_')){
    if(op.op==='slide_add'){if(editor.document.pages.length>=100)throw Error('Лимит 100 слайдов');const i=(op.index??editor.document.pages.length+1)-1;if(i<0||i>editor.document.pages.length)throw Error('Неверная позиция слайда');editor.document.pages.splice(i,0,{id:crypto.randomUUID(),components:[],background:editor.color('background','#f7f5fa')});editor.document.index=i;}
    else if(op.op==='slide_select')editor.document.index=pageIndex(op);
    else if(op.op==='slide_delete'){if(editor.document.pages.length===1)throw Error('Нельзя удалить единственный слайд');editor.document.pages.splice(pageIndex(op),1);editor.document.index=Math.min(editor.document.index,editor.document.pages.length-1);}
    else if(op.op==='slide_duplicate'){const i=pageIndex(op),copy=structuredClone(editor.document.pages[i]);copy.id=crypto.randomUUID();const groups=new Map<string,string>();copy.components.forEach(c=>{c.id=crypto.randomUUID();if(c.group){if(!groups.has(c.group))groups.set(c.group,crypto.randomUUID());c.group=groups.get(c.group);}});editor.document.pages.splice(i+1,0,copy);editor.document.index=i+1;}
    else if(op.op==='slide_move'){const to=pageIndex(op);const [p]=editor.document.pages.splice(editor.document.index,1);editor.document.pages.splice(to,0,p);editor.document.index=to;}
    else throw Error('Неизвестная операция со слайдом');
    editor.document.selected=null;editor.document.selectedIds=[];continue;
   }
   if(op.op==='select'&&!op.targets?.length){editor.document.selected=null;editor.document.selectedIds=[];continue;}
   const targets=resolve(op);
   if(op.op!=='select'&&targets.some(c=>c.locked)&&!(op.op==='update'&&props.locked===false&&Object.keys(props).length===1))throw Error('Объект заблокирован. Сначала разблокируйте его.');
   if(op.op.startsWith('table_')){
    if(targets.length!==1||targets[0].kind!=='table')throw Error('Выберите одну таблицу');
    const c=targets[0],rows=structuredClone(c.rows?.length?c.rows:[['']]),cols=rows[0].length;
    if(rows.some(r=>r.length!==cols))throw Error('У строк таблицы разная длина');
    if(op.op==='table_cell'){
     if(!Number.isInteger(op.row)||!Number.isInteger(op.column)||!rows[(op.row??0)-1]||op.column!<1||op.column!>cols)throw Error('Такой ячейки нет');
     rows[op.row!-1][op.column!-1]=op.value??'';
    }else{
     const isRow=op.op.startsWith('table_row_'),add=op.op.endsWith('_add'),count=isRow?rows.length:cols;
     if(!['table_row_add','table_row_delete','table_column_add','table_column_delete'].includes(op.op))throw Error('Неизвестная операция таблицы');
     const i=(op.index??(add?count+1:count))-1;
     if(!Number.isInteger(i)||i<0||i>(add?count:count-1)||(!add&&count===1))throw Error('Неверный номер строки или столбца');
     if(isRow)rows.splice(i,add?0:1,...(add?[Array(cols).fill('')]:[]));
     else rows.forEach(row=>row.splice(i,add?0:1,...(add?['']:[])));
    }
    properties({rows});c.rows=rows;continue;
   }
   if(op.op==='transfer'){const destination=editor.document.pages[pageIndex(op)];if(destination===editor.current)continue;if(destination.components.length+targets.length>100)throw Error('Лимит 100 элементов на слайде');const ids=new Set(targets.map(c=>c.id));editor.current.components=editor.current.components.filter(c=>!ids.has(c.id));targets.forEach(c=>delete c.voiceNumber);destination.components.push(...targets);editor.document.selected=null;editor.document.selectedIds=[];continue;}
   if(op.op==='select'){editor.selectMany(targets.map(c=>c.id));continue;}
   if(op.op==='group'){const id=crypto.randomUUID();targets.forEach(c=>c.group=id);continue;}
   if(op.op==='ungroup'){targets.forEach(c=>delete c.group);continue;}
   if(op.op==='delete'){const ids=new Set(targets.map(c=>c.id));editor.current.components=editor.current.components.filter(c=>!ids.has(c.id));editor.document.selected=null;editor.document.selectedIds=[];continue;}
   if(op.op==='duplicate'){for(const c of targets){const copy={...structuredClone(c),id:crypto.randomUUID(),x:Math.min(1280-c.width,c.x+30),y:Math.min(720-c.height,c.y+30)};delete copy.group;delete copy.voiceNumber;editor.current.components.push(copy);editor.document.selected=copy.id;}continue;}
   if(op.op==='move'){props.x=Math.max(-Math.min(...targets.map(c=>c.x)),Math.min(props.x??0,...targets.map(c=>1280-c.x-c.width)));props.y=Math.max(-Math.min(...targets.map(c=>c.y)),Math.min(props.y??0,...targets.map(c=>720-c.y-c.height)));}
   if(op.op==='update'||op.op==='move'){for(const c of targets)editor.update(c.id,op.op==='move'?{x:c.x+(props.x??0),y:c.y+(props.y??0)}:props,false);continue;}
   if(op.op==='layer'){for(const c of op.value==='back'?[...targets].reverse():targets){const list=editor.current.components,i=list.indexOf(c);list.splice(i,1);const at=op.value==='front'?list.length:op.value==='back'?0:op.value==='forward'?Math.min(list.length,i+1):op.value==='backward'?Math.max(0,i-1):-1;if(at<0)throw Error('Неизвестный порядок слоёв');list.splice(at,0,c);}continue;}
   if(op.op==='align'){
    const left=targets.length===1?0:Math.min(...targets.map(c=>c.x)),right=targets.length===1?1280:Math.max(...targets.map(c=>c.x+c.width));
    const top=targets.length===1?0:Math.min(...targets.map(c=>c.y)),bottom=targets.length===1?720:Math.max(...targets.map(c=>c.y+c.height));
    if(op.value?.startsWith('distribute-')){if(targets.length<3)throw Error('Для распределения нужны минимум три объекта');const horizontal=op.value==='distribute-horizontal';if(!horizontal&&op.value!=='distribute-vertical')throw Error('Неверное распределение');const sorted=[...targets].sort((a,b)=>horizontal?a.x-b.x:a.y-b.y);const gap=((horizontal?right-left:bottom-top)-targets.reduce((sum,c)=>sum+(horizontal?c.width:c.height),0))/(targets.length-1);let pos=horizontal?left:top;for(const c of sorted){if(horizontal)c.x=pos;else c.y=pos;pos+=(horizontal?c.width:c.height)+gap;}}
    else for(const c of targets){switch(op.value){case 'left':c.x=left;break;case 'right':c.x=right-c.width;break;case 'center':c.x=(left+right-c.width)/2;break;case 'top':c.y=top;break;case 'bottom':c.y=bottom-c.height;break;case 'middle':c.y=(top+bottom-c.height)/2;break;default:throw Error('Неизвестное выравнивание');}}
    continue;
   }
   throw Error(`Операция ${op.op} не поддерживается`);
  }
  if(editor.document.pages.length>100||editor.document.pages.some(p=>p.components.length>100))throw Error('Лимит: 100 слайдов, 100 элементов на слайде');
  for(const p of editor.document.pages)for(const c of p.components){if(c.kind==='chart'&&((c.values?.length??0)!==(c.labels?.length??0)))throw Error('Число значений и подписей диаграммы не совпадает');}
  editor.ensureNumbers();
  if(JSON.stringify(original.pages)!==JSON.stringify(editor.document.pages)){editor.undoStack=editor.limitHistory([...history,original]);editor.redoStack=[];}
  editor.lastMove=undefined;
  if(plan.operations.length===1&&plan.operations[0].op==='move'){
   const before=original.pages[original.index];const moved=editor.current.components.filter(c=>{const old=before.components.find(o=>o.id===c.id);return old&&(old.x!==c.x||old.y!==c.y);});
   if(moved.length){const old=before.components.find(c=>c.id===moved[0].id)!;editor.lastMove={ids:moved.map(c=>c.id),dx:moved[0].x-old.x,dy:moved[0].y-old.y,snapshot:JSON.stringify(editor.document)};}
  }
  editor.notice=plan.summary||'Изменения применены';
 }catch(e){editor.document=original;editor.undoStack=history;editor.redoStack=redo;throw e;}
}
