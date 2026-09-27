import type {Component,VoiceEditor} from './voiceEditor';
import {applyPlan,Operation} from './editorOperations';
import {ambiguousContent} from './localCreation';
import {normalizeVoice,voiceNumber} from './voiceVocabulary';

const kinds:Record<string,Component['kind']>={заголовок:'title',заголовка:'title',текст:'text',текста:'text',карточка:'card',карточку:'card',карточки:'card',фигура:'shape',фигуру:'shape',фигуры:'shape',таблица:'table',таблицу:'table',таблицы:'table',таблице:'table',диаграмма:'chart',диаграмму:'chart',диаграммы:'chart',изображение:'image',изображения:'image',картинку:'image',картинка:'image',фото:'image'};
const kindPattern=Object.keys(kinds).join('|');
const unquote=(s:string)=>/^(?:«[^»]*»|"[^"]*"|“[^”]*”)$/.test(s)?s.slice(1,-1):s;
const colors:Record<string,string>={красн:'#dc2626',син:'#2563eb',бел:'#ffffff',черн:'#17141f',зелен:'#15803d',желт:'#facc15',фиолетов:'#7654ff',сер:'#6b7280'};
const hundreds:Record<string,number>={сто:100,двести:200,триста:300,четыреста:400,пятьсот:500,шестьсот:600,семьсот:700,восемьсот:800,девятьсот:900};

function number(raw:string):number|undefined{
 const s=normalizeVoice(raw);
 const n=voiceNumber(s);if(n!==undefined)return n;
 const ordinal=s.match(/^(перв|втор|треть|четверт|пят|шест|седьм|восьм|девят|десят)(?:ого|его|ой|ей|ю)$/);
 if(ordinal)return ['перв','втор','треть','четверт','пят','шест','седьм','восьм','девят','десят'].indexOf(ordinal[1])+1;
 if(s.startsWith('минус ')){const value=number(s.slice(6));return value===undefined||value<0?undefined:-value;}
 const [head,...tail]=s.split(' '),base=head==='тысяча'?1000:hundreds[head];
 if(base){const rest=tail.length?number(tail.join(' ')):0;if(rest!==undefined&&rest>=0&&rest<(base===1000?1000:100))return base+rest;}
}

const chained=(s:string)=>/(?:^|\s)(?:и|затем|потом)(?:\s|$)|[.!?;]\s+\S/i.test(s.replace(/«[^»]*»|"[^"]*"|“[^”]*”/g,''));

function coordinates(raw:string):[number,number]{
 const value=normalizeVoice(raw).replace(/^строка\s+/,'');
 const explicit=value.split(/\s*,\s*|\s+столбец\s+/);
 const candidates=explicit.length===2?[explicit]:value.split(' ').slice(1).map((_,i)=>[value.split(' ').slice(0,i+1).join(' '),value.split(' ').slice(i+1).join(' ')]);
 const valid=candidates.map(pair=>pair.map(number)).filter(pair=>pair.every(n=>n!==undefined));
 if(valid.length!==1)throw Error('Укажите строку и столбец ячейки числами, разделёнными запятой');
 return valid[0] as [number,number];
}

/** Recognized references never fall back to an unrelated current selection. */
function targets(e:VoiceEditor,raw=''):string[]|undefined{
 const value=normalizeVoice(raw);
 if(!value||/^(это|его|ее|выбранное|выбранные|выбранный объект|выбранный элемент|выбранный текст)$/.test(value))return e.selectedIds;
 if(/^(все|все элементы|все объекты)$/.test(value))return e.current.components.map(c=>c.id);
 const numeric=value.replace(/^(?:номера?|элементы?|объекты?)\s+/,'').replace(/№\s*/g,'').split(/\s+и\s+|\s*,\s*/).map(number);
 if(numeric.every(n=>n!==undefined))return numeric.map(n=>{
  const c=e.current.components.find(c=>c.voiceNumber===n);
  if(!c)throw Error('Такого номера нет на этом слайде');return c.id;
 });
 if(chained(value))return;
 if(/^(?:номера?|элементы?|объекты?)\s+|^№/.test(value))throw Error('Неверный номер объекта');
 const match=value.match(new RegExp(`^(?:(.+?) )?(${kindPattern})(?: (.+))?$`));
 let found:Component[]|undefined;
 if(match){
  const [,ordinal,kind,name]=match;
  if(ordinal&&number(ordinal)===undefined)return;
  found=e.current.components.filter(c=>c.kind===kinds[kind]);
  if(ordinal){const index=number(ordinal)!;found=index>0?found.slice(index-1,index):[];}
  if(name){
   const numbered=name.match(/^(?:номер|№)\s*(.+)$/);
   if(numbered){const n=number(numbered[1]);if(n===undefined)throw Error('Неверный номер объекта');found=found.filter(c=>c.voiceNumber===n);}
   else{
    const literal=/^«[^»]*»$|^"[^"]*"$|^“[^”]*”$/.test(name);
    if(!literal&&ambiguousContent(name))return;
    found=found.filter(c=>normalizeVoice(c.text)===unquote(name));
   }
  }
 }else{
  found=e.current.components.filter(c=>normalizeVoice(c.text)===unquote(value));
  if(!found.length&&unquote(value)===value)return;
 }
 if(!found.length)throw Error('Такого объекта нет на этом слайде');
 if(found.length>1)throw Error('Найдено несколько объектов. Уточните номер элемента.');
 return found.map(c=>c.id);
}

