import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {VoiceEditor} from './voiceEditor';
import {applyPlan} from './editorOperations';
import {quickVoice} from './quickVoice';
beforeEach(()=>{vi.stubGlobal('localStorage',{setItem:vi.fn()});vi.stubGlobal('fetch',vi.fn(()=>{throw Error('Unexpected model call');}));});
afterEach(()=>vi.unstubAllGlobals());
const say=(e:VoiceEditor,s:string)=>e.interpret(s,()=>{});
it('selects multiple stable numbers, moves and refines without a model, undo restores geometry',async()=>{
 const e=new VoiceEditor();const a=e.add('card','A'),b=e.add('card','B');
 await say(e,'Выбери номера один и два');expect(e.selectedIds).toEqual([a.id,b.id]);
 await say(e,'Вправо на двадцать');expect(a.x).toBe(84);expect(b.x).toBe(84);
 await say(e,'Ещё немного');expect(a.x).toBe(94);
 await say(e,'Половину назад');expect(a.x).toBe(89);
 await say(e,'Отмени');expect(e.current.components[0].x).toBe(94);expect(fetch).not.toHaveBeenCalled();
});
it('preserves numbers across layering, deletion and duplication',async()=>{
 const e=new VoiceEditor();const a=e.add('card','A'),b=e.add('card','B');
 applyPlan(e,{operations:[{op:'layer',targets:[a.id],value:'front'}],clarification:'',summary:''});
 expect(a.voiceNumber).toBe(1);await say(e,'Выбери два');await say(e,'Удали');
 const c=e.add('text','C');expect(c.voiceNumber).toBe(3);
 await say(e,'Дублируй');expect(new Set(e.current.components.map(c=>c.voiceNumber)).size).toBe(3);expect(b.voiceNumber).toBe(2);
});
it('does not guess which two cards among three, or partially select absent numbers',async()=>{
 const e=new VoiceEditor();for(let i=0;i<3;i++)e.add('card',String(i));const selected=e.document.selected;
 await say(e,'Выбери две карточки');expect(e.notice).toContain('Уточните');expect(e.document.selected).toBe(selected);
 await say(e,'Выбери номера один и семь');expect(e.notice).toContain('Такого номера нет');expect(e.document.selected).toBe(selected);
});
it('moves a group with one bounded delta, retaining its spacing',async()=>{
 const e=new VoiceEditor();const a=e.add('card','A'),b=e.add('card','B');a.x=800;b.x=900;a.group=b.group='group';
 await say(e,'Выбери один');await say(e,'Вправо на сто');expect(a.x).toBe(860);expect(b.x).toBe(960);
});
it('refuses stale relative commands after a manual change or undo',async()=>{
 const e=new VoiceEditor();const a=e.add('text','A');await say(e,'Вправо');e.update(a.id,{text:'changed'});
 await say(e,'Ещё');expect(a.x).toBe(84);expect(e.notice).toContain('Нет актуального');
 e.undo();await say(e,'Половину назад');expect(e.notice).toContain('Нет актуального');
});
it('preserves dictation and supports an explicit command prefix',async()=>{
 const e=new VoiceEditor();e.add('text','');e.mode='dictation';await say(e,'Вправо');expect(e.selected?.text).toBe('Вправо');
 await say(e,'Команда вправо на 10');expect(e.selected?.x).toBe(74);
});
it('planner selected targets apply to the whole selection and selection does not consume undo',()=>{
 const e=new VoiceEditor();const a=e.add('card','A'),b=e.add('card','B');
 applyPlan(e,{operations:[{op:'select',targets:[a.id,b.id]}],clarification:'',summary:''});expect(e.undoStack).toHaveLength(0);
 applyPlan(e,{operations:[{op:'update',targets:['selected'],props:{bold:true}}],clarification:'',summary:''});expect(a.bold&&b.bold).toBe(true);
});

