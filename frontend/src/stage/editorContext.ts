import type {Document} from './voiceEditor';

/** Include explicitly named slides, never send the whole deck by default. */
export function contextPages(command:string,document:Document,pageId:string){
 const ids=new Set([pageId]);
 const ordinals=['перв','втор','трет','четверт','пят','шест','седьм','восьм','девят','десят'];
 const normalized=command.toLowerCase().replace(/ё/g,'е');
 for(const match of normalized.matchAll(/(?:слайд(?:е|а)?\s+(\d+)|\b(\d+)\s*[-–]?\s*(?:й|ый|ой|м)?\s+слайд|([а-я]+)\s+слайд)/g)){
  const n=match[1]||match[2]?Number(match[1]||match[2]):ordinals.findIndex(prefix=>match[3]?.startsWith(prefix))+1;
  if(n>0&&document.pages[n-1])ids.add(document.pages[n-1].id);
 }
 return document.pages.filter(p=>ids.has(p.id));
}
