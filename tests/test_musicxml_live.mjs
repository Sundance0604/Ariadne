import test from 'node:test';
import assert from 'node:assert/strict';
import {frameAt,projectedQuarter,createMusicXMLLive} from '../review/musicxml-live.mjs';
import {makeDOM,Element} from './research-dom.mjs';

test('score-time activation is half-open, rejects uncovered gaps, and clears the last frame',()=>{
  const frames=[{id:'a',start_q:0,end_q:1},{id:'b',start_q:1,end_q:2},{id:'c',start_q:3,end_q:4}];
  assert.equal(frameAt(frames,1).id,'b');assert.equal(frameAt(frames,2),null);
  assert.equal(frameAt(frames,1-1e-10).id,'b');assert.equal(frameAt(frames,1-1e-5).id,'a');
  assert.equal(frameAt(frames,4),null);assert.equal(frameAt(frames,null),null);
});
test('tempo changes remain nonlinear in time and the truncated tail is never extrapolated',()=>{
  const p={ppq:480,reference_end_seconds:3,reference_end_quarter:2.5,
    reference_clock:[{tick:0,midi_seconds:0,seconds_per_tick:1/480},{tick:480,midi_seconds:1,seconds_per_tick:2/480}]};
  assert.equal(projectedQuarter(p,1),1);assert.equal(projectedQuarter(p,2),1.5);
  assert.equal(projectedQuarter(p,3),null);assert.equal(projectedQuarter(p,-1),null);
});

test('all current instruments and alternative readings update without touching the essay',async()=>{
  const $=makeDOM(),base=document.getElementById,root=new Element('section');document.getElementById=id=>id==='musicxml-live'?root:base(id);
  $('essay-body').textContent='persistent';$('essay-body').scrollTop=110;
  const payload={available:true,projection:{ppq:1,reference_end_seconds:3,reference_end_quarter:3,
    reference_clock:[{tick:0,midi_seconds:0,seconds_per_tick:1}]},frames:[
      {id:'a',start_q:0,end_q:1,number:'1',page:1,onset_q:'0',harmony_window_id:'h',active_instruments:[
        {label:'圆号',roles:['持续层'],pitches:['E4'],instrument_names:[]},{label:'巴松',roles:['低音支撑'],pitches:['A2'],instrument_names:[]}]},
      {id:'b',start_q:1,end_q:2,number:'1',page:1,onset_q:'1',harmony_window_id:'h',active_instruments:[]}],
    readings:{h:[{label:'读法一',functions:[],kind:'complete_vertical'},{label:'读法二',functions:[],kind:'complete_vertical'}]}};
  globalThis.fetch=async()=>({ok:true,json:async()=>payload});const panel=createMusicXMLLive();await panel.load('ravel-left-hand');
  assert.equal(panel.at(0).data,payload);assert.equal(panel.at(0).frame.active_instruments.length,2);
  assert.equal(panel.at(1.5).frame.active_instruments.length,0);assert.equal(panel.at(3).frame,null);
  assert.equal(root.children.length,0,'provider must not create a second harmony/orchestration UI');
  assert.equal($('essay-body').textContent,'persistent');assert.equal($('essay-body').scrollTop,110);
});

test('an old performance response cannot activate instruments after a track reset',async()=>{
  makeDOM();const base=document.getElementById,root=new Element('section');document.getElementById=id=>id==='musicxml-live'?root:base(id);
  let finish;globalThis.fetch=()=>new Promise(resolve=>{finish=resolve;});const panel=createMusicXMLLive();const request=panel.load('ravel-left-hand');panel.reset();
  finish({ok:true,json:async()=>({available:true})});await request;assert.equal(panel.at(0).data,null);
});
