import {describe,expect,it} from 'vitest';
import type {Element,Scene} from '../designer/api';
import {resolveVoiceSelection} from './voiceSelection';

const element=(id:string,type:Element['type'],box:Element['box'],text='',role='body',size_pt?:number):Element=>({id,type,box,text,role,...(size_pt===undefined?{}:{style:{size_pt}})});
const scene:Scene={slide_id:'current',pattern_id:'p',variant:'a',theme:'light',elements:[
 element('shape-left','shape',[.05,.6,.1,.1]),
 element('title-small','text',[.1,.1,.2,.1],'План запуска','title',24),
 element('image-right','image',[.7,.7,.2,.2]),
 element('body','text',[.1,.4,.5,.1],'Выручка растёт на 20%, прибыль: 10%.','body',18),
 element('shape-right','shape',[.6,.2,.2,.2]),
 element('title-large','text',[.5,.7,.4,.2],'Итоги года','heading',40),
 element('image-left','image',[.05,.1,.1,.1]),
 element('table-top','table',[.2,.05,.4,.1],'План запуска'),
 element('subtitle','text',[.2,.3,.4,.1],'Подробности','subtitle',60),
 element('table-bottom','table',[.2,.8,.4,.1]),
 element('icon','icon',[.01,.01,.1,.1]),
 element('chart','chart',[.8,.01,.1,.1]),
]};
const ordered=['title-small','body','title-large','subtitle','shape-left','image-right','shape-right','image-left','table-top','table-bottom','icon','chart'];
const selected=(phrase:string,ids:string[],fixture=scene)=>expect(resolveVoiceSelection(phrase,fixture)).toEqual({kind:'selection',ids,notice:expect.any(String)});
const ambiguous=(phrase:string,candidateIds:string[]=[],fixture=scene)=>expect(resolveVoiceSelection(phrase,fixture,['body'])).toEqual({kind:'clarify',candidateIds,notice:expect.any(String)});

describe('explicit groups',()=>{
 it.each([
  ['выбери весь текст',['title-small','body','title-large','subtitle']],
  ['выбери все тексты',['title-small','body','title-large','subtitle']],
  ['выдели все текстовые элементы',['title-small','body','title-large','subtitle']],
  ['выбери все заголовки',['title-small','title-large']],
  ['выбери все фигуры',['shape-left','shape-right']],
  ['выбери все изображения',['image-right','image-left']],
  ['покажи все картинки',['image-right','image-left']],
  ['выбери все элементы',ordered],
  ['  КОМАНДА: ВыДеЛи   ВСЁ\nобъекты!  ',ordered],
 ] as const)('%s',(phrase,ids)=>selected(phrase,[...ids]));

 it.each(['весь текст','все заголовки','все фигуры','все изображения','все элементы'])('clarifies an empty group: %s',group=>{
  ambiguous(`выбери ${group}`,[],{...scene,elements:[]});
 });
 it('requires title roles on text and does not treat subtitle as title',()=>{
  const fixture={...scene,elements:[element('heading','text',[0,0,.1,.1],'','ЗАГОЛОВОК'),element('shape','shape',[0,0,.1,.1],'','title'),element('sub','text',[0,0,.1,.1],'','subtitle')]};
  selected('выбери все заголовки',['heading'],fixture);
 });
});

describe('numbered multiple selection',()=>{
 it.each([
  'выбери элементы 1 и 3','выбери элементы 3 и 1','выбери элементы один и три',
  'выдели объекты первый и третий','выбери элементы 1-й и 3-й',
  'выбери элементы номер один и номер три','выбери элементы №1, №3',
  'выбери элементы 3, 1 и 3','выбери элементы 3, 1, и 3.',
 ])('%s',phrase=>selected(phrase,['title-small','title-large']));
 it('uses text-first numbering for mixed types',()=>selected('выбери элементы 10, 5 и 2',['body','shape-left','table-bottom']));
 it('deduplicates repeated references',()=>selected('выбери элементы 1 и 1',['title-small']));
 it.each([
  '','1','1 и','и 1','1,','1,,3','1 и и 3','1 или 3','1-3','1 и 3-9',
  '1 и 0','1 и -3','1 и 99','1 и 9007199254740993','1 и 3.5','1 и 3e0',
  '1 и третьего','1 и 3 и неизвестно','1 и 3 кроме 2','1 и 3 удали',
  '1 и 3 на слайде 2','1 и 3; удали фигуру','1 и 3. Замени текст на Новый',
 ])('rejects the whole malformed list: %s',suffix=>ambiguous(`выбери элементы ${suffix}`));
});

