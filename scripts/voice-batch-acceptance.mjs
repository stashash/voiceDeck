import assert from 'node:assert/strict';
import {parseArgs} from 'node:util';
import {writeFile} from 'node:fs/promises';

const {values}=parseArgs({options:{deck:{type:'string'},output:{type:'string'},'allow-mutation':{type:'boolean'}}});
if(!values.deck||!/^[a-f0-9]{32}$/.test(values.deck)||!values['allow-mutation'])throw Error('Use --deck <isolated-test-deck-id> --allow-mutation [--output new-file.json]');
const base='http://127.0.0.1:8191',path=`/decks/${values.deck}`,report={kind:'voice-batch-api-acceptance',base,deck:values.deck,time:new Date().toISOString(),checks:[],physical_microphone:false};
async function request(suffix,body){
  const started=performance.now();
  const response=await fetch(base+path+suffix,{method:body===undefined?'GET':'POST',headers:{'content-type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(10000)});
  const data=await response.json();return {status:response.status,data,ms:Math.round(performance.now()-started)};
}
const state=async()=>{const response=await request('');assert.equal(response.status,200);return response.data.variants.a;};
const before=await state(),scene=before.scenes[0],targets=scene.elements.filter(e=>e.type==='text').slice(0,2);
assert.equal(targets.length,2,'Acceptance needs two text elements on the first test slide');
const batch={expected_revision:before.revision??'',target_slide_id:scene.slide_id,operations:targets.map(el=>({element_id:el.id,style:{bold:!el.style?.bold,italic:!el.style?.italic}}))};
const endpoint='/a/slides/1/voice-batch';
const invalid=await request(endpoint,{...batch,operations:[batch.operations[0],{element_id:'missing-acceptance-target',style:{bold:true}}]});
assert.equal(invalid.status,422);assert.deepEqual((await state()).scenes,before.scenes);assert.equal((await state()).revision,before.revision);
report.checks.push({name:'invalid-second-target-no-partial-save',status:invalid.status,ms:invalid.ms});
for(const [name,body] of [['stale-revision',{...batch,expected_revision:'stale-acceptance'}],['wrong-slide',{...batch,target_slide_id:'wrong-acceptance-slide'}]]){
  const response=await request(endpoint,body);assert.equal(response.status,409);report.checks.push({name,status:response.status,ms:response.ms});
}
let committed=false,committedRevision;
try{
  const saved=await request(endpoint,batch);assert.equal(saved.status,200);committed=true;committedRevision=saved.data.revision;
  assert.notEqual(committedRevision,before.revision);
  const persisted=await state();assert.equal(persisted.revision,committedRevision);
  for(const op of batch.operations){const el=persisted.scenes[0].elements.find(e=>e.id===op.element_id);assert.equal(el.style.bold,op.style.bold);assert.equal(el.style.italic,op.style.italic);}
  assert.deepEqual(persisted.scenes.slice(1),before.scenes.slice(1));
  report.checks.push({name:'batch-persisted-and-other-slides-unchanged',status:saved.status,ms:saved.ms,targets:targets.map(e=>e.id)});
  const replay=await request(endpoint,batch);assert.equal(replay.status,409);report.checks.push({name:'replay-rejected',status:replay.status,ms:replay.ms});
  assert.equal((await state()).revision,committedRevision);
  const undone=await request('/a/revert',{});assert.equal(undone.status,200);committed=false;
  assert.deepEqual((await state()).scenes,before.scenes);assert.deepEqual(undone.data.plan,before.plan);
  report.checks.push({name:'single-undo-restores-complete-batch',status:undone.status,ms:undone.ms});
}finally{
  // Never revert someone else's intervening edit during failed acceptance.
  if(committed&&(await state()).revision===committedRevision)await request('/a/revert',{});
}
report.passed=true;
if(values.output)await writeFile(values.output,JSON.stringify(report,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify(report,null,2));
