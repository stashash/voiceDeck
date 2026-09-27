import {afterEach,expect,it,vi} from 'vitest';
import {VoiceEditor} from './voiceEditor';
import {applyPlan} from './editorOperations';
import {EditorPersistence,Draft,DraftStorage} from './editorPersistence';
import {contextPages} from './editorContext';

afterEach(()=>{vi.useRealTimers();vi.unstubAllGlobals();});
const reply=(operations:unknown[])=>({ok:true,json:async()=>({operations,clarification:'',summary:'Done'})});

it('includes only current and explicitly referenced slides',()=>{
 const e=new VoiceEditor();for(let i=0;i<49;i++)e.command('новый слайд');
 expect(contextPages('Удали карточку',e.document,e.current.id)).toHaveLength(1);
 const included=contextPages('Перейди на первый слайд и удали карточку',e.document,e.current.id);
 expect(included.map(p=>p.id)).toEqual([e.document.pages[0].id,e.current.id]);
});

it('creates a complete compound instruction locally with a single undo',async()=>{
 const fetch=vi.fn();vi.stubGlobal('fetch',fetch);
 const e=new VoiceEditor();await e.interpret('Добавь заголовок План запуска и две карточки: Продукт и Продажи',()=>{});
 expect(e.current.components.map(c=>c.text)).toEqual(['План запуска','Продукт','Продажи']);
 expect(e.undoStack).toHaveLength(1);e.undo();expect(e.current.components).toHaveLength(0);expect(fetch).not.toHaveBeenCalled();
});

it('never accepts only the creation prefix of a compound request',async()=>{
 const fetch=vi.fn().mockResolvedValue(reply([]));vi.stubGlobal('fetch',fetch);
 const e=new VoiceEditor();await e.interpret('Добавь заголовок План и сделай его красным',()=>{});
 expect(fetch).toHaveBeenCalledOnce();expect(e.current.components).toHaveLength(0);
 await e.interpret('Добавь текст «План и сделай его красным»',()=>{});
 expect(e.selected?.text).toBe('План и сделай его красным');expect(fetch).toHaveBeenCalledOnce();
});

it('queues independent model commands instead of cancelling the preceding command',async()=>{
 const responses:((v:unknown)=>void)[]=[];
 vi.stubGlobal('fetch',vi.fn(()=>new Promise(r=>responses.push(r))));
 const e=new VoiceEditor();
 const first=e.interpret('Красиво оформи первый блок',()=>{});
 const second=e.interpret('Теперь добавь второй блок',()=>{});
 expect(e.queued).toBe(1);expect(responses).toHaveLength(1);
 responses[0](reply([{op:'add',props:{kind:'text',text:'First'}}]));await first;
 await vi.waitFor(()=>expect(responses).toHaveLength(2));
 responses[1](reply([{op:'add',props:{kind:'text',text:'Second'}}]));await second;
 expect(e.current.components.map(c=>c.text)).toEqual(['First','Second']);
});

it('watchdog releases a fetch that ignores cancellation and late results cannot apply',async()=>{
 vi.useFakeTimers();let resolve!:(v:unknown)=>void;
 vi.stubGlobal('fetch',vi.fn(()=>new Promise(r=>{resolve=r;})));
 const e=new VoiceEditor();const pending=e.interpret('Разработай оформление',()=>{});
 const late=resolve;
 await vi.advanceTimersByTimeAsync(35001);await pending;
 expect(e.thinking).toBe(false);expect(e.notice).toContain('время ожидания');
 late(reply([{op:'add',props:{kind:'text',text:'Late'}}]));await Promise.resolve();
 expect(e.current.components).toHaveLength(0);
 await vi.advanceTimersByTimeAsync(2001);
});

it('keeps navigation and selection independent of a pending plan',async()=>{
 let resolve!:(v:unknown)=>void;vi.stubGlobal('fetch',()=>new Promise(r=>{resolve=r;}));
 const e=new VoiceEditor();const first=e.current.id;const card=e.add('card','First');
 e.command('новый слайд');const other=e.add('text','Other');e.document.index=0;e.select(card.id);
 const pending=e.interpret('Сократи формулировку',()=>{});
 e.document.index=1;e.select(other.id);
 resolve(reply([{op:'update',targets:['e1'],props:{text:'Short'}}]));await pending;
 expect(e.current.id).not.toBe(first);expect(e.selected?.id).toBe(other.id);expect(e.document.pages[0].components[0].text).toBe('Short');
});

it('edits individual cells and protects locked elements atomically',async()=>{
 const e=new VoiceEditor();await e.interpret('Добавь таблицу 2 на 2',()=>{});
 await e.interpret('Ячейка 2, 1: Выручка',()=>{});expect(e.selected?.rows?.[1]).toEqual(['Выручка','']);
 await e.interpret('Добавь строку',()=>{});expect(e.selected?.rows).toHaveLength(3);
 await e.interpret('Заблокируй',()=>{});
 expect(()=>applyPlan(e,{operations:[{op:'table_cell',row:1,column:1,value:'Bad'}],clarification:'',summary:''})).toThrow('заблокирован');
 await e.interpret('Разблокируй',()=>{});await e.interpret('Удали строку 3',()=>{});expect(e.selected?.rows).toHaveLength(2);
});

it('retries an uncertain save with exactly the same identity before newer edits',async()=>{
 const records:Draft[]=[];const storage:DraftStorage={get:async()=>undefined,put:async d=>{records.push(structuredClone(d));}};
 const e=new VoiceEditor();e.add('text','First');const draft:Draft={id:'doc',revision:0,title:'Title',document:e.document,dirty:true};
 const fetch=vi.fn().mockRejectedValueOnce(Error('Network lost')).mockResolvedValueOnce({ok:true,json:async()=>({revision:1})}).mockResolvedValueOnce({ok:true,json:async()=>({revision:2})});vi.stubGlobal('fetch',fetch);
 const persistence=new EditorPersistence(draft,()=>{},storage);
 await expect(persistence.flush()).rejects.toThrow('Network lost');
 e.selected!.text='Newer';persistence.schedule(e.document,'Title');
 await persistence.retry();
 const bodies=fetch.mock.calls.map(c=>JSON.parse(c[1].body));
 expect(bodies[1]).toEqual(bodies[0]);expect(bodies[2].base_revision).toBe(1);expect(bodies[2].document.pages[0].components[0].text).toBe('Newer');
 expect(records.at(-1)?.dirty).toBe(false);expect(draft.revision).toBe(2);
});

it('retains the local draft on a revision conflict and never forces an overwrite',async()=>{
 let backup:Draft|undefined;const storage:DraftStorage={get:async()=>undefined,put:async d=>{backup=d;}};
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:false,json:async()=>({detail:'Документ изменён в другой вкладке'})}));
 const draft:Draft={id:'doc',revision:1,title:'Title',document:new VoiceEditor().document,dirty:true};
 const persistence=new EditorPersistence(draft,()=>{},storage);
 await expect(persistence.flush()).rejects.toThrow('другой вкладке');
 expect(backup?.dirty).toBe(true);expect(draft.revision).toBe(1);
});
