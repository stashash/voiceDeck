import type {VoiceEditor} from './voiceEditor';
import {applyPlan} from './editorOperations';
import {localCreation,ambiguousContent} from './localCreation';
import {localEdits} from './localEdits';
import {normalizeVoice,voiceNumber as number} from './voiceVocabulary';

/** Strict local matches only; free-form instructions remain the planner's responsibility. */
export function quickVoice(e:VoiceEditor,raw:string):boolean{
 const c=normalizeVoice(raw).replace(/[.!?]+$/,'').trim();
 if(/^(покажи|скрой|убери) номера$/.test(c)){e.showNumbers=c.startsWith('покажи');e.notice=e.showNumbers?'Номера показаны. Скажите «Выбери номер семь»':'Номера скрыты';return true;}
 if(/^сними выделение$/.test(c)){e.selectMany([]);return true;}
 const creation=localCreation(raw);
 if(creation){applyPlan(e,{operations:creation,clarification:'',summary:'Элементы созданы'});return true;}
 if(c==='новый слайд'){e.command(raw);return true;}
 const exact:Record<string,object>={'жирный':{bold:true},'обычный':{bold:false,italic:false},'курсив':{italic:true},'заблокируй':{locked:true},'разблокируй':{locked:false},'впиши изображение':{fit:'contain'},'заполни изображением':{fit:'cover'}};
 if(exact[c]){applyPlan(e,{operations:[{op:'update',props:exact[c]}],clarification:'',summary:'Свойства изменены'});return true;}
 const replacement=raw.match(/^(?:замени текст на|напиши|запиши)\s+(.+)$/i);
 if(replacement&&e.selected&&!ambiguousContent(replacement[1])){applyPlan(e,{operations:[{op:'update',props:{text:replacement[1].replace(/^[«"]|[»"]$/g,'')}}],clarification:'',summary:'Текст изменён'});return true;}
 const style=c.match(/^(?:сделай |цвет |заливка )?(красным|красный|синим|синий|белым|белый|черным|черный|акцентным|акцентный)$/);
 if(style){const color=style[1].startsWith('крас')?'#dc2626':style[1].startsWith('син')?'#2563eb':style[1].startsWith('бел')?'#ffffff':style[1].startsWith('чер')?'#17141f':e.color('accent','#7654ff');applyPlan(e,{operations:e.selectedIds.map(id=>({op:'update',targets:[id],props:e.current.components.find(c=>c.id===id)?.kind==='card'||e.current.components.find(c=>c.id===id)?.kind==='shape'?{fill:color}:{color}})),clarification:'',summary:'Цвет изменён'});return true;}
 const actions:Record<string,{op:string;value?:string}>={'сгруппируй':{op:'group'},'разгруппируй':{op:'ungroup'}};
 if(actions[c]){applyPlan(e,{operations:[actions[c]],clarification:'',summary:'Расположение изменено'});return true;}
 if(c==='одинаковая высота'||c==='одинаковая ширина'){const key=c==='одинаковая высота'?'height':'width';if(!e.selected){e.notice='Выберите объекты';return true;}applyPlan(e,{operations:[{op:'update',props:{[key]:e.selected[key]}}],clarification:'',summary:'Размеры выровнены'});return true;}
 const selection=c.match(/^вы(?:бери|дели) (.+)$/);
 if(selection&&!/^(?:слайд(?: |$)|.+ слайд$)/.test(selection[1])){
  const value=selection[1];
  if(value==='все'||value==='все элементы'){e.selectMany(e.current.components.map(x=>x.id));return true;}
  const list=value.replace(/^(?:номера?|элементы?|объекты?)\s+/,'').replace(/№\s*/g,'').split(/\s+и\s+|\s*,\s*/).map(number);
  if(list.every(n=>n!==undefined)){
   const targets=list.map(n=>e.current.components.find(x=>x.voiceNumber===n));
   if(targets.some(x=>!x)){e.showNumbers=true;e.notice='Такого номера нет на этом слайде. Назовите номера с холста.';}
   else e.selectMany(targets.map(x=>x!.id));return true;
  }
  const cards=value.match(/^(все|две|три|четыре|\d+) карточки$/);
  if(cards){const targets=e.current.components.filter(x=>x.kind==='card');if(cards[1]==='все'||targets.length===number(cards[1]))e.selectMany(targets.map(x=>x.id));else{e.showNumbers=true;e.notice=`На слайде ${targets.length} карточек. Уточните номера: «Выбери номера два и три».`;}return true;}
  const name=value.replace(/^[«"]|[»"]$/g,'');const named=e.current.components.filter(x=>x.text.toLowerCase().replace(/ё/g,'е')===name);
  if(named.length===1){e.selectMany([named[0].id]);return true;}
  if(named.length>1){e.showNumbers=true;e.notice='Есть несколько элементов с таким текстом. Уточните номер.';return true;}
 }
 if(localEdits(e,raw))return true;
 const repeat=/^(еще|еще немного|половину назад)$/.test(c);
 const move=c.match(/^(?:(?:сдвинь|перемести) (?:выбранное |выбранные |это )?)?(вправо|влево|вверх|вниз|правее|левее|выше|ниже)(?: на (.+?)(?: пиксел(?:ь|я|ей))?)?$/);
 if(repeat||move){
  let ids=e.selectedIds,dx=0,dy=0;
  if(repeat){const last=e.lastMove;if(!last||last.snapshot!==JSON.stringify(e.document)){e.notice='Нет актуального перемещения. Сначала скажите, например, «Вправо на 20».';return true;}ids=last.ids;const factor=c==='половину назад'?-.5:c==='еще немного'?.5:1;dx=last.dx*factor;dy=last.dy*factor;}
  else {const amount=move![2]?number(move![2]):20;if(amount===undefined)return false;if(amount>1280){e.notice='Слишком большое перемещение';return true;}if(/вправо|правее/.test(move![1]))dx=amount;else if(/влево|левее/.test(move![1]))dx=-amount;else if(/вверх|выше/.test(move![1]))dy=-amount;else dy=amount;}
  if(!ids.length){e.notice='Сначала выберите объект по номеру или на холсте';return true;}
  applyPlan(e,{operations:[{op:'move',targets:ids,props:{x:dx,y:dy}}],clarification:'',summary:'Объекты перемещены'});return true;
 }
 if(/^(удали|убери|дублируй)( выбранное| выбранные| это)?$/.test(c)){
  if(!e.selectedIds.length){e.notice='Сначала выберите объекты';return true;}
  applyPlan(e,{operations:[{op:c.startsWith('дублируй')?'duplicate':'delete',targets:e.selectedIds}],clarification:'',summary:c.startsWith('дублируй')?'Созданы копии':'Выбранные объекты удалены'});return true;
 }
 return false;
}


