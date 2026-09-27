import type {DeckVoiceAction} from './deckVoice';
import {voiceNumber,normalizeVoice} from './voiceVocabulary';

export function deckNumber(raw:string):number|undefined {
 const s=normalizeVoice(raw).replace(/(?:ом|ем)$/,'ый');
 const known=voiceNumber(s);if(known!==undefined)return known;
 const hundreds:Record<string,number>={сто:100,двести:200,триста:300,четыреста:400,пятьсот:500,шестьсот:600,семьсот:700,восемьсот:800,девятьсот:900,тысяча:1000};
 const [head,...tail]=s.split(' ');if(hundreds[head]!==undefined){const rest=tail.length?voiceNumber(tail.join(' ')):0;if(rest!==undefined&&rest<100)return hundreds[head]+rest;}
}
const unquote=(s:string)=>s.trim().replace(/^[«"“]|[»"”]$/g,'');
function color(raw:string):string|undefined {
 const s=normalizeVoice(raw).replace(/^#/,'');if(/^[a-f0-9]{6}$/.test(s))return s.toUpperCase();
 const colors:Record<string,string>={красн:'DC2626',син:'2563EB',зелен:'16A34A',черн:'111111',бел:'FFFFFF',желт:'FACC15',сер:'9CA3AF',фиолетов:'9333EA',оранжев:'EA580C'};
 return Object.entries(colors).find(([stem])=>new RegExp(`^${stem}(ый|ий|ой|ая|яя|ым|им|ую|юю)$`).test(s))?.[1];
}

/** Structural commands only: literal values retain their original case and punctuation. */
export function parseDeckExtended(raw:string):DeckVoiceAction|undefined {
 const s=raw.trim().replace(/^команда\s*[:,.!]?\s*/i,'');
 const c=normalizeVoice(s).replace(/[.!?]+$/,'');
 const notes=s.match(/^(?:заметки(?: докладчика)?|запиши в заметки|измени заметки на)\s*[:]?\s+(.+)$/i);
 if(notes)return {kind:'notes',text:unquote(notes[1])};
 if(/^(?:очисти|удали) заметки(?: докладчика)?$/.test(c))return {kind:'notes',text:''};
 if(/^(?:сними выделение|ничего не выбирай)$/.test(c))return {kind:'deselect'};
 if(/^(?:сделай (?:текст )?жирным|жирный(?: текст)?|полужирный)$/.test(c))return {kind:'style',bold:true};
 if(/^(?:убери жирность|нежирный|обычный шрифт)$/.test(c))return {kind:'style',bold:false};
 if(/^(?:курсив|сделай (?:текст )?курсивом)$/.test(c))return {kind:'style',italic:true};
 if(/^(?:убери курсив|без курсива)$/.test(c))return {kind:'style',italic:false};
 const align=c.match(/^(?:выровняй )?текст (по центру|по левому краю|по правому краю)$/);
 if(align)return {kind:'style',text_align:align[1]==='по центру'?'center':align[1]==='по левому краю'?'left':'right'};
 const font=c.match(/^(?:размер (?:текста|шрифта)|шрифт)(?: на)? (.+)$/);
 if(font){const n=deckNumber(font[1]);return n!==undefined&&n>=6&&n<=144?{kind:'style',size_pt:n}:{kind:'unknown',text:s};}
 const dimension=c.match(/^(?:сделай |установи )?(ширин[ау]|высот[ау])(?: элемента| объекта)? (.+?)(?: пиксел(?:ь|я|ей))?$/);
 if(dimension){const n=deckNumber(dimension[2]),width=dimension[1].startsWith('шир');return n!==undefined&&n>=20&&n<=(width?1280:720)?{kind:'style',...(width?{width:n/1280}:{height:n/720})}:{kind:'unknown',text:s};}
 const paint=c.match(/^(?:(?:сделай |измени )?фон(?: слайда)?(?: на)?|заливка|цвет фигуры|цвет текста|покрась (?:текст|фигуру) в) (.+)$/);
 if(paint){const hex=color(paint[1]);if(!hex)return {kind:'unknown',text:s};return /фон/.test(c)?{kind:'background',color:hex}:{kind:'style',...(/заливка|фигуры|фигуру/.test(c)?{fill:hex}:{color:hex})};}
 const layer=c.match(/^(?:(?:перенеси|перемести|подними|опусти)(?: (?:элемент|объект|его))? )?на (передний|задний) план$/);
 if(layer)return {kind:'layer',order:layer[1]==='передний'?'front':'back'};
 const reorder=c.match(/^(?:перемести|перенеси) слайд(?: на место| на позицию| на)? (.+)$/);
 if(reorder){const n=deckNumber(reorder[1]);return n!==undefined&&n>0?{kind:'slideMove',number:n}:{kind:'unknown',text:s};}
 const cell=s.match(/^(?:измени |запиши в )?ячейк[ау]\s+(.+?)[, ]+\s*(.+?)(?:\s+на\s+|\s*:\s*)(.+)$/i);
 if(cell){const row=deckNumber(cell[1]),column=deckNumber(cell[2]);return row!==undefined&&row>=1&&column!==undefined&&column>=1?{kind:'table',action:'table_cell',row:row-1,column,text:unquote(cell[3])}:{kind:'unknown',text:s};}
 const table=c.match(/^(добавь|удали) (строку|столбец)(?: таблицы)?(?: (.+))?$/);
 if(table){const n=table[3]?deckNumber(table[3]):undefined;const row=table[2]==='строку';if(table[3]&&(n===undefined||n<(row?2:1))||table[1]==='удали'&&n===undefined)return {kind:'unknown',text:s};return {kind:'table',action:`table_${row?'row':'column'}_${table[1]==='добавь'?'add':'delete'}`,...(row?{row:n===undefined?undefined:n-1}:{column:n})};}
 const add=s.match(/^(?:добавь|создай) (заголовок|текст|карточку|фигуру|прямоугольник|таблицу)(?:\s+(.+))?$/i);
 if(add){const types={заголовок:'title',текст:'text',карточку:'card',фигуру:'shape',прямоугольник:'shape',таблицу:'table'} as const;const type=types[add[1].toLowerCase() as keyof typeof types];
  if(type==='table'&&add[2]){const sizes=normalizeVoice(add[2]).replace(/[.!?]+$/,'').match(/^(.+?) (?:на|x|×) (.+)$/);if(!sizes)return {kind:'unknown',text:s};const rows=deckNumber(sizes[1]),columns=deckNumber(sizes[2]);if(rows===undefined||columns===undefined||rows<1||rows>8||columns<1||columns>5)return {kind:'unknown',text:s};return {kind:'addElement',elementType:type,text:'',table:{columns:Array.from({length:columns},(_,i)=>`Столбец ${i+1}`),rows:Array.from({length:rows-1},()=>Array(columns).fill(''))}};}
  return {kind:'addElement',elementType:type,text:unquote(add[2]??'')};
 }
}
