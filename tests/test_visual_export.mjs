import test from 'node:test';
import assert from 'node:assert/strict';
import {intervalIndex} from '../review/interval-index.mjs';
import {createVisualExport} from '../review/visual-export.mjs';
test('indexed windows preserve long ties, simultaneous boundaries and reverse seeks',()=>{
  const index=intervalIndex([{id:'long',start_seconds:0,end_seconds:20},{id:'a',start_seconds:1,end_seconds:2},{id:'b',start_seconds:2,end_seconds:3}]);
  assert.deepEqual(index.between(2,2).map(e=>e.id),['long','b']);
  index.between(15,16);assert.deepEqual(index.between(1.5,1.5).map(e=>e.id),['long','a']);
  assert.equal(index.lastStart(2),2);assert.equal(index.lastEnd(2),2);
});
test('full-video intro, movement pauses and applause leave the new visual layer transparent',()=>{
  const activity={parts:[],events:[],coverage:{segments:[{start_seconds:10,end_seconds:20},{start_seconds:30,end_seconds:40}]}};
  const renderer=createVisualExport({notes:[]},activity,{width:400,height:240,panels:{flow:{x:0,y:0,width:400,height:240}},overlay_x:0,overlay_y:0});
  for(const t of [0,9,20,25,40])assert.equal(renderer.at(t).commands.length,0);
  assert.ok(renderer.at(12).commands.length>0);assert.deepEqual(renderer.at(12),renderer.at(12));
});
