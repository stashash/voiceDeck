import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {VoiceEditor} from './voiceEditor';
beforeEach(()=>{vi.stubGlobal('localStorage',{setItem:vi.fn()});vi.stubGlobal('fetch',vi.fn(()=>{throw Error('Unexpected model call');}));});
afterEach(()=>vi.unstubAllGlobals());
it('handles everyday Russian editing commands entirely offline',async()=>{
 const e=new VoiceEditor(),title=e.add('title','План'),a=e.add('card','Продажи'),b=e.add('card','Продукт');
 const say=(s:string)=>e.interpret(s,()=>{});
 await say('Выбери заголовок.');expect(e.selected?.id).toBe(title.id);
 await say('Сделай заголовок красным');expect(title.color).toBe('#dc2626');
 await say('Сделай заголовок крупнее');expect(title.size).toBe(48);
 await say('Сделай его жирным');expect(title.bold).toBe(true);
 await say('Размер текста тридцать два');expect(title.size).toBe(32);
 await say('Выбери вторую карточку');expect(e.selected?.id).toBe(b.id);
 await say('Перемести первую карточку вправо на тридцать');expect(a.x).toBe(94);
 await say('Подвинь карточку «Продажи» на двадцать пикселей вниз');expect(a.y).toBe(200);
 await say('Переименуй карточку «Продажи» в «Рост»');expect(a.text).toBe('Рост');
 await say('Замени заголовок на «Запуск и рост»');expect(title.text).toBe('Запуск и рост');
 await say('Сделай фон белым');expect(e.current.background).toBe('#ffffff');
 await say('Удали карточку «Рост»');expect(e.current.components.map(c=>c.id)).not.toContain(a.id);
 await say('Отмена');expect(e.current.components.map(c=>c.id)).toContain(a.id);
 await say('Добавь новый слайд');expect(e.document.index).toBe(1);
 await say('Перейди на первый слайд');expect(e.document.index).toBe(0);
 expect(fetch).not.toHaveBeenCalled();
});
it('refuses ambiguous and locked targets without touching an unrelated selection',async()=>{
 const e=new VoiceEditor();e.add('title','One');e.add('title','Two');e.add('card','Card');
 await expect(e.interpret('Сделай заголовок красным',()=>{})).rejects.toThrow('несколько');
 expect(e.selected?.text).toBe('Card');
 e.selected!.locked=true;
 await expect(e.interpret('Сделай карточку шире',()=>{})).rejects.toThrow('заблокирован');
 await e.interpret('Разблокируй карточку',()=>{});expect(e.selected?.locked).toBe(false);
 expect(fetch).not.toHaveBeenCalled();
});
it('never consumes the recognized prefix of a compound editing request',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>({operations:[],clarification:'Уточните',summary:''})}));
 const e=new VoiceEditor();const title=e.add('title','Plan');
 await e.interpret('Сделай заголовок крупнее и красным',()=>{});
 expect(title.size).toBe(44);expect(fetch).toHaveBeenCalledOnce();
});
