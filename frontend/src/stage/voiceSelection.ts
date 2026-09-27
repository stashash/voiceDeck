import type {Element,Scene} from '../designer/api';
import {normalizeVoice,voiceNumber} from './voiceVocabulary';

export type VoiceSelectionResult =
 | {kind:'selection';ids:string[];notice:string}
 | {kind:'clarify';candidateIds:string[];notice:string}
 | null;

const normalize=(text:string)=>normalizeVoice(text.normalize('NFC'));
const isTitle=(element:Element)=>element.type==='text'&&/^(?:title|heading|заголовок)$/i.test(element.role);
const clarify=(candidateIds:string[]=[],notice='Уточните объекты для выбора на текущем слайде.'):VoiceSelectionResult=>({kind:'clarify',candidateIds,notice});
const select=(elements:Element[]):VoiceSelectionResult=>elements.length
 ? {kind:'selection',ids:elements.map(element=>element.id),notice:elements.length===1?'Выбран один элемент.':`Выбрано элементов: ${elements.length}.`}
 : clarify([],'На текущем слайде подходящих элементов нет.');
const single=(elements:Element[]):VoiceSelectionResult=>elements.length===1?select(elements)
 : clarify(elements.map(element=>element.id),elements.length?'Найдено несколько элементов. Уточните номер.':'На текущем слайде подходящих элементов нет.');

const groupKinds:Record<string,(element:Element)=>boolean>={
 'весь текст':element=>element.type==='text',
 'все тексты':element=>element.type==='text',
 'все текстовые элементы':element=>element.type==='text',
 'все заголовки':isTitle,
 'все фигуры':element=>element.type==='shape',
 'все изображения':element=>element.type==='image',
 'все картинки':element=>element.type==='image',
 'все элементы':()=>true,
 'все объекты':()=>true,
};
const targetKinds:Record<string,(element:Element)=>boolean>={
 фигуру:element=>element.type==='shape',
 картинку:element=>element.type==='image',
 изображение:element=>element.type==='image',
 таблицу:element=>element.type==='table',
 заголовок:isTitle,
};
const quotePairs:Record<string,string>={'«':'»','"':'"','“':'”','„':'“',"'":"'"};
const hasSlideScope=(text:string)=>/(?:^|\s)слайд(?:а|е|у|ом|ы|ов|ам|ами|ах)?(?:\s|[,.:;!?]|$)/.test(text);