export function localEdits(e:VoiceEditor,raw:string):boolean{
 const c=normalizeVoice(raw).replace(/[.!?]+$/,'').trim();
 const apply=(operations:Operation[],summary:string)=>applyPlan(e,{operations,summary,clarification:''});
 const withTargets=(reference:string,operation:(ids:string[])=>Operation[],summary:string)=>{
  const ids=targets(e,reference);
  if(ids===undefined){if(chained(reference))return false;throw Error('Объект не найден. Уточните номер элемента.');}
  if(!ids.length)throw Error('Сначала выберите объект');
  apply(operation(ids),summary);return true;
 };
 const slideIndex=(reference:string)=>{
  if(!reference||/^(?:этот|текущий)$/.test(reference))return e.document.index+1;
  if(reference==='следующий')return e.document.index+2;
  if(reference==='предыдущий')return e.document.index;
  if(reference==='последний')return e.document.pages.length;
  const n=number(reference.replace(/^(?:номер|№)\s*/,''));if(n===undefined)throw Error('Неверный номер слайда');return n;
 };
 const shorthand=c.match(/^слайд (.+)$/);
 const slide=c.match(/^(?:(?:перейди|переключись) на|открой|выбери|покажи) (?:слайд (.+)|(.+) слайд)$/)
  ??c.match(/^(следующий|предыдущий|первый|последний) слайд$/)
  ??(shorthand&&number(shorthand[1].replace(/^(?:номер|№)\s*/,''))!==undefined?shorthand:null);
 if(slide&&!chained(c)){
  apply([{op:'slide_select',index:slideIndex(slide[1]??slide[2])}],'Слайд выбран');return true;
 }
 const slideEdit=c.match(/^(удали|убери|дублируй|скопируй) (?:слайд(?: (.+))?|(.+) слайд)$/);
 if(slideEdit&&!chained(c)){apply([{op:/удали|убери/.test(slideEdit[1])?'slide_delete':'slide_duplicate',index:slideIndex(slideEdit[2]??slideEdit[3]??'')}],'Слайды обновлены');return true;}
 if(/^(?:добавь|создай)(?: новый)? слайд$/.test(c)){apply([{op:'slide_add'}],'Слайд создан');return true;}
 const select=c.match(/^(?:выбери|выдели) (.+)$/);
 if(select){const ids=targets(e,select[1]);if(ids!==undefined){e.selectMany(ids);return true;}if(!chained(select[1]))throw Error('Объект не найден. Уточните номер элемента.');}
 const cell=raw.match(/^(?:в (.+?) )?(?:ячейка|(?:измени|заполни) ячейку) (.+?)\s*[:=]\s*([\s\S]*)$/i);
 if(cell){
  const [row,column]=coordinates(cell[2]);
  return withTargets(cell[1]??'',ids=>[{op:'table_cell',targets:ids,row,column,value:unquote(cell[3])}],'Ячейка изменена');
 }
 const tableScope=c.match(/^(.*?) (?:в|из) (.+)$/);
 const table=(tableScope?.[1]??c).match(/^(добавь|вставь|удали) (?:(строку|столбец)(?: (.+))?|(.+?) (строку|столбец))$/);
 if(table){
  const value=table[3]??table[4],index=value===undefined?undefined:number(value.replace(/^(?:номер|№)\s*/,''));
  if(value!==undefined&&chained(value))return false;
  if(value!==undefined&&index===undefined)throw Error('Неверный номер строки или столбца');
  return withTargets(tableScope?.[2]??'',ids=>[{op:`table_${(table[2]??table[5])==='строку'?'row':'column'}_${table[1]==='удали'?'delete':'add'}`,targets:ids,index}],'Таблица изменена');
 }
 const rename=raw.match(/^(?:(?:измени|замени) (текст заголовка|заголовок|текст)(?: на)?|переименуй ((?:«[^»]*»|"[^"]*"|“[^”]*”|[^«»"“”])+?) в)\s+(.+)$/i);
 if(rename&&(!ambiguousContent(rename[3])||unquote(rename[3])!==rename[3])){
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
 const toggle=c.match(/^(включи|выключи|убери) (жирный шрифт|полужирный шрифт|жирное начертание|курсив)(?: у (.+))?$/);
 if(toggle)return withTargets(toggle[3]??'',ids=>[{op:'update',targets:ids,props:{[toggle[2]==='курсив'?'italic':'bold']:toggle[1]==='включи'}}],'Свойства изменены');
 const style=c.match(/^(?:сделай )?(?:(.+?) )?(не жирным|нежирным|не курсивным|без курсива|без жирного|полужирным|полужирный|полужирной|жирным|жирный|жирной|курсивом|курсив|курсивным|курсивный|обычным|обычной|обычный шрифт|крупнее|мельче|меньше|больше|шире|уже)$/);
 if(style)return withTargets(style[1]??'',ids=>ids.map(id=>{
  const item=e.current.components.find(c=>c.id===id)!;
  const props:Partial<Component>=/^(?:полу)?жирн/.test(style[2])?{bold:true}:/^курсив/.test(style[2])?{italic:true}:/^(?:не ?жирным|без жирного)$/.test(style[2])?{bold:false}:/^(?:не курсивным|без курсива)$/.test(style[2])?{italic:false}:/^обычн/.test(style[2])?{bold:false,italic:false}:style[2]==='шире'||style[2]==='уже'?{width:Math.max(50,Math.min(1280,item.width+(style[2]==='шире'?40:-40)))}:{size:Math.max(10,Math.min(160,item.size+(/крупнее|больше/.test(style[2])?4:-4)))};
  return {op:'update',targets:[id],props};
 }),'Свойства изменены');
 const dimension=c.match(/^(?:установи |сделай )?(размер текста|размер шрифта|шрифт|ширина|ширину|высота|высоту|поворот|непрозрачность|прозрачность|скругление) (.+)$/);
 if(dimension){
  const rest=dimension[2].replace(/ (?:пиксел(?:ь|я|ей)|пункт(?:а|ов)?|процент(?:а|ов)?|градус(?:а|ов)?)$/,'');
  // Search longest numeric suffix first so a spoken number is never mistaken for a target.
  const words=rest.split(' ');
  for(let i=0;i<words.length;i++){
   const n=number(words.slice(i).join(' ').replace(/^(?:на|до) /,''));if(n===undefined)continue;
   const ref=words.slice(0,i).join(' ').replace(/(?:^| )(?:на|до)$/,'');
   const key:Record<string,string>={'размер текста':'size','размер шрифта':'size',шрифт:'size',ширина:'width',ширину:'width',высота:'height',высоту:'height',поворот:'rotation',непрозрачность:'opacity',прозрачность:'opacity',скругление:'radius'};
   return withTargets(ref,ids=>[{op:'update',targets:ids,props:{[key[dimension[1]]]:key[dimension[1]]==='opacity'?n/100:n}}],'Размер изменён');
  }
  if(chained(c))return false;
  throw Error('Укажите допустимое числовое значение');
 }
 const textAlign=c.match(/^(?:выравнивание текста|(?:выровняй|выравняй) текст)(?: (.+?))? по (левому краю|правому краю|центру)$/);
 if(textAlign)return withTargets(textAlign[1]??'',ids=>[{op:'update',targets:ids,props:{align:textAlign[2]==='левому краю'?'left':textAlign[2]==='правому краю'?'right':'center'}}],'Текст выровнен');
 const align=c.match(/^(?:выровняй|выравняй)(?: (.+?))? по (левому краю|правому краю|верхнему краю|нижнему краю|центру|середине|центру по вертикали)$/);
 if(align){const values:Record<string,string>={'левому краю':'left','правому краю':'right','верхнему краю':'top','нижнему краю':'bottom',центру:'center',середине:'middle','центру по вертикали':'middle'};
  return withTargets(align[1]??'',ids=>[{op:'align',targets:ids,value:values[align[2]]}],'Объекты выровнены');}
 const distribute=c.match(/^распредели(?: (.+?))? по (горизонтали|вертикали)$/);
 if(distribute)return withTargets(distribute[1]??'',ids=>[{op:'align',targets:ids,value:distribute[2]==='горизонтали'?'distribute-horizontal':'distribute-vertical'}],'Объекты распределены');
 const layer=c.match(/^(?:(?:перемести|отправь|подними|опусти|поставь|вынеси)(?: (.+?))? )?(на передний план|на задний план|на слой вперед|на слой назад|на один слой вперед|на один слой назад|на слой выше|на слой ниже)$/);
 if(layer)return withTargets(layer[1]??'',ids=>[{op:'layer',targets:ids,value:layer[2]==='на передний план'?'front':layer[2]==='на задний план'?'back':/вперед|выше/.test(layer[2])?'forward':'backward'}],'Порядок слоёв изменён');
 const before=c.match(/^(?:сдвинь|перемести|подвинь) (.*?) на (.+?)(?: пиксел(?:ь|я|ей))? (вправо|влево|вверх|вниз)$/);
 const move=before?[before[0],before[1],before[3],before[2]]:c.match(/^(?:сдвинь|перемести|подвинь) (.*?) ?(вправо|влево|вверх|вниз|правее|левее|выше|ниже)(?: на (.+?)(?: пиксел(?:ь|я|ей))?)?$/);
 if(move){const n=move[3]?voiceNumber(move[3]):20;if(n!==undefined)return withTargets(move[1],ids=>[{op:'move',targets:ids,props:{x:/вправо|правее/.test(move[2])?n:/влево|левее/.test(move[2])?-n:0,y:/вниз|ниже/.test(move[2])?n:/вверх|выше/.test(move[2])?-n:0}}],'Объекты перемещены');}
 const remove=c.match(/^(удали|убери|дублируй|скопируй|заблокируй|разблокируй) (.+)$/);
 if(remove&&!/^(слайд|строку|столбец)(?: |$)/.test(remove[2]))return withTargets(remove[2],ids=>[remove[1].includes('блокируй')?{op:'update',targets:ids,props:{locked:remove[1]==='заблокируй'}}:{op:/дублируй|скопируй/.test(remove[1])?'duplicate':'delete',targets:ids}],'Команда выполнена');
 return false;
}
