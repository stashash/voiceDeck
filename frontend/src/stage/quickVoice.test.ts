import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {VoiceEditor} from './voiceEditor';
import {applyPlan} from './editorOperations';
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
