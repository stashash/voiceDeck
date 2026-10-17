import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {readFileSync} from 'node:fs';
import {DeckMeaning,routeDeckMeaningCommand,meaningInstructionHint,type DeckMeaningContext} from './deckMeaning';
import {DeckMeaningPanel} from './DeckMeaningPanel';

function context():DeckMeaningContext{return {deckId:'deck',variant:'a',index:0,selectedId:null,unsaved:'',active:{revision:'r1',status:'done',design_system_id:'light',plan:null,findings:[],error:null,scenes:[{slide_id:'s1',pattern_id:'p',variant:'a',theme:'light',elements:[{id:'t',type:'text',role:'title',text:'Рост 5%',box:[0,0,1,.2]},{id:'b',type:'text',role:'body',text:'Материал автора',box:[0,.2,1,.8]}]},{slide_id:'s2',pattern_id:'p',variant:'a',theme:'light',elements:[]}]}};}
function stubModel(extra:Record<string,unknown>={}){
 const fetch=vi.fn(async(_url,init)=>{const p=JSON.parse(init.body as string);return {ok:true,json:async()=>({main_idea:'Идея',explanation:'Объяснение',details:[],evidence:[{source_id:'s1',quote:'Рост 5%'}],caveats:[],recommendation:'update_current',slide_draft:null,verification:'requires_confirmation',slide_id:p.slide_id,version:p.version,...extra})} as Response;});
 vi.stubGlobal('fetch',fetch);return fetch;
}
afterEach(()=>vi.unstubAllGlobals());
describe('presentation meaning preview and application boundary',()=>{
 it('mounts the meaning affordance in the standard edit route and keeps voice controls',()=>{
  const source=readFileSync(new URL('../pages/EditPage.tsx',import.meta.url),'utf8');
  expect(source).toContain('<DeckMeaningPanel');expect(source).toContain('prepare=>guard(()=>commitDeckDictation');expect(source).toContain('aria-label="Голосовое редактирование"');
  const html=renderToStaticMarkup(<DeckMeaningPanel context={context()} disabled={false} onApply={async()=>false}/>);
  expect(html).toContain('Раскрытие смысла слайда');expect(html).toContain('Углубить мысль слайда');expect(html).toContain('aria-expanded="true"');expect(html).toContain('Проверьте цель правки ниже');expect(html).toContain('Автоматическая цель:');
  expect(source.indexOf('if(routeDeckMeaningCommand(raw')).toBeLessThan(source.indexOf('let resolved=parseVoiceOperation(raw)'));
  expect(source.indexOf('if(routeDeckMeaningCommand(raw')).toBeGreaterThan(source.indexOf('if(dictation.current){'));
 });
 it.each(['раскрой смысл: объясни механизм','Команда: раскрыть смысл слайда: объясни механизм','расширь смысл — объясни механизм'])('intercepts spoken/typed intent %s as preview without a direct rewrite or mutation',async raw=>{
  const fetch=stubModel(),m=new DeckMeaning(),c=context(),before=structuredClone(c),open=vi.fn(),rewrite=vi.fn();m.update(c);
  let requested:Promise<void>|undefined;
  if(!routeDeckMeaningCommand(raw,instruction=>{open();requested=m.request(instruction,()=>{});}))rewrite();
  await requested;
  expect(open).toHaveBeenCalledOnce();expect(rewrite).not.toHaveBeenCalled();expect(m.instruction).toBe('объясни механизм');expect(m.draft).toBeDefined();
  expect(c).toEqual(before);expect(fetch).toHaveBeenCalledOnce();expect(fetch.mock.calls[0][0]).toContain('/editor/meaning/expand');
 });
 it('shows a hint for a bare meaning intent and leaves other commands untouched',async()=>{
  const fetch=stubModel(),m=new DeckMeaning();m.update(context());let requested:Promise<void>|undefined;
  expect(routeDeckMeaningCommand('Раскрой смысл',instruction=>{requested=m.request(instruction,()=>{});})).toBe(true);
  await requested;expect(m.error).toBe(meaningInstructionHint);expect(m.draft).toBeUndefined();expect(fetch).not.toHaveBeenCalled();
  const preview=vi.fn();expect(routeDeckMeaningCommand('Добавь текст: раскрой смысл',preview)).toBe(false);expect(preview).not.toHaveBeenCalled();
 });
 it('requests a non-mutating draft with selected slide and neighbors; applies edited text only through explicit payload',async()=>{
  const fetch=stubModel(),m=new DeckMeaning(),c=context(),before=structuredClone(c);m.update(c);
  await m.request('Объясни механизм',()=>{});
  expect(m.error).toBe('');expect(c).toEqual(before);expect(fetch).toHaveBeenCalledTimes(1);
  const p=JSON.parse(fetch.mock.calls[0][1].body as string);
  expect(p.context.current_slide).toBe('s1');expect(p.context.sources.s1).toContain('Материал автора');expect(p.context.sources).toHaveProperty('s2');
  m.draft!.explanation='Исправлено автором';const payload=m.application();
  expect(payload).toMatchObject({element_id:'b',expected_revision:'r1',target_slide_id:'s1'});
  expect(payload.text).toContain('Требует подтверждения автора');expect(payload.text).toContain('Исправлено автором');expect(payload.text).toContain('Данные автора (s1)');
  expect(c).toEqual(before);m.reject();expect(m.draft).toBeUndefined();expect(()=>m.application()).toThrow();
 });
 it.each(['revision','navigation','variant','selection','unsaved'] as const)('blocks %s changes and navigation away/back',async kind=>{
  stubModel();const m=new DeckMeaning(),c=context();m.update(c);await m.request('Пример',()=>{});
  const next=structuredClone(c);
  if(kind==='revision')next.active.revision='r2';if(kind==='navigation')next.index=1;if(kind==='variant')next.variant='b';if(kind==='selection')next.selectedId='t';if(kind==='unsaved')next.unsaved='new notes';
  m.update(next);m.update(c);expect(m.stale).toBe(true);expect(()=>m.application()).toThrow('изменился');
 });
 it('rejects invented evidence, invalid fields, excessive text and unknown revision',async()=>{
  stubModel({evidence:[{source_id:'s1',quote:'invented'}]});const m=new DeckMeaning(),c=context();m.update(c);await m.request('пример',()=>{});expect(m.draft).toBeUndefined();expect(m.error).toContain('источник');
  stubModel();await m.request('пример',()=>{});m.draft!.main_idea='';expect(()=>m.application()).toThrow('Проверьте');
  m.draft!.main_idea='Идея';m.draft!.explanation='x'.repeat(1800);expect(()=>m.application()).toThrow('Слишком много');
  const n=new DeckMeaning();c.active.revision=null;n.update(c);await n.request('пример',()=>{});expect(()=>n.application()).toThrow('Версия');
 });
 it('requires an unambiguous text target and honors explicit selection',async()=>{
  const fetch=stubModel(),m=new DeckMeaning(),c=context();c.active.scenes[0].elements.push({...c.active.scenes[0].elements[1],id:'other'});m.update(c);await m.request('пример',()=>{});expect(m.error).toContain('Выберите один текстовый блок');expect(fetch).not.toHaveBeenCalled();
  c.selectedId='other';m.update(c);await m.request('пример',()=>{});expect(m.application().element_id).toBe('other');
 });
 it('ignores late model responses after context changes or rejection',async()=>{
  let release!:(value:Response)=>void;
  vi.stubGlobal('fetch',vi.fn((_url,init)=>new Promise<Response>(resolve=>{const p=JSON.parse(init.body as string);release=()=>resolve({ok:true,json:async()=>({main_idea:'Идея',explanation:'Текст',details:[],evidence:[],caveats:[],recommendation:'update_current',slide_draft:null,verification:'requires_confirmation',slide_id:p.slide_id,version:p.version})} as Response);})))
  const m=new DeckMeaning(),c=context();m.update(c);const request=m.request('Пример',()=>{});await vi.waitFor(()=>expect(release).toBeDefined());m.update({...c,index:1});release({} as Response);await request;expect(m.draft).toBeUndefined();expect(m.busy).toBe(false);
 });
});
