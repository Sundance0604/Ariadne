import test from 'node:test';
import assert from 'node:assert/strict';
import {makeDOM,Element,fixture} from './research-dom.mjs';
import {createMusicXMLReader} from '../review/musicxml-evidence.mjs';
import {createStructuralHUD} from '../review/structural-hud.mjs';

test('MusicXML reader exposes every measure without seeking or replacing an article',async()=>{
  const $=makeDOM(),base=document.getElementById,root=new Element('details');
  document.getElementById=id=>id==='musicxml-reader'?root:base(id);
  const reader=createMusicXMLReader();reader.reset();assert.equal(root.hidden,true);
  const payload=fixture();payload.musicxml={summary:{measures:535},measures:Array.from({length:535},(_,i)=>({measure_id:`xml-m${i+1}`,number:String(i+1),page:Math.floor(i/6)+1}))};
  reader.load(payload,'ravel-left-hand');assert.equal(root.hidden,false);
  const select=root.children.find(n=>n.tagName==='select');assert.equal(select.children.length,535);
  $('essay-body').append(new Element('article'));const article=$('essay-body').children[0];$('essay-body').scrollTop=137;
  globalThis.fetch=async url=>({ok:true,json:async()=>({measure:{number:'34',page:11},part_registry:[],harmony:[],
    orchestration:[{parts:[]}],intervals:[],chordal_intervals:[],hierarchy:[],motif_comparisons:[],cadences:[],events:[]})});
  select.value='xml-m34';await root.children.find(n=>n.tagName==='button').onclick();
  assert.match(root.textContent,/第34小节/);assert.match(root.textContent,/不改变播放位置/);
  assert.equal($('essay-body').children[0],article);assert.equal($('essay-body').scrollTop,137);
  reader.reset();reader.load(fixture(),'lark-ascending');assert.equal(root.hidden,true);
});

test('a late MusicXML response cannot repopulate a reset track',async()=>{
  makeDOM();const base=document.getElementById,root=new Element('details');document.getElementById=id=>id==='musicxml-reader'?root:base(id);
  const reader=createMusicXMLReader();reader.load({musicxml:{summary:{measures:1},measures:[{measure_id:'xml-m1',number:1,page:1}]}},'ravel-left-hand');
  let finish;globalThis.fetch=()=>new Promise(resolve=>{finish=resolve;});
  const loading=root.children.find(n=>n.tagName==='button').onclick();reader.reset();
  finish({ok:true,json:async()=>({})});await loading;assert.equal(root.hidden,true);
});

test('XML measure index is not a duplicate card; curated research remains and auxiliary data is opt-in',()=>{
  const $=makeDOM(),hud=createStructuralHUD({onEssay(){}}),d=fixture();
  d.events[0].analysis_origin='musicxml_analysis';d.events[1].analysis_origin='engine_candidate';
  d.events.push({...d.events[0],id:'study',short_label:'direct study',analysis_origin:'score_study'});
  hud.load(d);hud.update({playingPage:1});assert.doesNotMatch($('structural-hud').textContent,/hypothesis A/);
  assert.match($('structural-hud').textContent,/direct study/);assert.doesNotMatch($('structural-hud').textContent,/hypothesis B/);
});
