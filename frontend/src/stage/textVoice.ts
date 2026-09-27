import {voiceNumber} from './voiceVocabulary';

export type TextVoiceAction=({kind:'textStart'}|{kind:'text'|'appendText';text:string})&{elementNumber?:number};
const unquote=(s:string)=>s.trim().replace(/^[«"“]|[»"”]$/g,'');

/** ASR can put the selection, command and dictated value in a single sentence. */
export function parseTextVoice(raw:string):TextVoiceAction|undefined{
 const s=raw.trim().replace(/^команда\s*[:,.!]?\s*/i,'');
 const compound=s.match(/^(?:(?:выбери|выдели)\s+)?(?:(?:элемент|номер)\s+)?(.+?)[.!?,;:]?\s+((?:измени|поменяй|меняй|замени|редактируй|вставь|ставь|запиши|напиши)\s+.+)$/i);
 if(compound){
  const elementNumber=voiceNumber(compound[1]);
  if(elementNumber!==undefined){const action=parseTextVoice(compound[2]);if(action)return {...action,elementNumber};}
 }
 const append=s.match(/^(?:(?:измени|поменяй) текст[,. :]+)?добавь в (?:конец|конце)(?:\s+текста)?(?:\s+слова?)?\s+(.+)$/i);
 if(append)return {kind:'appendText',text:unquote(append[1])};
 if(/^(?:(?:измени|поменяй|меняй|замени|редактируй|вставь|ставь) текст|текст)[.!?,:;]*$/i.test(s))return {kind:'textStart'};
 const replacement=s.match(/^(?:замени|измени|поменяй|меняй|редактируй) текст(?:\s+на\s*|\s*[.!?,:;]\s*)(.+)$/i)
  ??s.match(/^(?:(?:вставь|ставь) текст[.:]?|запиши|напиши)\s+(.+)$/i);
 if(replacement)return {kind:'text',text:unquote(replacement[1])};
}
