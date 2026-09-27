import {parseDeckVoice, type DeckVoiceAction} from './deckVoice';
import {deckNumber} from './deckVoiceExtended';

export type LayoutOperation = 'alignLeft'|'alignRight'|'alignTop'|'alignBottom'|'alignCenterX'|'alignCenterY'|'distributeX'|'distributeY'|'sameWidth'|'sameHeight'|'sameSize';
export type LayoutVoiceAction = {kind:'layout';operation:LayoutOperation};
export type AtomicVoiceStep = Extract<DeckVoiceAction,{kind:'style'|'move'}> | LayoutVoiceAction;
export type VoiceOperation = DeckVoiceAction | LayoutVoiceAction | {kind:'macro';steps:AtomicVoiceStep[]} | {kind:'unsupported';text:string};
type Capability = {target:'none'|'single'|'selection';engine:'local'|'model';batch:boolean};
const local = (target:Capability['target']='none',batch=false):Capability => ({target,engine:'local',batch});

// Exhaustive capability registry: adding a parser kind also requires an execution policy.
export const VOICE_OPERATIONS = {
  style:local('selection',true), move:local('selection',true), layout:local('selection',true), macro:local('selection',true),
  semanticSelection:local(), background:local(), notes:local(), layer:local('single'), slideMove:local(),
  table:local('single'), deleteElement:local('single'), duplicateElement:local('single'), deselect:local(),
  repeat:local('selection'), next:local(), previous:local(), undo:local(), add:local(), copy:local(), delete:local(), cancel:local(),
  title:local(), textStart:local('single'), select:local(), element:local(), pattern:local(),
  text:local('single'), appendText:local('single'), ask:{target:'single',engine:'model',batch:false},
  addElement:local(), unknown:local(), unsupported:local(),
} satisfies Record<VoiceOperation['kind']|'semanticSelection',Capability>;

const layoutPhrases:ReadonlyArray<[RegExp,LayoutOperation]> = [
  [/^выровняй(?: (?:выделенные|выбранные)(?: элементы| объекты)?)? по левому краю$/, 'alignLeft'],
  [/^выровняй(?: (?:выделенные|выбранные)(?: элементы| объекты)?)? по правому краю$/, 'alignRight'],
  [/^выровняй(?: (?:выделенные|выбранные)(?: элементы| объекты)?)? по верхнему краю$/, 'alignTop'],
  [/^выровняй(?: (?:выделенные|выбранные)(?: элементы| объекты)?)? по нижнему краю$/, 'alignBottom'],
  [/^выровняй(?: элементы| объекты)? по центру по горизонтали$/, 'alignCenterX'],
  [/^выровняй(?: элементы| объекты)? по центру по вертикали$/, 'alignCenterY'],
  [/^(?:распредели(?: элементы| объекты)? равномерно по горизонтали|одинаковые отступы по горизонтали)$/, 'distributeX'],
  [/^(?:распредели(?: элементы| объекты)? равномерно по вертикали|одинаковые отступы по вертикали)$/, 'distributeY'],
  [/^(?:сделай (?:одинаковую ширину|ширину одинаковой)|одинаковая ширина)$/, 'sameWidth'],
  [/^(?:сделай (?:одинаковую высоту|высоту одинаковой)|одинаковая высота)$/, 'sameHeight'],
  [/^(?:сделай (?:одинаковый размер|размер одинаковым)|одинаковый размер)$/, 'sameSize'],
];
function layout(raw:string):LayoutVoiceAction|undefined {
  const phrase=raw.trim().toLowerCase().replace(/ё/g,'е').replace(/[.!?]+$/,'').replace(/\s+/g,' ');
  const found=layoutPhrases.find(([pattern])=>pattern.test(phrase));
  return found?{kind:'layout',operation:found[1]}:undefined;
}
function atomic(raw:string):AtomicVoiceStep|undefined {
  const structural=layout(raw);if(structural)return structural;
  const action=parseDeckVoice(raw);
  return (action.kind==='style'||action.kind==='move')&&action.slide===undefined&&action.elementNumber===undefined?action:undefined;
}