function literalQuery(raw:string):string|undefined {
 const value=raw.trim(),closing=quotePairs[value[0]];
 if(!closing)return /[«»"“”„']/.test(value)?undefined:value;
 const end=value.indexOf(closing,1);
 if(end<0||!/^\s*[.!?]*$/.test(value.slice(end+1)))return;
 const content=value.slice(1,end).trim();
 return content&&!/[«»"“”„]/.test(content)?content:undefined;
}

function elementNumber(raw:string):number|undefined {
 const value=raw.replace(/^(?:номер\s+|№\s*)/,'');
 const ordinal=value.match(/^(\d+)-(?:й|ый|ой|ий)$/);
 const number=ordinal?Number(ordinal[1]):voiceNumber(value);
 return number!==undefined&&Number.isSafeInteger(number)&&number>0?number:undefined;
}

function validBox(element:Element):boolean {
 return element.box.length===4&&element.box.every(Number.isFinite)&&element.box[2]>0&&element.box[3]>0;
}

function extreme(elements:Element[],score:(element:Element)=>number,largest:boolean):VoiceSelectionResult {
 if(!elements.length)return single([]);
 const values=elements.map(score);
 if(values.some(value=>!Number.isFinite(value)))return clarify(elements.map(element=>element.id),'Не удалось однозначно сравнить размеры или положение элементов.');
 const best=values.reduce((a,b)=>largest?Math.max(a,b):Math.min(a,b));
 // Normalized boxes can differ by floating-point rounding only.
 return single(elements.filter((_,index)=>Math.abs(values[index]-best)<=1e-9*Math.max(1,Math.abs(best))));
}

/** Pure replacement selection. Existing selection never breaks semantic ties. */
export function resolveVoiceSelection(raw:string,scene:Scene,selectedIds:readonly string[]=[]):VoiceSelectionResult {
 const command=normalize(raw).replace(/^команда(?:\s*[:,.!]\s*|\s+)/,'');
 const match=command.match(/^(?:выбери|выдели|покажи)\s+(.+)$/);
 if(!match)return null;
 const target=match[1].replace(/[.!?]+$/,'').trim();
 // Keep the same stable text-first order as deckSelectable without importing its executor.
 const elements=[...scene.elements.filter(element=>element.type==='text'),...scene.elements.filter(element=>element.type!=='text')];
 const group=Object.hasOwn(groupKinds,target)?groupKinds[target]:undefined;
 if(group)return select(elements.filter(group));

 const list=target.match(/^(?:элементы|объекты)(?:\s+(.*))?$/);
 if(list){
  const tokens=(list[1]??'').split(/\s*,\s*(?:и\s+)?|\s+и\s+/);
  const numbers=tokens.map(token=>elementNumber(token.trim()));
  if(tokens.length<2||numbers.some(number=>number===undefined||number>elements.length))return clarify([],'Укажите существующие номера элементов через «и» или запятую.');
  const positions=new Set(numbers);
  return select(elements.filter((_,index)=>positions.has(index+1)));
 }

 const text=match[1].match(/^текст\s+(со словами(?:\s+|$))?([\s\S]*)$/);
 if(text&&(text[1]||Object.hasOwn(quotePairs,text[2][0]??''))){
  const payload=text[2].trim();
  // Quoted slide references are literal text; unquoted scope is ambiguous.
  if(!Object.hasOwn(quotePairs,payload[0]??'')&&hasSlideScope(payload))return clarify();
  const query=literalQuery(payload);
  if(!query?.trim())return clarify([],'Укажите непустой текст в кавычках или после «со словами».');
  return single(elements.filter(element=>element.type==='text'&&normalize(element.text).includes(normalize(query))));
 }

 const spatial=target.match(/^(?:сам(?:ую|ый|ое)\s+)?(лев(?:ую|ый|ое)|прав(?:ую|ый|ое)|верхн(?:юю|ий|ее)|нижн(?:юю|ий|ее))\s+(фигуру|картинку|изображение|таблицу|заголовок)$/);
 if(spatial){
  const candidates=elements.filter(targetKinds[spatial[2]]);
  const direction=spatial[1];
  const horizontal=/^(?:лев|прав)/.test(direction),largest=/^(?:прав|нижн)/.test(direction);
  return extreme(candidates,element=>validBox(element)?element.box[horizontal?0:1]+(largest?element.box[horizontal?2:3]:0):NaN,largest);
 }
 if(target==='самый большой заголовок'){
  const candidates=elements.filter(isTitle);
  // Font size is comparable only if every title has one; otherwise all must omit it.
  const hasFont=candidates.some(element=>element.style?.size_pt!=null);
  return extreme(candidates,element=>hasFont
   ? typeof element.style?.size_pt==='number'&&element.style.size_pt>0?element.style.size_pt:NaN
   : validBox(element)?element.box[2]*element.box[3]:NaN,true);
 }

 // Recognized families with extra or malformed targets must not select a prefix.
 if(/^(?:весь|все)(?:\s|$)/.test(target)
  ||/^текст(?:\s+со словами|\s*[«"“„']|$)/.test(target)
  ||/^(?:сам(?:ую|ый|ое)\s+)?(?:лев(?:ую|ый|ое)|прав(?:ую|ый|ое)|верхн(?:юю|ий|ее)|нижн(?:юю|ий|ее))\s+(?:фигуру|картинку|изображение|таблицу|заголовок)(?:\s|[,.;:]|$)/.test(target)
  ||/^самый большой заголовок(?:\s|[,.;:]|$)/.test(target))return clarify();
 return null;
}
