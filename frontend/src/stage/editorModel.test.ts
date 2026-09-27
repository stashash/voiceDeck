import {afterEach,expect,it,vi} from 'vitest';
import {VoiceEditor} from './voiceEditor';
afterEach(()=>{vi.useRealTimers();vi.unstubAllGlobals();});
const response=(data:unknown,ok=true)=>({ok,json:async()=>data});

it('waits for cold loading then runs the original command once without extending inference timeout',async()=>{
 vi.useFakeTimers();vi.stubGlobal('localStorage',{setItem:vi.fn()});
 const fetch=vi.fn()
  .mockResolvedValueOnce(response({detail:{code:'model_loading',message:'Loading'}},false))
  .mockResolvedValueOnce(response({state:'loading',model:'model'}))
  .mockResolvedValueOnce(response({state:'ready',model:'model'}))
  .mockResolvedValueOnce(response({operations:[{op:'add',props:{text:'Ready'}}],clarification:'',summary:'Done'}));
 vi.stubGlobal('fetch',fetch);const e=new VoiceEditor();const pending=e.interpret('Создай содержательный слайд',()=>{});
 await vi.advanceTimersByTimeAsync(701);await pending;
 expect(e.current.components.map(c=>c.text)).toEqual(['Ready']);
 expect(fetch.mock.calls.map(c=>String(c[0]).split('/editor/')[1])).toEqual(['intent','intent/prepare','intent/model','intent']);
 expect(fetch.mock.calls[0][1].body).toBe(fetch.mock.calls[3][1].body);
 expect(e.thinking).toBe(false);
});

it('cancels a cold command immediately and leaves local edits available',async()=>{
 vi.useFakeTimers();vi.stubGlobal('localStorage',{setItem:vi.fn()});
 const fetch=vi.fn().mockResolvedValue(response({state:'loading',model:'model'}))
  .mockResolvedValueOnce(response({detail:{code:'model_loading',message:'Loading'}},false));
 vi.stubGlobal('fetch',fetch);const e=new VoiceEditor();e.add('title','Plan');
 const pending=e.interpret('Создай содержательный слайд',()=>{});
 await vi.advanceTimersByTimeAsync(50);
 await e.interpret('Выбери заголовок',()=>{});expect(e.selected?.text).toBe('Plan');
 e.cancel();await pending;await vi.advanceTimersByTimeAsync(5000);
 expect(e.thinking).toBe(false);expect(e.current.components).toHaveLength(1);
 expect(fetch.mock.calls.filter(c=>String(c[0]).endsWith('/intent'))).toHaveLength(1);
});

it('refuses to replay the command against edits made while the model loads',async()=>{
 vi.useFakeTimers();vi.stubGlobal('localStorage',{setItem:vi.fn()});
 const fetch=vi.fn().mockResolvedValue(response({state:'ready',model:'model'}))
  .mockResolvedValueOnce(response({detail:{code:'model_loading',message:'Loading'}},false))
  .mockResolvedValueOnce(response({state:'loading',model:'model'}));
 vi.stubGlobal('fetch',fetch);const e=new VoiceEditor();e.add('title','Plan');
 const pending=e.interpret('Создай содержательный слайд',()=>{});
 await vi.advanceTimersByTimeAsync(50);await e.interpret('Сделай заголовок красным',()=>{});
 await vi.advanceTimersByTimeAsync(701);await pending;
 expect(e.notice).toContain('Слайд изменился');expect(e.selected?.color).toBe('#dc2626');
 expect(fetch.mock.calls.filter(c=>String(c[0]).endsWith('/intent'))).toHaveLength(1);
});
