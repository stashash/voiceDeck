import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {VoiceEditor} from './voiceEditor';
beforeEach(()=>{vi.stubGlobal('localStorage',{setItem:vi.fn()});vi.stubGlobal('fetch',vi.fn().mockRejectedValue(Error('Model must not handle literal text')));});
afterEach(()=>vi.unstubAllGlobals());
const say=(e:VoiceEditor,phrase:string)=>e.interpret(phrase,()=>{});
it('replaces text from the recorded ASR wording without a model',async()=>{
 const e=new VoiceEditor();e.add('title','Старый заголовок');
 await say(e,'Измени текст. Один, два, три.');
 expect(e.selected?.text).toBe('Один, два, три.');expect(fetch).not.toHaveBeenCalled();
 e.undo();expect(e.selected?.text).toBe('Старый заголовок');
});
it('binds a next-phrase replacement to the selected object and preserves literal command words',async()=>{
 const e=new VoiceEditor();e.add('title','Старый заголовок');
 await say(e,'Измени текст.');expect(e.waitingForText).toBe(true);
 await say(e,'Выбери успех и сделай шаг.');
 expect(e.selected?.text).toBe('Выбери успех и сделай шаг.');expect(e.waitingForText).toBe(false);
 expect(fetch).not.toHaveBeenCalled();
});
it('selects an element and replaces its text within a single recognized utterance',async()=>{
 const e=new VoiceEditor();const first=e.add('title','Первый');e.add('card','Второй');
 await say(e,'Один. Измени текст. Раз, два, три. Пока все');
 expect(first.text).toBe('Раз, два, три. Пока все');expect(e.current.components[1].text).toBe('Второй');
 expect(fetch).not.toHaveBeenCalled();
});
it('cancels pending replacement without undoing previous edits',async()=>{
 const e=new VoiceEditor();e.add('title','Было');await say(e,'Измени текст на Стало');
 const history=e.undoStack.length;
 await say(e,'Измени текст');await say(e,'Отмена.');
 expect(e.waitingForText).toBe(false);expect(e.selected?.text).toBe('Стало');expect(e.undoStack).toHaveLength(history);
 expect(fetch).not.toHaveBeenCalled();
});
it.each(['selection','page','text','lock'])('rejects dictation after a %s change',async(change)=>{
 const e=new VoiceEditor();const first=e.add('title','Первый');const second=e.add('text','Второй');e.select(first.id);
 await say(e,'Измени текст');
 if(change==='selection')e.select(second.id);
 if(change==='page'){e.document.pages.push({id:'other',components:[],background:'#ffffff'});e.document.index=1;}
 if(change==='text')first.text='Правка мышью';
 if(change==='lock')first.locked=true;
 await say(e,'Не записывать');
 expect(first.text).toBe(change==='text'?'Правка мышью':'Первый');expect(second.text).toBe('Второй');
 expect(e.waitingForText).toBe(false);expect(fetch).not.toHaveBeenCalled();
});
it('does not invoke the model for a missing or non-text selection',async()=>{
 const e=new VoiceEditor();await say(e,'Измени текст на Новый');expect(e.notice).toBe('Не выбран текстовый элемент');
 e.add('shape','');await say(e,'Измени текст');expect(e.waitingForText).toBe(false);
 expect(fetch).not.toHaveBeenCalled();
});
it('edits only the numbered text inside a mixed group',async()=>{
 const e=new VoiceEditor();const first=e.add('title','Первый');const second=e.add('shape','');first.group=second.group='group';
 await say(e,'Один. Измени текст');await say(e,'Новый текст.');
 expect(first.text).toBe('Новый текст.');expect(second.text).toBe('');
 expect(fetch).not.toHaveBeenCalled();
});
it('appends to each grouped text without replacing its existing content',async()=>{
 const e=new VoiceEditor();const first=e.add('title','Первый');const second=e.add('text','Второй');first.group=second.group='group';e.select(first.id);
 await say(e,'Добавь в конец текста итог');
 expect(first.text).toBe('Первый итог');expect(second.text).toBe('Второй итог');
 expect(fetch).not.toHaveBeenCalled();
});