it('navigates and edits explicit slides with spoken numbers entirely offline',async()=>{
 const e=new VoiceEditor();e.add('title','Первый');
 applyPlan(e,{operations:[{op:'slide_add'},{op:'add',props:{kind:'title',text:'Второй'}},{op:'slide_add'},{op:'add',props:{kind:'title',text:'Третий'}}],clarification:'',summary:''});
 const original=e.document.pages.map(p=>p.id),history=e.undoStack.length;
 await say(e,'Покажи первый слайд');expect(e.current.id).toBe(original[0]);expect(e.selectedIds).toEqual([]);
 await say(e,'Переключись на следующий слайд');expect(e.current.id).toBe(original[1]);
 await say(e,'Предыдущий слайд');expect(e.current.id).toBe(original[0]);
 await say(e,'Выбери слайд три');expect(e.current.id).toBe(original[2]);
 await say(e,'Открой последний слайд');expect(e.undoStack).toHaveLength(history);
 await say(e,'Скопируй второй слайд');expect(e.document.pages).toHaveLength(4);expect(e.current.components[0].text).toBe('Второй');
 expect(e.current.id).not.toBe(original[1]);
 await say(e,'Удали слайд один');expect(e.document.pages.map(p=>p.id)).not.toContain(original[0]);
 await say(e,'Отмена');expect(e.document.pages[0].id).toBe(original[0]);expect(fetch).not.toHaveBeenCalled();
});

it.each(['Открой слайд ноль','Выбери нулевой слайд','Перейди на слайд девять','Предыдущий слайд','Следующий слайд','Удали слайд ноль','Скопируй слайд девять'])('refuses invalid slide destinations locally: %s',async command=>{
 const e=new VoiceEditor();e.add('card','Выбрано');const before=structuredClone(e.document);
 await expect(say(e,command)).rejects.toThrow();expect(e.document).toEqual(before);
 expect(e.undoStack).toHaveLength(0);expect(fetch).not.toHaveBeenCalled();
});

it('accepts raw punctuation for commands but retains literal cell punctuation',()=>{
 const e=new VoiceEditor();const table=e.add('table','План');table.rows=[['']];
 expect(quickVoice(e,'Ячейка один, один: Доход, Ёж!')).toBe(true);
 expect(table.rows).toEqual([['Доход, Ёж!']]);
 expect(quickVoice(e,'Размер шрифта тридцать два.')).toBe(true);expect(table.size).toBe(32);
 expect(fetch).not.toHaveBeenCalled();
});

it.each(['Слайд про доставку','Слайд о доставке','Сделай слайд профессиональным','Сделай слайд про Доставку','Сделай красивый слайд'])('routes free form slide requests to the planner: %s',async command=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:false,json:async()=>({detail:'Модель недоступна'})}));
 const e=new VoiceEditor();e.add('card','Выбранная');const before=structuredClone(e.document);
 expect(quickVoice(e,command)).toBe(false);expect(e.document).toEqual(before);
 await e.interpret(command,()=>{});
 const requests=vi.mocked(fetch).mock.calls.filter(([url])=>String(url).endsWith('/editor/intent'));
 expect(requests).toHaveLength(1);expect(JSON.parse(requests[0][1]!.body as string).instruction).toBe(command);
 expect(e.notice).toContain('Модель недоступна');
 expect(e.document).toEqual(before);expect(e.undoStack).toHaveLength(0);
});

it('only treats a bare slide phrase as navigation when it contains a complete number',async()=>{
 const e=new VoiceEditor();e.command('новый слайд');
 await say(e,'Слайд один');expect(e.document.index).toBe(0);
 await say(e,'Слайд номер два');expect(e.document.index).toBe(1);
 const before=structuredClone(e.document);
 await expect(say(e,'Слайд девять')).rejects.toThrow('Такого слайда нет');
 expect(e.document).toEqual(before);expect(fetch).not.toHaveBeenCalled();
});
