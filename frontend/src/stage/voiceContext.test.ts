import {expect,it} from 'vitest';
import {VoiceContextTimeline,deletionStillValid} from './voiceContext';

it('binds audio to manual context and rejects a switch during or after speech',()=>{
 const t=new VoiceContextTimeline();t.record(0,320,'a',100);t.record(320,640,'b',420);
 expect(t.resolve(0,320,'a',420)?.key).toBe('a');
 expect(t.resolve(0,320,'b',420)).toBeUndefined();
 expect(t.resolve(250,500,'b',420)).toBeUndefined();
 expect(t.resolve(320,640,'b',420)?.key).toBe('b');
});
it('rejects replay after connection invalidation and malformed/missing timing',()=>{
 const t=new VoiceContextTimeline();t.record(0,320,'a',100);
 expect(t.resolve(undefined,320,'a',100)).toBeUndefined();
 expect(t.resolve(0,Infinity,'a',100)).toBeUndefined();
 t.clear();t.record(640,960,'a',200);
 expect(t.resolve(0,320,'a',200)).toBeUndefined();
 expect(t.resolve(640,960,'a',10201)).toBeUndefined();
});
it('requires confirmation to match document, variant, revision and stable slide identity',()=>{
 const p={deckId:'d',variant:'a',revision:'r',slideId:'s',index:1,expiresAt:100};
 const c={deckId:'d',variant:'a',revision:'r',slideIds:['s','other']};
 expect(deletionStillValid(p,c,99)).toBe(true);
 expect(deletionStillValid(p,c,100)).toBe(false);
 expect(deletionStillValid(p,{...c,revision:'new'},0)).toBe(false);
 expect(deletionStillValid(p,{...c,slideIds:['other','s']},0)).toBe(false);
 expect(deletionStillValid(p,{...c,variant:'b'},0)).toBe(false);
});
