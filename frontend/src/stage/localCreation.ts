import type {Operation} from './editorOperations';

const kinds={заголовок:'title',текст:'text',карточку:'card',фигуру:'shape',прямоугольник:'shape',изображение:'image'} as const;
const counts:Record<string,number>={две:2,три:3,четыре:4};
const literal=(s:string)=>/^(?:«[^»]*»|"[^"]*")$/.test(s.trim());
const text=(s:string)=>literal(s)?s.trim().slice(1,-1):s.trim();
export const ambiguousContent=(s:string)=>!literal(s)&&(/\s(?:и|затем|потом)\s|[.!?;]\s+\S/i.test(s)||/[«»"]/.test(s));

/** Returns a complete plan or nothing: no successful prefix-only execution. */
export function localCreation(raw:string):Operation[]|undefined{
 const compound=raw.match(/^(?:добавь|создай) заголовок (.+?) и (две|три|четыре|[2-4]) карточки\s*:\s*(.+)$/i);
 if(compound){
  if(ambiguousContent(compound[1]))return;
  const cards=localCreation(`создай ${compound[2]} карточки: ${compound[3]}`);
  return cards?[{op:'add',props:{kind:'title',text:text(compound[1])}},...cards]:undefined;
 }
 const cards=raw.match(/^(?:добавь|создай) (две|три|четыре|[2-4]) карточки(?:\s*:\s*(.+))?$/i);
 if(cards){
  const n=Number(cards[1])||counts[cards[1].toLowerCase()];
  const names=cards[2]?.split(/\s*;\s*|\s*,\s*|\s+и\s+/i);
  if(names&&(names.length!==n||names.some(s=>!s.trim()||ambiguousContent(s))))return;
  return Array.from({length:n},(_,i)=>({op:'add',props:{kind:'card',text:names?text(names[i]):`Карточка ${i+1}`,x:64+i*1152/n,y:220,width:1152/n-24,height:280}}));
 }
 const table=raw.match(/^(?:добавь|создай) таблицу (\d+) на (\d+)$/i);
 if(table){const rows=Number(table[1]),cols=Number(table[2]);if(rows<1||rows>20||cols<1||cols>12)return;return [{op:'add',props:{kind:'table',rows:Array.from({length:rows},()=>Array(cols).fill('')),width:900,height:Math.min(450,rows*48)}}];}
 const create=raw.match(/^(?:добавь|создай) (заголовок|текст|карточку|фигуру|прямоугольник|изображение)(?:\s+(.+))?$/i);
 if(create&&!ambiguousContent(create[2]??''))return [{op:'add',props:{kind:kinds[create[1].toLowerCase() as keyof typeof kinds],text:text(create[2]??'')}}];
}