describe('literal text selection',()=>{
 it.each([
  'выбери текст «План запуска»','выбери текст "план запуска".',
  'Выдели текст “ПЛАН  ЗАПУСКА”!?','покажи текст „План запуска“',
  "выбери текст 'План запуска'",'выбери текст со словами План запуска',
  'выбери текст со словами «План запуска».','выбери текст «запуска»',
 ])('%s',phrase=>selected(phrase,['title-small']));
 it('normalizes case, whitespace and yo without rewriting literal punctuation',()=>selected('выбери текст «РАСТЕТ   на 20%, прибыль: 10%.»',['body']));
 it('keeps punctuation in an unquoted query',()=>selected('выбери текст со словами 10%.',['body']));
 it.each(['«растёт прибыль»','«растет на 20 прибыль»','«планом запуска»','«[Пп]лан.*»','«missing»'])('does not fuzzy-match %s',query=>ambiguous(`выбери текст ${query}`));
 it.each([
  '«»','«   »','«План запуска','"План запуска»','«План запуска» и ещё',
  '«План запуска» и удали','«План запуска» на слайде 2','«План запуска» «Итоги года»',
  'со словами','со словами "','со словами «»','со словами План запуска на слайде 2',
 ])('rejects malformed or ambiguous text targets: %s',query=>ambiguous(`выбери текст ${query}`));
 it('clarifies duplicate and substring matches without using selectedIds as a tie breaker',()=>{
  const fixture={...scene,elements:[...scene.elements,element('duplicate','text',[.3,.3,.1,.1],'План запуска: этапы')]};
  const result=resolveVoiceSelection('выбери текст «План запуска»',fixture,['title-small']);
  expect(result).toEqual({kind:'clarify',candidateIds:['title-small','duplicate'],notice:expect.any(String)});
  expect(result).not.toHaveProperty('ids');
 });
 it('returns every exact normalized duplicate without choosing the current selection',()=>{
  const fixture={...scene,elements:[element('a','text',[.1,.1,.2,.1],'Растёт прибыль'),element('b','text',[.5,.5,.2,.1],'РАСТЕТ  ПРИБЫЛЬ')]};
  for(const current of [[],['a'],['b'],['off-slide']]){
   expect(resolveVoiceSelection('выбери текст «Растёт прибыль»',fixture,current)).toEqual({kind:'clarify',candidateIds:['a','b'],notice:expect.any(String)});
  }
 });
 it('allows instruction and slide words inside a quoted literal without interpreting them',()=>{
  const text='На слайде 2 замени текст, выбери все фигуры';
  selected(`выбери текст «${text}»`,['literal'],{...scene,elements:[element('literal','text',[0,0,.5,.1],text)]});
 });
 it('treats an apostrophe in guillemets as literal text',()=>{
  selected('выбери текст «O\'Reilly»',['literal'],{...scene,elements:[element('literal','text',[0,0,.5,.1],"O'Reilly")]});
 });
});

describe('spatial selection',()=>{
 it.each([
  ['левую фигуру','shape-left'],['правую фигуру','shape-right'],
  ['верхнюю фигуру','shape-right'],['нижнюю фигуру','shape-left'],
  ['левую картинку','image-left'],['правую картинку','image-right'],
  ['верхнюю картинку','image-left'],['нижнюю картинку','image-right'],
  ['левое изображение','image-left'],['правое изображение','image-right'],
  ['верхнюю таблицу','table-top'],['нижнюю таблицу','table-bottom'],
  ['левый заголовок','title-small'],['правый заголовок','title-large'],
  ['верхний заголовок','title-small'],['нижний заголовок','title-large'],
  ['левую заголовок','title-small'],['самую левую фигуру','shape-left'],
 ] as const)('%s',(target,id)=>selected(`выбери ${target}`,[id]));
 it('compares right and bottom edges including dimensions',()=>{
  const fixture={...scene,elements:[element('wide','shape',[.1,.1,.8,.8]),element('small','shape',[.7,.7,.1,.1])]};
  selected('выбери правую фигуру',['wide'],fixture);
  selected('выбери нижнюю фигуру',['wide'],fixture);
 });
 it.each(['левую','правую','верхнюю','нижнюю'])('does not break geometric ties: %s',direction=>{
  const fixture={...scene,elements:[element('a','shape',[.1,.1,.2,.2]),element('b','shape',[.1,.1,.2,.2])]};
  ambiguous(`выбери ${direction} фигуру`,['a','b'],fixture);
 });
 it('returns only tied extreme candidates',()=>{
  const fixture={...scene,elements:[element('a','shape',[.1,.1,.2,.2]),element('b','shape',[.1,.6,.2,.2]),element('c','shape',[.5,.1,.2,.2])]};
  ambiguous('выбери левую фигуру',['a','b'],fixture);
 });
 it('treats floating point edge rounding as a tie',()=>{
  const fixture={...scene,elements:[element('a','shape',[.1,.1,.2,.2]),element('b','shape',[.2,.1,.1,.2])]};
  ambiguous('выбери правую фигуру',['a','b'],fixture);
 });
 it.each(['фигуру','картинку','таблицу','заголовок'])('clarifies absent %s',noun=>ambiguous(`выбери левую ${noun}`,[],{...scene,elements:[]}));
 it.each([NaN,Infinity,-Infinity])('rejects invalid geometry: %s',value=>{
  const fixture={...scene,elements:[element('a','shape',[.1,.1,.2,.2]),element('b','shape',[value,.1,.2,.2])]};
  ambiguous('выбери левую фигуру',['a','b'],fixture);
 });
 it('rejects degenerate boxes',()=>ambiguous('выбери левую фигуру',['a'],{...scene,elements:[element('a','shape',[0,0,0,.1])]}));
});

