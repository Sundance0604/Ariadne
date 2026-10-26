import assert from 'node:assert/strict';
import {test} from 'node:test';
import {activeEvents,indexResearch,referenceTickAt,spanNavigation} from '../review/research-model.mjs';
import {createStructuralHUD} from '../review/structural-hud.mjs';
import {appendEngineEvidence} from '../review/engine-evidence.mjs';
import {makeDOM,fixture,Element} from './research-dom.mjs';
const sha='a'.repeat(64);
function candidate(id,dimension,start,end){return {id,dimension,short_label:id,html:'candidate',
  analysis_origin:'engine_candidate',claim_level:'theoretical_analysis',verification:{score:'pending',timing:'candidate_alignment'},
  score_spans:[{precision:'reference_interval_candidate',reference_start_tick:start,reference_end_tick:end,
    reference_sha256:sha,pdf_page_start:11,pdf_page_end:11}]};}
test('reference clock follows tempo changes and rejects wrong source or endpoint',()=>{
  const clock=[{tick:0,midi_seconds:0,seconds_per_tick:.001},{tick:1000,midi_seconds:1,seconds_per_tick:.002}];
  assert.equal(referenceTickAt(clock,2),1500);assert.equal(referenceTickAt(clock,-1),null);
  const data={events:[candidate('h','harmony',0,100)]},index=indexResearch(data);
  assert.equal(activeEvents(index,{referenceTick:50,referenceSha256:sha,playingPage:10}).get('harmony').length,1);
  assert.equal(activeEvents(index,{referenceTick:100,referenceSha256:sha}).get('harmony').length,0);
  assert.equal(activeEvents(index,{referenceTick:50,referenceSha256:'wrong'}).get('harmony').length,0);
  assert.equal(spanNavigation(data.events[0].score_spans[0],{location:'reference_interval_candidate',timing:'candidate_alignment'}).canSeek,false);
});
test('harmony changes inside one reference bar without rebuilding orchestration or article',()=>{
  const $=makeDOM(),data=fixture(),hud=createStructuralHUD({onEssay(){}});
  $('hud-auto-candidates').checked=true;
  data.events=[candidate('h1','harmony',0,100),candidate('h2','harmony',100,200),candidate('orch','orchestration',0,300)];
  $('essay-body').append(new Element());$('essay-body').scrollTop=123;
  const article=$('essay-body').children[0];hud.load(data);
  hud.update({playingPage:10,browsedPage:10,referenceTick:50,referenceSha256:sha});
  const orch=$('structural-hud').children[1].children[1],replacements=orch.replacements;
  assert.match($('structural-hud').textContent,/h1/);assert.match($('structural-hud').textContent,/PDF\/MIDI候选/);
  hud.update({playingPage:10,browsedPage:10,referenceTick:150,referenceSha256:sha});
  assert.match($('structural-hud').textContent,/h2/);assert.doesNotMatch($('structural-hud').textContent,/h1/);
  assert.equal(orch.replacements,replacements);assert.equal($('essay-body').children[0],article);assert.equal($('essay-body').scrollTop,123);
  hud.update({playingPage:10,referenceTick:220,referenceSha256:sha});assert.match($('structural-hud').children[0].textContent,/待分析/);
});
test('late evidence response cannot repopulate a reset track',async()=>{
  const $=makeDOM();let complete;
  $('hud-auto-candidates').checked=true;
  const hud=createStructuralHUD({onEssay(){},onEvidence:()=>new Promise(resolve=>{complete=resolve;})});
  hud.load({events:[candidate('h','harmony',0,100)],essays:[],sources:[]});
  hud.update({playingPage:11,referenceTick:1,referenceSha256:sha});hud.showEvent(candidate('h','harmony',0,100));
  await Promise.resolve();hud.reset();complete({facts:{notes:[],written_marks:[]},derivations:[],uncertainties:[]});
  await new Promise(resolve=>setImmediate(resolve));assert.equal($('hud-detail').hidden,true);assert.equal($('hud-detail').children.length,0);
});
test('evidence table keeps octave, instrument, raw location and sustain separate',()=>{
  makeDOM();const target=new Element();
  appendEngineEvidence(target,{ppq:480,facts:{notes:[{part_id:'horn',pitch:57,start_tick:0,key_end_tick:480,sounding_end_tick:960,
    score_locations:[{page:15,physical_system_index:0,x_pt:200}],correspondence:{octave_agrees:true}}],written_marks:[]},
    derivations:[{sonority:{pitch_classes:[2,6,9],bass:21,candidates:[]},key_held_sonority:{pitch_classes:[2,6,9],bass:57,candidates:[]},pedal_residue_note_ids:['piano']}],uncertainties:['未核验录音']});
  for(const value of ['圆号','A3','15页','1.000／2.000','CC64','A0','未核验录音'])assert.ok(target.textContent.includes(value),value);
});
test('score-review cases are readable while retaining agent-only review status',()=>{
  makeDOM();const target=new Element();
  appendEngineEvidence(target,{facts:{notes:[],written_marks:[]},derivations:[],uncertainties:[],case_reviews:[{
    title:'F小七和弦的局部归约',observations:['低层F、C还原'],findings:['上层Ab、C、Eb'],unresolved:['局部调性未确立']}]});
  for(const text of ['代理读谱抽查','未升级为人工或专家验收','谱面观察','局部调性未确立'])assert.ok(target.textContent.includes(text));
});
test('direct score studies and opted-in engine candidates coexist without a source winner',()=>{
  const $=makeDOM(),data=fixture(),hud=createStructuralHUD({onEssay(){}});
  $('hud-auto-candidates').checked=true;
  data.events.push(candidate('automatic','harmony',0,100));
  data.events.push({id:'study',dimension:'harmony',short_label:'score argument',claim_level:'theoretical_analysis',
    analysis_origin:'score_study',html:'checked transcription, human pending',
    score_spans:[{precision:'page_range',pdf_page_start:1,pdf_page_end:1}],verification:{score:'agent_score_checked'}});
  hud.load(data);hud.update({playingPage:1,referenceTick:50,referenceSha256:sha});
  const text=$('structural-hud').children[0].textContent;
  assert.match(text,/score argument/);assert.match(text,/automatic/);
  hud.showDimension('harmony');assert.match($('hud-detail').textContent,/仅页级定位/);assert.match($('hud-detail').textContent,/人工签核待完成/);
  hud.update({playingPage:2,referenceTick:50,referenceSha256:sha});
  assert.match($('structural-hud').children[0].textContent,/automatic/);
});
test('automatic exploration is opt-in and never rewrites the article',()=>{
  const $=makeDOM(),hud=createStructuralHUD({onEssay(){}});
  hud.load({events:[candidate('automatic','harmony',0,100)],essays:[],sources:[]});
  $('essay-body').textContent='article kept';$('essay-body').scrollTop=120;
  hud.update({playingPage:11,referenceTick:50,referenceSha256:sha});
  assert.match($('structural-hud').children[0].textContent,/待分析/);
  $('hud-auto-candidates').checked=true;$('hud-auto-candidates').onchange();
  assert.match($('structural-hud').children[0].textContent,/automatic/);
  assert.equal($('essay-body').textContent,'article kept');assert.equal($('essay-body').scrollTop,120);
});
