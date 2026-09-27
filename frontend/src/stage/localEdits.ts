import type {Component,VoiceEditor} from './voiceEditor';
import {applyPlan,Operation} from './editorOperations';
import {ambiguousContent} from './localCreation';
import {normalizeVoice,voiceNumber} from './voiceVocabulary';

const kinds:Record<string,Component['kind']>={заголовок:'title',текст:'text',карточка:'card',карточку:'card',фигура:'shape',фигуру:'shape',таблица:'table',таблицу:'table',диаграмма:'chart',диаграмму:'chart',изображение:'image',картинку:'image',картинка:'image',фото:'image'};
const kindPattern=Object.keys(kinds).join('|');
const unquote=(s:string)=>s.replace(/^[«"“]|[»"”]$/g,'');
const colors:Record<string,string>={красн:'#dc2626',син:'#2563eb',бел:'#ffffff',черн:'#17141f',зелен:'#15803d',желт:'#facc15',фиолетов:'#7654ff',сер:'#6b7280'};

/** Recognized references never fall back to an unrelated current selection. */
function targets(e:VoiceEditor,raw=''):string[]|undefined{
 const value=normalizeVoice(raw);
 if(!value||/^(это|его|ее|выбранное|выбранные|выбранный объект|выбранный элемент)$/.test(value))return e.selectedIds;
 if(/^(все|все элементы|все объекты)$/.test(value))return e.current.components.map(c=>c.id);
 const numeric=value.replace(/^(?:номера?|элементы?|объекты?)\s+/,'').replace(/№\s*/g,'').split(/\s+и\s+|\s*,\s*/).map(voiceNumber);
 if(numeric.every(n=>n!==undefined))return numeric.map(n=>{
  const c=e.current.components.find(c=>c.voiceNumber===n);
  if(!c)throw Error('Такого номера нет на этом слайде');return c.id;
 });
 const match=value.match(new RegExp(`^(?:(.+?) )?(${kindPattern})(?: (.+))?$`));
 let found:Component[]|undefined;
 if(match){
  const [,ordinal,kind,name]=match;
  if(ordinal&&voiceNumber(ordinal)===undefined)return;
  found=e.current.components.filter(c=>c.kind===kinds[kind]);
  if(ordinal)found=found.slice(voiceNumber(ordinal)!-1,voiceNumber(ordinal));
  if(name){
   const literal=/^«[^»]*»$|^"[^"]*"$/.test(name);
   if(!literal&&(ambiguousContent(name)||/(?:^|\s)(?:и|затем|потом)(?:\s|$)/.test(name)))return;
   found=found.filter(c=>normalizeVoice(c.text)===unquote(name));
   if(!literal&&!found.length)return;
  }
 }else{
  found=e.current.components.filter(c=>normalizeVoice(c.text)===unquote(value));
  if(!found.length)return;
 }
 if(!found.length)throw Error('Такого объекта нет на этом слайде');
 if(found.length>1)throw Error('Найдено несколько объектов. Уточните номер элемента.');
 return found.map(c=>c.id);
}

