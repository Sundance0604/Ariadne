import test from 'node:test';
import assert from 'node:assert/strict';
import {createHarmonicFlow} from '../review/harmonic-flow.mjs';
const n=(id,pc,start,end,part='P15')=>({id,pc,start_seconds:start,end_seconds:end,part_id:part,family:'键盘／拨弦'});
const make=notes=>createHarmonicFlow({notes,coverage:{segments:[{start_seconds:0,end_seconds:10}]}});
test('seeking and pausing give the same absolute frame; uncovered gaps stay empty',()=>{
  const flow=make([n('a',0,1,3),n('b',7,4,5)]),first=flow.frame(2);flow.frame(8);
  assert.deepEqual(flow.frame(2),first);assert.deepEqual(first.active_pitch_classes,[0]);
  assert.deepEqual(flow.frame(10).visible_note_ids,[]);
});
test('doubling the same pitch class/family never increases brightness',()=>{
  const a=make([n('a',0,1,3)]).frame(2),b=make([n('a',0,1,3),n('b',0,1,3)]).frame(2);
  assert.deepEqual(a.commands,b.commands);assert.equal(b.visible_note_ids.length,2);
});
test('part filtering and half-open ends retain objective activity',()=>{
  const flow=make([n('a',0,1,3),n('b',7,2,4,'P1')]);
  assert.deepEqual(flow.frame(3).active_pitch_classes,[7]);
  assert.deepEqual(flow.frame(2,{partIds:['P1']}).active_pitch_classes,[7]);
  assert.equal(flow.frame(2,{width:800,height:480}).commands[0].w,800);
});
