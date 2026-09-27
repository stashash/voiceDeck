import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {expect,it,vi} from 'vitest';
import {VoiceEditor} from './voiceEditor';
import {parseDeckVoice} from './deckVoice';

const fixture=process.env.EDITOR_TEXT_AUDIO;
it.skipIf(!fixture)('replaces slide text from the real authenticated ASR stream',async()=>{
 const script=fileURLToPath(new URL('../../../scripts/editor-audio-smoke.mjs',import.meta.url));
 const output=execFileSync(process.execPath,[script,fixture!],{encoding:'utf8',timeout:90000,env:{...process.env,BASE_URL:process.env.EDITOR_AUDIO_BASE_URL??'http://localhost:8088'}});
 const result=JSON.parse(output.trim());
 console.log(JSON.stringify(result));
 expect(result.result).toBe('PASS');expect(result.warnings).toEqual([]);
 expect(['textStart','text']).toContain(parseDeckVoice(result.utterances[0]).kind);
 vi.stubGlobal('localStorage',{setItem:vi.fn()});
 vi.stubGlobal('fetch',vi.fn().mockRejectedValue(Error('Literal text must not call a model')));
 try{
  const editor=new VoiceEditor();editor.add('title','Старый текст');
  for(const phrase of result.utterances)await editor.interpret(phrase,()=>{});
  expect(editor.selected?.text).toMatch(/^Один, два, три\.?$/);
  expect(editor.waitingForText).toBe(false);
  expect(fetch).not.toHaveBeenCalled();
  console.log(JSON.stringify({utterances:result.utterances,replacement:editor.selected?.text,packets:result.packetsAcknowledged}));
 }finally{vi.unstubAllGlobals();}
},100000);