export function localEdits(e:VoiceEditor,raw:string):boolean{
 const c=normalizeVoice(raw);
 const apply=(operations:Operation[],summary:string)=>applyPlan(e,{operations,summary,clarification:''});
 const withTargets=(reference:string,operation:(ids:string[])=>Operation[],summary:string)=>{
  const ids=targets(e,reference);if(ids===undefined)return false;
  if(!ids.length)throw Error('Сначала выберите объект');
  apply(operation(ids),summary);return true;
 };
 const select=c.match(/^(?:выбери|выдели) (.+)$/);
 if(select){const ids=targets(e,select[1]);if(ids!==undefined){e.selectMany(ids);return true;}}
 const slide=c.match(/^(?:(?:перейди|переключись) на|открой|выбери) (?:слайд (.+)|(.+) слайд)$/);
 if(slide){const n=voiceNumber(slide[1]??slide[2]);if(n!==undefined){apply([{op:'slide_select',index:n}],'Слайд выбран');return true;}}
 if(/^(?:добавь|создай)(?: новый)? слайд$/.test(c)){apply([{op:'slide_add'}],'Слайд создан');return true;}
 const rename=raw.match(/^(?:(?:измени|замени) (заголовок|текст|текст заголовка)(?: на)?|переименуй (.+?) в)\s+(.+)$/i);
 if(rename&&!ambiguousContent(rename[3])){
  const ref=rename[2]??(normalizeVoice(rename[1])==='текст'?'':normalizeVoice(rename[1]).replace('текст ',''));
  return withTargets(ref,ids=>[{op:'update',targets:ids,props:{text:unquote(rename[3])}}],'Текст изменён');
 }
 const color=c.match(/^(?:(?:сделай|покрась) (.*?) ?|(?:цвет|заливка|фон)(?: слайда)? )(#[0-9a-f]{6}|(?:красн|син|бел|черн|зелен|желт|фиолетов|сер)(?:ым|им|ый|ий|ой|ая|яя|ое|ее))$/);
 if(color){
  const value=color[2].startsWith('#')?color[2]:Object.entries(colors).find(([key])=>color[2].startsWith(key))?.[1];
  if(!value)return false;
  const ref=color[1]??'';
  if(/^фон(?: слайда)?$/.test(ref)||c.startsWith('фон ')){apply([{op:'background',props:{fill:value}}],'Фон изменён');return true;}
  return withTargets(ref,ids=>ids.map(id=>({op:'update',targets:[id],props:c.startsWith('заливка ')||['shape','card'].includes(e.current.components.find(c=>c.id===id)!.kind)?{fill:value}:{color:value}})),'Цвет изменён');
 }
 const style=c.match(/^(?:сделай )?(?:(.+?) )?(жирным|жирный|курсивом|курсив|обычным|крупнее|мельче|меньше|больше|шире|уже)$/);
 if(style)return withTargets(style[1]??'',ids=>ids.map(id=>{
  const item=e.current.components.find(c=>c.id===id)!;
  const props:Partial<Component>=/^жирн/.test(style[2])?{bold:true}:/^курсив/.test(style[2])?{italic:true}:style[2]==='обычным'?{bold:false,italic:false}:style[2]==='шире'||style[2]==='уже'?{width:Math.max(50,Math.min(1280,item.width+(style[2]==='шире'?40:-40)))}:{size:Math.max(10,Math.min(160,item.size+(/крупнее|больше/.test(style[2])?4:-4)))};
  return {op:'update',targets:[id],props};
 }),'Свойства изменены');
 const dimension=c.match(/^(?:установи |сделай )?(размер текста|размер шрифта|ширина|высота|поворот|непрозрачность|скругление)(?: (.+?))?(?: на)? (\d+|[а-я ]+?)(?: пиксел(?:ь|я|ей)| процентов| градусов)?$/);
 if(dimension){
  // Try the full suffix first: multi-word Russian numbers are not object names.
  const rest=c.replace(/^(?:установи |сделай )?(?:размер текста|размер шрифта|ширина|высота|поворот|непрозрачность|скругление) /,'').replace(/ (?:пиксел(?:ь|я|ей)|процентов|градусов)$/,'');
  const full=voiceNumber(rest),n=full??voiceNumber(dimension[3]);
  if(n!==undefined){const key:Record<string,string>={'размер текста':'size','размер шрифта':'size',ширина:'width',высота:'height',поворот:'rotation',непрозрачность:'opacity',скругление:'radius'};
   return withTargets(full!==undefined?'':dimension[2]??'',ids=>[{op:'update',targets:ids,props:{[key[dimension[1]]]:dimension[1]==='непрозрачность'?n/100:n}}],'Размер изменён');}
 }
 const before=c.match(/^(?:сдвинь|перемести|подвинь) (.*?) на (.+?)(?: пиксел(?:ь|я|ей))? (вправо|влево|вверх|вниз)$/);
 const move=before?[before[0],before[1],before[3],before[2]]:c.match(/^(?:сдвинь|перемести|подвинь) (.*?) ?(вправо|влево|вверх|вниз|правее|левее|выше|ниже)(?: на (.+?)(?: пиксел(?:ь|я|ей))?)?$/);
 if(move){const n=move[3]?voiceNumber(move[3]):20;if(n!==undefined)return withTargets(move[1],ids=>[{op:'move',targets:ids,props:{x:/вправо|правее/.test(move[2])?n:/влево|левее/.test(move[2])?-n:0,y:/вниз|ниже/.test(move[2])?n:/вверх|выше/.test(move[2])?-n:0}}],'Объекты перемещены');}
 const remove=c.match(/^(удали|убери|дублируй|скопируй|заблокируй|разблокируй) (.+)$/);
 if(remove&&!/^(слайд|строку|столбец)(?: |$)/.test(remove[2]))return withTargets(remove[2],ids=>[remove[1].includes('блокируй')?{op:'update',targets:ids,props:{locked:remove[1]==='заблокируй'}}:{op:/дублируй|скопируй/.test(remove[1])?'duplicate':'delete',targets:ids}],'Команда выполнена');
 return false;
}