const quoted=/«[^»]*»|"[^"]*"|“[^”]*”|„[^“]*“/g;
function textRewrite(raw:string):boolean {
  let command=raw.toLowerCase().replace(/ё/g,'е').replace(quoted,'«target»').trim().replace(/[.!?]+$/,'');
  const scope=command.match(/\s+на (?:слайде (.+)|(.+) слайде)$/);
  if(scope){if(deckNumber(scope[1]??scope[2])===undefined)return false;command=command.slice(0,scope.index);}
  const explicit=/^(сократи|перепиши|перефразируй|измени|переведи|упрости|увеличь|уменьши|сделай)\s+(?:(?:этот|выбранный)\s+)?(?:текст заголовка|заголовок|текст)(?=\s|[,;]|$)/.exec(command);
  const addressed=/^(сократи|перепиши|измени|сделай) (?:текст )?(?:элемент|объект)(?:а)? (?:номер )?(.+?)(?:[,;:]|$)/.exec(command);
  const shorthand=/^(сократи|перепиши|короче|сделай)(?=\s|$)/.exec(command);
  const prefix=addressed??explicit??shorthand;if(!prefix)return false;
  if(addressed&&deckNumber(addressed[2])===undefined)return false;
  let tail=command.slice(prefix[0].length).trim();
  if(explicit&&!addressed){
    tail=tail.replace(/^«target»\s*/,'');
    const number=tail.replace(/^(?:номер |№\s*)/,'');
    if(deckNumber(number)!==undefined)tail='';
  }
  if(!tail)return !['сделай','измени','увеличь','уменьши'].includes(prefix[1]);
  const attribute='(?:числа|цифры|даты|смысл|факты|названия|термины)';
  const attributes=`${attribute}(?: и ${attribute})*`;
  const amount='(?:\\d+|одного|одной|двух|трех|четырех|пяти|шести|семи|восьми|девяти|десяти)';
  const clauses=[
    '(?:на )?(?:более |менее )?(?:короче|длиннее|яснее|понятнее|проще|официальнее|выразительнее|официальн(?:ый|ым)|понятн(?:ый|ым)|кратк(?:ий|им)|длинн(?:ый|ым))',
    `(?:до|на) ${amount} (?:%|процентов|слов|слова|слово|предложений|предложения|предложение|символов|строк)`,
    `(?:сохрани|не меняй) ${attributes}`, `${attributes} не меняй`, `без изменения ${attributes}`,
    'на (?:русский|английский|немецкий|французский|испанский)(?: язык)?',
  ].map(pattern=>new RegExp(`^(?:${pattern})(?=\\s|[,;]|$)`));
  // Consume the whole suffix; no successful prefix of a mixed layout/text request.
  while(tail){
    const next=tail.replace(/^(?:[,;:]\s*|и\s+)/,'');
    if(!next)return false;
    const clause=clauses.map(pattern=>pattern.exec(next)).find(Boolean);if(!clause)return false;
    tail=next.slice(clause[0].length).trim();
  }
  return true;
}

function macroParts(source:string):string[]|undefined {
  const closers:Record<string,string>={'«':'»','"':'"','“':'”','„':'“'};
  let closing:string|undefined;
  const mask=source.split('').map(char=>{
    if(closing){if(char===closing)closing=undefined;return '_';}
    if(Object.hasOwn(closers,char)){closing=closers[char];return '_';}
    return char;
  }).join('');
  if(closing)return;
  const parts:string[]=[];let start=0;
  for(const match of mask.matchAll(/\s*[,;]?\s+(?:а затем|затем|потом)\s+/gi)){
    parts.push(source.slice(start,match.index));start=match.index+match[0].length;
  }
  parts.push(source.slice(start));return parts;
}

export function parseVoiceOperation(raw:string):VoiceOperation {
  const source=raw.trim().replace(/^команда\s*[:,.!]?\s*/i,'');
  const action=parseDeckVoice(source);
  // Text payloads are opaque, even when they contain words such as "затем".
  if(['text','appendText','notes'].includes(action.kind)
    ||action.kind==='addElement'&&['title','text','card'].includes(action.elementType??'text')
    ||action.kind==='table'&&action.action==='table_cell')return action;
  const single=layout(source);if(single)return single;
  const parts=macroParts(source);
  if(!parts)return {kind:'unsupported',text:'Уточните границы цитируемого текста. Документ не изменён.'};
  if(parts.length>1){
    const steps=parts.map(atomic);
    if(parts.length<=6&&steps.every((step):step is AtomicVoiceStep=>!!step))return {kind:'macro',steps};
    return {kind:'unsupported',text:'Составная команда не поддерживается целиком. Документ не изменён.'};
  }
  if(action.kind==='addElement'&&action.text.trim())return {kind:'unsupported',text:'Параметры создаваемого объекта не распознаны. Документ не изменён.'};
  // Layout intents must never fall through to the text-rewrite model.
  if(action.kind==='ask'&&!textRewrite(action.text)){
    return {kind:'unsupported',text:'Для этой операции нет проверенного исполнителя. Документ не изменён.'};
  }
  return action;
}
