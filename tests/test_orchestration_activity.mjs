import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createOrchestrationActivity} from '../review/orchestration-activity.mjs';
import {createHarmonicFlow} from '../review/harmonic-flow.mjs';
const part={id:'v1',label:'第一小提琴',family:'弦乐',color:'#FFDF42',flow_group:'v1'};
const fixture={parts:[part],coverage:{segments:[{start_seconds:0,end_seconds:6}]},events:[
  {id:'tie',event_ids:['a','b'],part_id:'v1',start_seconds:0,end_seconds:2},
  {id:'repeat',event_ids:['c'],part_id:'v1',start_seconds:3,end_seconds:4}]};
test('onset flashes, ties sustain without reattack, release fades and uncovered time clears',()=>{
  const model=createOrchestrationActivity(fixture);
  assert.ok(model.frame(.02).states[0].level>model.frame(1).states[0].level);
  assert.equal(model.frame(1).states[0].attack,false);assert.equal(model.frame(1).states[0].active,true);
  assert.deepEqual(model.frame(1).states[0].event_ids,['a','b']);
  assert.equal(model.frame(2).states[0].active,false);assert.equal(model.frame(2.3).states[0].level,0);
  assert.equal(model.frame(3.02).states[0].attack,true);assert.equal(model.frame(6).states[0].level,0);
});
test('seeking produces deterministic states and unknown source timing never implies rest',()=>{
  const model=createOrchestrationActivity({...fixture,unknown_intervals:[{part_id:'v1',start_seconds:4,end_seconds:5}]});
  const expected=model.frame(1);model.frame(5.5);assert.deepEqual(model.frame(1),expected);
  assert.equal(model.frame(4.5).states[0].unknown,true);
});
test('quartet keeps four independent modules and colors rather than one string tile',()=>{
  const parts=['v1','v2','va','vc'].map((id,i)=>({...part,id,label:id,color:['#F2B859','#FBCF4A','#F4E150','#DDE56B'][i],flow_group:id}));
  const data={parts,events:[],notes:[]},frame=createOrchestrationActivity(data).frame(1);
  assert.equal(frame.states.length,4);assert.equal(frame.height,108);
  const texts=createHarmonicFlow(data).frame(1).commands.filter(c=>c.op==='text').map(c=>c.text);
  for(const p of parts)assert.ok(texts.includes(p.label));assert.ok(!texts.includes('钢琴'));
});
test('nonpitched percussion uses a separate lane without inventing a pitch class',()=>{
  const data={parts:[{...part,id:'dr',family:'打击乐',label:'小鼓',flow_group:'dr'}],notes:[],
    percussion:[{id:'hit',part_id:'dr',start_seconds:1,end_seconds:1.2}]};
  const frame=createHarmonicFlow(data).frame(1.1);
  assert.deepEqual(frame.active_pitch_classes,[]);assert.deepEqual(frame.visible_percussion_ids,['hit']);
  assert.ok(frame.commands.some(c=>c.op==='text'&&c.text==='打击'));
});
test('the harmony legend keeps every instrument even with legacy five-family grouping fields',()=>{
  const parts=Array.from({length:19},(_,i)=>({id:`p${i}`,label:`乐器${i}`,family:`组${i%5}`,flow_group:`组${i%5}`,color:'#FFDF42'}));
  const frame=createHarmonicFlow({parts,notes:[]}).frame(1);
  assert.equal(frame.instrument_ids.length,19);
  for(const part of parts)assert.ok(frame.commands.some(c=>c.op==='text'&&c.text===part.label));
});
test('Prokofiev harmony explicitly shows five categories while orchestration retains nineteen instruments',()=>{
  const registry=JSON.parse(fs.readFileSync(new URL('../works/prokofiev-piano-concerto-2/metadata/visual-parts.json',import.meta.url),'utf8'));
  const data={parts:registry.parts,flow_groups:registry.harmony_groups,notes:[],events:[]};
  const harmony=createHarmonicFlow(data).frame(1),orchestration=createOrchestrationActivity(data).frame(1);
  assert.equal(harmony.group_ids.length,5);assert.equal(harmony.height,240);
  assert.deepEqual(registry.harmony_groups.map(g=>g.label),['钢琴','弦乐','木管','铜管','打击乐']);
  assert.equal(orchestration.states.length,19);assert.equal(harmony.instrument_ids.length,19);
  for(const g of registry.harmony_groups)assert.ok(harmony.commands.some(c=>c.op==='text'&&c.text===g.label));
  assert.ok(!harmony.commands.some(c=>c.op==='text'&&c.text==='第一小提琴'));
});
