import {it,expect,vi,afterEach} from 'vitest';
import {VoiceEditor} from './voiceEditor';
afterEach(()=>vi.unstubAllGlobals());
it('fast commands run while planning; canceled responses never apply',async()=>{
 let resolve!:(value:unknown)=>void;
 vi.stubGlobal('fetch',vi.fn(()=>new Promise(r=>{resolve=r;})));
 const e=new VoiceEditor();e.add('card','A');const x=e.selected!.x;
 const pending=e.interpret('Сделай красивую композицию',()=>{});
 await e.interpret('вправо на 20',()=>{});
 expect(e.selected!.x).toBe(x+20);
 await e.interpret('стоп',()=>{});
 resolve({ok:true,json:async()=>({operations:[{op:'delete',targets:['selected']}],clarification:'',summary:''})});
 await pending;expect(e.current.components).toHaveLength(1);expect(e.thinking).toBe(false);
});
it('creation and exact text editing do not call a model',async()=>{
 const fetch=vi.fn();vi.stubGlobal('fetch',fetch);const e=new VoiceEditor();
 await e.interpret('Добавь заголовок План запуска',()=>{});
 await e.interpret('Замени текст на Итоги',()=>{});
 expect(e.selected?.text).toBe('Итоги');expect(fetch).not.toHaveBeenCalled();
 e.undo();expect(e.selected?.text).toBe('План запуска');
});
