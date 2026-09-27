export type DictationDraft={slide:number;slideId:string;id:string;revision:string;text:string};
export type DictationChange={kind:'draft';text:string}|{kind:'finish'}|{kind:'cancel'};
export function editDictation(text:string,raw:string):DictationChange{
  const phrase=raw.trim(),command=phrase.toLowerCase().replace(/[.!?]+$/,'');
  const literal=phrase.match(/^(?:буквально|запиши буквально)\s+([\s\S]+)$/i);
  const append=(value:string)=>({kind:'draft' as const,text:text+(text&&!/\s$/.test(text)?' ':'')+value});
  if(literal)return append(literal[1]);
  if(/^(?:готово|закончи диктовку|сохрани диктовку)$/.test(command))return {kind:'finish'};
  if(/^(?:отмена диктовки|отмени диктовку)$/.test(command))return {kind:'cancel'};
  if(command==='новый абзац')return {kind:'draft',text:text.trimEnd()+'\n\n'};
  if(command==='новая строка')return {kind:'draft',text:text.trimEnd()+'\n'};
  if(command==='удали последнее слово')return {kind:'draft',text:text.trimEnd().replace(/\S+\s*$/,'').trimEnd()};
  const correction=phrase.match(/^исправь последнее слово на\s+([\s\S]+)$/i);
  if(correction)return {kind:'draft',text:text.trimEnd().replace(/\S+\s*$/,'')+correction[1]};
  return append(phrase);
}
