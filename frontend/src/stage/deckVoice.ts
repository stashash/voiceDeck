import {parseTextVoice} from './textVoice';
import {parseDeckExtended,deckNumber} from './deckVoiceExtended';
import type {DeckElementPayload} from '../designer/api';
export type DeckElementType='title'|'text'|'card'|'shape'|'image'|'table'|'chart';
export type DeckVoiceAction = ({kind:'style'} & Omit<DeckElementPayload,'action'>|{kind:'background';color:string}|{kind:'notes';text:string}|{kind:'layer';order:'front'|'back'}|{kind:'slideMove';number:number}|{kind:'table';action:'table_cell'|'table_row_add'|'table_row_delete'|'table_column_add'|'table_column_delete';row?:number;column?:number;text?:string}|{kind:'deleteElement'|'duplicateElement'|'deselect'}|{kind:'repeat';factor:number}|{kind:'move';dx:number;dy:number;align?:'left'|'right'|'top'|'bottom'|'center'}|{kind:'next'|'previous'|'undo'|'add'|'copy'|'delete'|'cancel'}|{kind:'title'}|{kind:'textStart'}|{kind:'select'|'element'|'pattern';number:number}|{kind:'text'|'appendText'|'ask'|'addElement'|'unknown';text:string;elementType?:DeckElementType;table?:DeckElementPayload['table']}) & {slide?:number;elementNumber?:number};
const numbers:Record<string,number>={один:1,одна:1,два:2,три:3,четыре:4,пять:5,шесть:6,семь:7,восемь:8,девять:9,десять:10,одиннадцать:11,двенадцать:12,тринадцать:13,четырнадцать:14,пятнадцать:15,шестнадцать:16,семнадцать:17,восемнадцать:18,девятнадцать:19,двадцать:20,тридцать:30};
const ordinals=['перв','втор','трет','четверт','пят','шест','седьм','восьм','девят','десят'];
function voiceNumber(s:string):number|undefined{
 const extended=deckNumber(s);if(extended!==undefined)return extended;
 if(/^\d+$/.test(s))return Number(s);
 if(numbers[s]!==undefined)return numbers[s];
 const parts=s.split(' ');if(parts.length===2&&numbers[parts[0]]>=20&&numbers[parts[1]]<10)return numbers[parts[0]]+numbers[parts[1]];
 const index=ordinals.findIndex(stem=>new RegExp(`^${stem}(ый|ой|ий|ом|ем|ую|ое)$`).test(s));return index<0?undefined:index+1;
}
export function parseDeckVoice(raw:string):DeckVoiceAction{
 raw=raw.trim().replace(/^команда\s*[:,.!]?\s*/i,'');
 const scopedAction=raw.match(/^на слайде? (.+?)[,;]?\s+((?:выбери|выдели|добавь|создай|замени|измени|напиши|запиши|сделай|шрифт|цвет|фон|удали|перемести|ширина|высота|заметки) .+)$/i)??raw.match(/^на (.+?) слайде[,;]?\s+(.+)$/i);
 if(scopedAction){const slide=voiceNumber(scopedAction[1].toLowerCase());if(slide!==undefined)return {...parseDeckVoice(scopedAction[2]),slide};return {kind:'unknown',text:raw};}
 const textAction=parseTextVoice(raw);if(textAction)return textAction;
 const addressed=raw.match(/^(?:выбери|выдели) (?:элемент )?(.+?)[,.;]\s+(.+)$/i);
 if(addressed){const elementNumber=voiceNumber(addressed[1].toLowerCase());const action=parseDeckVoice(addressed[2]);if(elementNumber!==undefined&&['style','move','deleteElement','duplicateElement','layer','table','text','appendText','textStart'].includes(action.kind))return {...action,elementNumber};return {kind:'unknown',text:raw};}
 const extended=parseDeckExtended(raw);if(extended)return extended;
 const s=raw.trim().replace(/[.!?]+$/,'').replace(/\s+/g,' ');const c=s.toLowerCase().replace(/ё/g,'е');
 if(/^(удали|убери)(?: (?:выбранный )?(?:элемент|объект|его))?$/.test(c))return {kind:'deleteElement'};
 if(/^(скопируй|дублируй) (?:выбранный )?(?:элемент|объект|его)$/.test(c))return {kind:'duplicateElement'};
 if(/^(сделай (?:текст )?крупнее|увеличь шрифт)$/.test(c))return {kind:'style',scale:1.15};
 if(/^(сделай (?:текст )?мельче|уменьши шрифт)$/.test(c))return {kind:'style',scale:1/1.15};
 const font=c.match(/^(?:размер (?:текста|шрифта)|шрифт) (.+)$/);
 if(font){const size=voiceNumber(font[1]);if(size!==undefined&&size>=6&&size<=144)return {kind:'style',size_pt:size};}
 const color=c.match(/^(?:сделай (?:текст )?|цвет текста )(красным|синим|зеленым|черным|белым|красный|синий|зеленый|черный|белый)$/);
 if(color)return {kind:'style',color:color[1].startsWith('крас')?'DC2626':color[1].startsWith('син')?'2563EB':color[1].startsWith('зел')?'16A34A':color[1].startsWith('чер')?'111111':'FFFFFF'};
 if(/^(еще|повтори|повтори перемещение)$/.test(c))return {kind:'repeat',factor:1};
 if(/^(еще немного|еще чуть-чуть|еще чуть)$/.test(c))return {kind:'repeat',factor:0.25};
 const small=c.match(/^(?:теперь )?(чуть|немного|чуть-чуть) (правее|левее|выше|ниже|вправо|влево|вверх|вниз)$/);
 if(small){const a=parseDeckVoice(small[2]);if(a.kind==='move')return {...a,dx:a.dx/4,dy:a.dy/4};}
 const move=c.match(/^(?:(?:перемести|подвинь|сдвинь|передвинь)(?: (?:элемент|его))? )?(вправо|влево|вверх|вниз|правее|левее|выше|ниже)(?: на (.+?)(?: пиксел(?:ь|я|ей))?)?$/);
 if(move){const amount=move[2]?voiceNumber(move[2]):20;if(amount!==undefined&&amount>0&&amount<=1280)return {kind:'move',dx:/вправо|правее/.test(move[1])?amount/1280:/влево|левее/.test(move[1])?-amount/1280:0,dy:/вниз|ниже/.test(move[1])?amount/720:/вверх|выше/.test(move[1])?-amount/720:0};}
 const align=c.match(/^(?:(?:перемести|подвинь|поставь|сдвинь)(?: (?:элемент|его))? )?(в центр|по центру|к левому краю|к правому краю|к верхнему краю|к нижнему краю)$/);
 if(align)return {kind:'move',dx:0,dy:0,align:({'в центр':'center','по центру':'center','к левому краю':'left','к правому краю':'right','к верхнему краю':'top','к нижнему краю':'bottom'} as const)[align[1] as 'в центр']};
 const compound=s.match(/^(?:выбери|выдели) (?:элемент )?(.+?)[,;]?\s+((?:поменяй|меняй|измени|замени|напиши|запиши|добавь) .+)$/i);
 if(compound){const elementNumber=voiceNumber(compound[1].toLowerCase().replace(/,$/,''));const action=parseDeckVoice(compound[2]);if(elementNumber!==undefined&&['text','appendText','textStart'].includes(action.kind))return {...action,elementNumber};}
 if(/^(?:(?:измени|поменяй|меняй|замени|редактируй|вставь|ставь) текст|диктую текст|текст)$/.test(c))return {kind:'textStart'};
 const append=s.match(/^(?:(?:измени|поменяй) текст[, ]+)?добавь в конец(?:\s+текста)?(?:\s+слова?)?\s+(.+)$/i)??s.match(/^(?:(?:измени|поменяй) текст[, ]+)?добавь в конце(?:\s+текста)?(?:\s+слова?)?\s+(.+)$/i);
 if(append)return {kind:'appendText',text:append[1].replace(/^[«"]|[»"]$/g,'')};
 const replacement=raw.trim().match(/^(?:(?:замени|измени|поменяй|меняй) текст (?:на|:)|(?:вставь|ставь) текст[.:]?|запиши|напиши)\s*(.+)$/i);
 if(replacement)return {kind:'text',text:replacement[1].trim().replace(/^[«"]|[»"]$/g,'')};
 // Resolve an explicit slide before resolving its element. Keep dictated text intact.
 const scoped=s.match(/^на слайд[е]? (.+?)(?:,?\s+)((?:выбери|выдели|добавь|замени|напиши|запиши) .+)$/i)??s.match(/^на (.+?) слайде[, ]+((?:выбери|выдели|добавь|замени|напиши|запиши) .+)$/i);
 if(scoped){const slide=voiceNumber(scoped[1].toLowerCase().replace(/ё/g,'е'));if(slide!==undefined)return {...parseDeckVoice(scoped[2]),slide};}
 if(/^(?:выбери|выдели|покажи) (?:основной )?заголовок$/.test(c))return {kind:'title'};
 const slidePhrase=c.replace(/^(?:(?:выбери|открой|покажи|переключись на|перейди на|перейди к) |на )/,'');
 const slideMatch=slidePhrase.match(/^слайд[уе]? (?:номер )?(.+)$/)??slidePhrase.match(/^(.+) слайд[е]?$/);
 if(slideMatch){const number=voiceNumber(slideMatch[1]);if(number!==undefined)return {kind:'select',number};}
 const selection=c.replace(/^(?:выбери|выдели|покажи|открой) /,'').replace(/^(?:элемент |объект |номер )(?:номер )?/,'').replace(/ (?:элемент|объект)$/,'');
 const selectedNumber=voiceNumber(selection);if(selectedNumber!==undefined)return {kind:'element',number:selectedNumber};
 const map:Record<string,DeckVoiceAction['kind']>={'следующий':'next','следующий слайд':'next','на следующий слайд':'next','перейди на следующий слайд':'next','перейди вперед':'next','перейди вперёд':'next','вперед':'next','вправо':'next','дальше':'next','предыдущий':'previous','предыдущий слайд':'previous','на предыдущий слайд':'previous','перейди на предыдущий слайд':'previous','перейди назад':'previous','назад':'previous','влево':'previous','отмени':'undo','отмена':'undo','отменить правку':'undo','новый слайд':'add','добавь слайд':'add','создай слайд':'add','скопируй слайд':'copy','дублируй слайд':'copy','удали слайд':'delete','удали текущий слайд':'delete','стоп':'cancel','остановись':'cancel'};
 if(map[c])return {kind:map[c]} as DeckVoiceAction;
 const nums:Record<string,number>={'один':1,'два':2,'три':3,'четыре':4,'пять':5,'шесть':6,'семь':7,'восемь':8,'девять':9,'десять':10};
 const add=c.match(/^на (?:слайде|слайд) (\d+|один|два|три|четыре|пять|шесть|семь|восемь|девять|десять) добавь (заголовок|текст|карточку|фигуру|изображение|таблицу|диаграмму)(?:\s+(.+))?$/);
 const addCurrent=c.match(/^добавь (заголовок|текст|карточку|фигуру|изображение|таблицу|диаграмму)(?:\s+(.+))?$/);
 const addMatch=add??addCurrent;
 if(addMatch){const type={'заголовок':'title','текст':'text','карточку':'card','фигуру':'shape','изображение':'image','таблицу':'table','диаграмму':'chart'}[addMatch[add?'2':'1']] as DeckElementType;return {kind:'addElement',elementType:type,text:addMatch[add?'3':'2']??'',slide:add?nums[addMatch[1]]??Number(addMatch[1]):undefined};}
 const shortElement=c.match(/^(?:выбери|открой|покажи) (\d+|один|два|три|четыре|пять|шесть|семь|восемь|девять|десять)$/);
 if(shortElement)return {kind:'element',number:nums[shortElement[1]]??Number(shortElement[1])};
 const m=c.match(/^(?:(?:выбери|открой|покажи) )?(слайд|элемент|образец)(?: номер)? (\d+|один|два|три|четыре|пять|шесть|семь|восемь|девять|десять)$/) ?? c.match(/^перейди (?:к|на) (слайду?|элементу?|образцу?)(?: номер)? (\d+|один|два|три|четыре|пять|шесть|семь|восемь|девять|десять)$/);
 if(m)return {kind:m[1].startsWith('слайд')?'select':m[1].startsWith('элемент')?'element':'pattern',number:nums[m[2]]??Number(m[2])};
 const text=s.match(/^(?:запиши|замени текст на|напиши)\s+(.+)$/i);if(text)return {kind:'text',text:text[1]};
 if(/^(?:выбери|выдели|перейди|открой|покажи|на слайд|слайд)/.test(c))return {kind:'unknown',text:s};
 return {kind:/^(?:сократи|сделай|перепиши|измени|замени|увеличь|уменьши|добавь|убери|удали|перемести|перекрась|выровняй|расположи|оформи|короче|вынести)(?:\s|$)/.test(c)?'ask':'unknown',text:s};
}
