import {describe,expect,it} from 'vitest';
import type {Element,Scene} from '../designer/api';
import {planVoiceBatch} from './voiceBatch';
import type {AtomicVoiceStep,LayoutOperation} from './voiceOperations';

const element=(id:string,box:Element['box'],type:Element['type']='text'):Element=>({id,box,type,role:'body',text:id,style:type==='text'?{size_pt:24}:undefined});
const scene=(elements:Element[]):Scene=>({slide_id:'s1',pattern_id:'p1',variant:'a',theme:'light',elements});
const sample=()=>scene([element('a',[.1,.1,.1,.1]),element('b',[.35,.3,.15,.2]),element('c',[.8,.7,.1,.1])]);
const plan=(operation:LayoutOperation,s=sample())=>planVoiceBatch(s,s.elements.map(e=>e.id),[{kind:'layout',operation}]);

describe('atomic voice batch planning',()=>{
  it('does not mutate the scene and merges a macro into one patch per ID',()=>{
    const s=sample(),before=JSON.stringify(s);
    const result=planVoiceBatch(s,['a','b'],[{kind:'style',bold:true},{kind:'style',size_pt:28},{kind:'move',dx:.01,dy:0}]);
    expect(JSON.stringify(s)).toBe(before);
    expect(result).toMatchObject({operations:[{element_id:'a',style:{bold:true,size_pt:28},box:[.11,.1,.1,.1]},{element_id:'b',style:{bold:true,size_pt:28}}]});
  });
  it.each<LayoutOperation>(['alignLeft','alignRight','alignTop','alignBottom','alignCenterX','alignCenterY','sameWidth','sameHeight','sameSize'])('keeps %s in bounds',operation=>{
    const result=plan(operation);expect('operations' in result).toBe(true);
    if('operations' in result)for(const op of result.operations){const [x,y,w,h]=op.box!;expect(x).toBeGreaterThanOrEqual(0);expect(y).toBeGreaterThanOrEqual(0);expect(x+w).toBeLessThanOrEqual(1);expect(y+h).toBeLessThanOrEqual(1);}
  });
  it('distributes horizontal gaps, preserving endpoints and widths',()=>{
    const result=plan('distributeX');
    expect(result).toMatchObject({operations:[{element_id:'b'}]});
    if('operations' in result)expect(result.operations[0].box![0]).toBeCloseTo(.425);
  });
  it('distributes vertical gaps',()=>{
    const result=plan('distributeY');
    expect(result).toMatchObject({operations:[{element_id:'b'}]});
    if('operations' in result)expect(result.operations[0].box![1]).toBeCloseTo(.35);
  });
  it('clamps group movement without collapsing relative positions',()=>{
    const result=planVoiceBatch(sample(),['a','c'],[{kind:'move',dx:1,dy:0}]);
    if(!('operations' in result))throw Error(result.notice);
    expect(result.operations[0].box![0]).toBeCloseTo(.2);
    expect(result.operations[1].box![0]).toBeCloseTo(.9);
  });
  it('centers the group as one body',()=>{
    const result=planVoiceBatch(sample(),['a','b'],[{kind:'move',dx:0,dy:0,align:'center'}]);
    if(!('operations' in result))throw Error(result.notice);
    expect(result.operations[0].box![0]).toBeCloseTo(.3);
    expect(result.operations[1].box![0]).toBeCloseTo(.55);
  });
  it.each([
    [[],[{kind:'style',bold:true}]],
    [['a','a'],[{kind:'style',bold:true}]],
    [['missing'],[{kind:'style',bold:true}]],
    [['a'],[{kind:'layout',operation:'alignLeft'}]],
    [['a','b'],[{kind:'layout',operation:'distributeX'}]],
    [['a','c'],[{kind:'style',width:.4}]],
    [['a','b'],[{kind:'style',bold:true},{kind:'style',size_pt:200}]],
  ] as [string[],AtomicVoiceStep[]][])('rejects an invalid complete plan (%s)',(ids,steps)=>expect(planVoiceBatch(sample(),ids,steps)).toHaveProperty('notice'));
  it('rejects overlapping distribution instead of introducing overlaps',()=>{
    expect(plan('distributeX',scene([element('a',[.1,.1,.3,.1]),element('b',[.2,.1,.3,.1]),element('c',[.3,.1,.3,.1])]))).toHaveProperty('notice');
  });
  it('rejects mixed-type text style with no partial patch',()=>{
    const s=sample();s.elements[1].type='shape';
    expect(planVoiceBatch(s,['a','b'],[{kind:'style',bold:true}])).toHaveProperty('notice');
  });
  it('does not generate history for a no-op',()=>expect(planVoiceBatch(sample(),['a'],[{kind:'style',size_pt:24}])).toHaveProperty('notice'));
  it('uses the first selected object as the size reference',()=>{
    expect(planVoiceBatch(sample(),['b','a'],[{kind:'layout',operation:'sameSize'}])).toMatchObject({operations:[{element_id:'a',box:[.1,.1,.15,.2]}]});
  });
});
