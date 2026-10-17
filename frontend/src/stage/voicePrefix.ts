/** Распознавание закрывает фразу на короткой паузе: «Слайд… два» приходит двумя фразами.
 * Одиночное начало команды ждёт продолжения и склеивается со следующей фразой. */
const PREFIX=/^(слайд|выбери|выдели|образец|элемент|перейди на|перейди к)$/i;
export const PREFIX_WAIT_MS=4000;
export type PendingPrefix={text:string;at:number}|null;

export function joinPrefix(raw:string,pending:PendingPrefix,now:number):{text:string|null;pending:PendingPrefix}{
 const bare=raw.trim().replace(/[.!?…,;:]+$/,'');
 if(PREFIX.test(bare))return {text:null,pending:{text:bare,at:now}};
 if(pending&&now-pending.at<PREFIX_WAIT_MS){
  const rest=raw.trim();
  return {text:`${pending.text} ${rest.charAt(0).toLocaleLowerCase('ru')}${rest.slice(1)}`,pending:null};
 }
 return {text:raw,pending:null};
}