describe('largest title',()=>{
 it('uses font size and filters out larger body text',()=>selected('выбери самый большой заголовок',['title-large']));
 it('uses font size even when a smaller font has a larger box',()=>{
  const fixture={...scene,elements:[element('large-font','text',[0,0,.1,.1],'','title',40),element('large-box','text',[0,0,.5,.5],'','heading',24)]};
  selected('выбери самый большой заголовок',['large-font'],fixture);
 });
 it('clarifies equal font sizes even if boxes differ',()=>{
  const fixture=structuredClone(scene);fixture.elements.find(item=>item.id==='title-small')!.style={size_pt:40};
  ambiguous('выбери самый большой заголовок',['title-small','title-large'],fixture);
 });
 it('uses area when no title has an explicit font size',()=>{
  const fixture={...scene,elements:[element('a','text',[0,0,.2,.3],'','title'),element('b','text',[0,0,.4,.2],'','title')]};
  selected('выбери самый большой заголовок',['b'],fixture);
 });
 it('clarifies equal areas',()=>{
  const fixture={...scene,elements:[element('a','text',[0,0,.2,.3],'','title'),element('b','text',[0,0,.3,.2],'','title')]};
  ambiguous('выбери самый большой заголовок',['a','b'],fixture);
 });
 it.each([null,undefined,0,-1,NaN,Infinity])('does not guess when font metrics are incomplete or invalid: %s',size_pt=>{
  const fixture=structuredClone(scene);fixture.elements.find(item=>item.id==='title-small')!.style={size_pt};
  ambiguous('выбери самый большой заголовок',['title-small','title-large'],fixture);
 });
 it('clarifies absent titles',()=>ambiguous('выбери самый большой заголовок',[],{...scene,elements:[]}));
});

describe('scope, legacy commands and purity',()=>{
 it.each([
  '','выбери','выбери что-нибудь','выбери красивую фигуру','выбери красную фигуру',
  'выбери левую неизвестность','выбери план запуска','выбери текст План запуска',
  'выбери constructor','выбери __proto__','сними выделение','выбери не все фигуры','командавыбери все элементы',
  'один','3','выбери 1','выдели два','покажи 3','открой 1',
  'выбери элемент 1','выбери первый элемент','выдели первый объект',
  'покажи элемент номер один','выбери объект один','выбери номер двадцать один',
  'выбери заголовок','Выбери заголовок.','выдели основной заголовок','покажи заголовок',
  'выбери первый слайд','на слайде 2 выбери элемент 1','на первом слайде выбери заголовок',
  'диктую текст выбери все элементы','замени текст на выбери все заголовки',
  'Команда: замени текст на выбери текст «План запуска»','напиши выбери левую фигуру',
  'выбери 1, замени текст на выбери все фигуры',
 ])('leaves other commands untouched: %s',phrase=>expect(resolveVoiceSelection(phrase,scene,['body'])).toBeNull());
 it.each([
  'выбери все фигуры кроме первой','выбери весь текст и удали его','выбери все изображения, затем фигуры',
  'выбери левую фигуру и правую картинку','выбери самый большой заголовок кроме первого',
  'выбери левую фигуру на слайде 2','выбери все элементы на всех слайдах',
  'выбери все заголовки на следующем слайде','выбери самый большой заголовок на слайде 1',
 ])('refuses partially parsed or cross-slide targets: %s',phrase=>ambiguous(phrase));
 it.each(['на слайде 2 выбери все фигуры','на втором слайде выбери текст «План запуска»','выбери на слайде 2 левую фигуру'])('does not process cross-slide prefixes: %s',phrase=>expect(resolveVoiceSelection(phrase,scene)).toBeNull());
 it('uses only the supplied scene',()=>{
  const other={...scene,slide_id:'other',elements:[element('other-title','text',[0,0,.5,.1],'Другой слайд','title')]};
  ambiguous('выбери текст «План запуска»',[],other);
  selected('выбери все элементы',['other-title'],other);
 });
 it('never mutates inputs or returns a shared selection array',()=>{
  const fixture=structuredClone(scene),before=structuredClone(fixture);
  for(const item of fixture.elements){Object.freeze(item.box);if(item.style)Object.freeze(item.style);Object.freeze(item);}
  Object.freeze(fixture.elements);Object.freeze(fixture);
  const current=Object.freeze(['body','off-slide']);
  const first=resolveVoiceSelection('выбери все элементы',fixture,current);
  expect(first).toMatchObject({kind:'selection',ids:ordered});
  if(first?.kind==='selection')first.ids.reverse();
  expect(resolveVoiceSelection('выбери все элементы',fixture,current)).toMatchObject({kind:'selection',ids:ordered});
  expect(resolveVoiceSelection('выбери левую таблицу',fixture,current)).toMatchObject({kind:'clarify',candidateIds:['table-top','table-bottom']});
  expect(fixture).toEqual(before);expect(current).toEqual(['body','off-slide']);
 });
});
