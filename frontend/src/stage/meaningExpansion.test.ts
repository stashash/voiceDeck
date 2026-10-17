import {afterEach,describe,expect,it,vi} from 'vitest';
import {VoiceEditor} from './voiceEditor';
import {meaningCommand} from './meaningExpansion';

function setup(){const e=new VoiceEditor();e.add('title','Рост 5%');e.add('text','Пилот');e.save=vi.fn();return e;}
function response(body:Record<string,unknown>){return {ok:true,json:async()=>body} as Response;}
function model(){return vi.stubGlobal('fetch',vi.fn(async(_url,init)=>{const p=JSON.parse(init.body as string);return response({main_idea:'Значение роста',explanation:'Новый результат 999%',details:[{text:'Пример',role:'иллюстрация',supports:'Раскрывает результат'}],evidence:[{source_id:p.slide_id,quote:'Рост 5%'}],caveats:['Причины не проверены'],recommendation:'update_current',slide_draft:null,verification:'requires_confirmation',slide_id:p.slide_id,version:p.version});}));}
afterEach(()=>vi.unstubAllGlobals());
describe('meaning preview boundary',()=>{
 it('recognises text and already transcribed voice requests',()=>{expect(meaningCommand('Команда: раскрой смысл: добавь пример')).toBe('добавь пример');expect(meaningCommand('добавь текст Раскрой смысл')).toBeUndefined();});
 it('keeps document and history unchanged until explicit accept; edits preview; undo restores source',async()=>{
  model();const e=setup(),before=structuredClone(e.document);await e.meaning.request('Объясни',()=>{});
  expect(e.document).toEqual(before);expect(e.undoStack).toHaveLength(0);
  e.meaning.draft!.explanation='Редактированный 123%';e.meaning.apply('update_current');
  expect(e.current.components.map(c=>c.text).join('\n')).toContain('Редактированный 123%');
  expect(e.current.components.every(c=>c.text.includes('подтвержден')||c.text.includes('подтверждения'))).toBe(true);
  expect(e.current.notes).toContain('Рост 5%');e.undo();expect(e.document).toEqual(before);
 });
 it('rejects draft without changing document',async()=>{model();const e=setup(),before=structuredClone(e.document);await e.meaning.request('пример',()=>{});e.meaning.reject();expect(e.document).toEqual(before);expect(e.meaning.draft).toBeUndefined();expect(e.undoStack).toHaveLength(0);});
 it('inserts follow-up immediately after source using current background, keeping original and undo',async()=>{
  model();const e=setup();e.current.background='#123456';const before=structuredClone(e.document);await e.meaning.request('пример',()=>{});e.meaning.apply('create_follow_up');expect(e.document.pages).toHaveLength(2);expect(e.document.pages[0]).toEqual(before.pages[0]);expect(e.current.background).toBe('#123456');e.undo();expect(e.document).toEqual(before);
 });
 it('blocks changes to source, context, slide navigation and edited preview constraints',async()=>{
  model();const e=setup();await e.meaning.request('пример',()=>{});e.current.components[0].text='Новая правка';expect(()=>e.meaning.apply('update_current')).toThrow('изменился');
  const other=setup();await other.meaning.request('пример',()=>{});other.meaning.draft!.main_idea='';expect(()=>other.meaning.apply('create_follow_up')).toThrow('заполнение');
 });
 it('keeps prior editable preview and work on model errors, bad output, timeout, and cancellation',async()=>{
  model();const e=setup();await e.meaning.request('пример',()=>{});const draft=e.meaning.draft,before=structuredClone(e.document);
  for(const run of [()=>Promise.reject(Error('timeout')),()=>Promise.resolve(response({})),()=>Promise.resolve({ok:false,json:async()=>({detail:'Недоступно'})} as Response)]){
   vi.stubGlobal('fetch',vi.fn(run));await e.meaning.request('Повтори',()=>{});expect(e.meaning.draft).toBe(draft);expect(e.meaning.error).toBeTruthy();expect(e.document).toEqual(before);
  }
 });
 it('uses same preview operation for recognised voice and refuses invented evidence',async()=>{
  model();const e=setup();await e.interpret('раскрой смысл: пример',()=>{});expect(e.meaning.draft).toBeDefined();expect(e.undoStack).toHaveLength(0);
  vi.stubGlobal('fetch',vi.fn(async(_url,init)=>{const p=JSON.parse(init.body as string);return response({...e.meaning.draft,evidence:[{source_id:p.slide_id,quote:'invented'}],version:p.version});}));
  await e.meaning.request('пример',()=>{});expect(e.meaning.error).toContain('источник');
 });
 it('refuses stale response generated while user edits, preserving the new work',async()=>{
  let release!:(r:Response)=>void;vi.stubGlobal('fetch',vi.fn((_url,init)=>new Promise<Response>(resolve=>{const p=JSON.parse(init.body as string);release=()=>resolve(response({main_idea:'Идея',explanation:'Текст',details:[],evidence:[],caveats:[],recommendation:'update_current',slide_draft:null,verification:'requires_confirmation',slide_id:p.slide_id,version:p.version}));})));
  const e=setup(),request=e.meaning.request('пример',()=>{});await vi.waitFor(()=>expect(release).toBeDefined());e.current.components[0].text='Новая правка';release(response({}));await request;expect(e.meaning.stale).toBe(true);expect(()=>e.meaning.apply('update_current')).toThrow('изменился');expect(e.current.components[0].text).toBe('Новая правка');
 });
 it('blocks navigation and neighboring context changes, and cancels pending draft without mutation',async()=>{
  model();const e=setup();e.command('новый слайд');e.document.index=0;e.undoStack=[];
  await e.meaning.request('пример',()=>{});e.document.index=1;expect(()=>e.meaning.apply('update_current')).toThrow('изменился');
  e.document.index=0;await e.meaning.request('пример',()=>{});e.document.pages[1].notes='новые данные';expect(()=>e.meaning.apply('update_current')).toThrow('изменился');
  const before=structuredClone(e.document);vi.stubGlobal('fetch',vi.fn(()=>new Promise(()=>{})));
  const pending=e.meaning.request('пример',()=>{});await vi.waitFor(()=>expect(e.meaning.busy).toBe(true));e.meaning.cancel();await pending;expect(e.document).toEqual(before);expect(e.meaning.busy).toBe(false);
 });
});
