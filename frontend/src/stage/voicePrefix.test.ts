import {it,expect} from 'vitest';
import {joinPrefix,PREFIX_WAIT_MS} from './voicePrefix';
import {parseDeckVoice} from './deckVoice';

it('joins a bare command start with the next phrase',()=>{
 const first=joinPrefix('Слайд.',null,1000);
 expect(first.text).toBeNull();
 const second=joinPrefix('Два.',first.pending,1800);
 expect(second).toEqual({text:'Слайд два.',pending:null});
 expect(parseDeckVoice(second.text!)).toEqual({kind:'select',number:2});
});
it('forgets a stale start and passes ordinary phrases through',()=>{
 const first=joinPrefix('Выбери',null,0);
 expect(joinPrefix('Отмени.',first.pending,PREFIX_WAIT_MS+1)).toEqual({text:'Отмени.',pending:null});
 expect(joinPrefix('Слайд десять.',null,0)).toEqual({text:'Слайд десять.',pending:null});
});
