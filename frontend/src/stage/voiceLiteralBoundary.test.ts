import {expect,it,vi} from 'vitest';
import {VoiceEditor} from './voiceEditor';
it('passes literal punctuation through the real voice interpretation boundary',async()=>{
 const e=new VoiceEditor();e.onSave=()=>{};
 const fetch=vi.spyOn(globalThis,'fetch').mockRejectedValue(Error('Model must not be used'));
 try{
  await e.interpret('Добавь текст API v2: Рост 20%.',()=>{});
  expect(e.selected?.text).toBe('API v2: Рост 20%.');
  await e.interpret('Сделай текст жирным.',()=>{});
  expect(e.selected?.bold).toBe(true);
  expect(fetch).not.toHaveBeenCalled();
 }finally{fetch.mockRestore();}
});
