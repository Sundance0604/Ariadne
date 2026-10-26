import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createScoreAnalysisModel,conditionalFigure,surfaceLabel} from '../review/score-analysis-model.mjs';
import {frameAt} from '../review/musicxml-live.mjs';
import {createStructuralHUD} from '../review/structural-hud.mjs';
import {makeDOM,Element} from './research-dom.mjs';
const read=p=>JSON.parse(fs.readFileSync(new URL('../'+p,import.meta.url),'utf8'));
const base=read('analysis/musicxml/current.json').path,interpretation=read('analysis/musicxml/interpretation-current.json').path;
const harmony=read(base+'/harmony.json').windows,frames=read(interpretation+'/activation.json').frames;
const raw=read(interpretation+'/harmonic-readings.json').readings;
const cases=read(read('analysis/hud/current.json').path+'/cases.json');
const data={windows:Object.fromEntries(harmony.map(w=>[w.id,{...w.sonority,pitches:w.sonority.spelled_pitches,id:w.id,event_ids:w.event_ids}])),
  frames,readings:Object.fromEntries(Object.entries(raw).map(([id,rs])=>[id,rs.map(r=>({...r,layer_bass:r.description.bass,chord:r.description.chord}))])),
  hud_cases:cases,form:read(interpretation+'/form-synthesis.json')};
function snapshot(q){const frame=frameAt(frames,q),i=frames.indexOf(frame);return {data,quarter:q,frame,previousFrame:frames[i-1]};}
const model=createScoreAnalysisModel();model.load({events:[],essays:[],sources:[]});
const view=q=>model.view({playingPage:snapshot(q).frame?.page},snapshot(q));

test('m11 keeps global E1, layer D2 and sustained context as separate objects',()=>{
  const v=view(31),r=v.harmony.alternatives.find(r=>r.kind==='bass_pitch_class_layer_reduction');
  assert.equal(v.harmony.surface.bass.name,'E1');assert.equal(r.layer_bass.name,'D2');assert.equal(r.chord.root,'G');assert.equal(r.chord.inversion,2);
  assert.equal(v.harmony.contextual.length,1);assert.equal(view(31.25).harmony.contextual[0],v.harmony.contextual[0]);
  assert.equal(view(33).harmony.contextual.length,0);
});
test('m58 names an open fifth without a third, root or invented background',()=>{
  const v=view(1321/8);assert.match(v.harmony.surface.label,/开放五度/);
  assert.equal(v.harmony.surface.chord,null);assert.equal(v.harmony.contextual.length,0);
  assert.deepEqual(v.orchestration.activeParts.map(p=>p.part_id),['P23']);
});
test('m63–64 uses four real windows rather than one bar-wide chord',()=>{
  const vs=[751/4,188,188.75,189].map(view);
  assert.deepEqual(vs.map(v=>v.harmony.surface.bass.name),['A3','A3','A1','D1']);
  assert.equal(vs[0].harmony.surface.chord.inversion,2);
  assert.equal(vs[1].harmony.alternatives.find(r=>r.kind==='bass_pitch_class_layer_reduction').chord.root,'E');
});
test('m520 adds bass clarinet after low strings and preserves stable form',()=>{
  const a=view(1517),b=view(1517.75);
  assert.deepEqual(a.orchestration.activeParts.map(p=>p.part_id),['P23','P30','P32','P35']);
  assert.deepEqual(b.orchestration.transitions.entered.map(p=>p.part_id),['P7']);
  assert.equal(a.signatures.form,b.signatures.form);
});
test('unpitched activity alone does not invalidate the harmony/background signature',()=>{
  const i=frames.findIndex((f,i)=>i>0&&f.harmony_window_id&&f.harmony_window_id===frames[i-1].harmony_window_id&&
    JSON.stringify(f.active_instruments.map(p=>p.part_id))!==JSON.stringify(frames[i-1].active_instruments.map(p=>p.part_id)));
  assert.ok(i>0);const a=view(frames[i-1].start_q),b=view(frames[i].start_q);
  assert.equal(a.signatures.harmony,b.signatures.harmony);assert.notEqual(a.signatures.orchestration,b.signatures.orchestration);
});
test('one four-card HUD keeps context/form DOM and article scroll across updates and evidence switches',()=>{
  const $=makeDOM(),article=new Element('article');$('essay-body').append(article);$('essay-body').scrollTop=173;
  let opened=0;const hud=createStructuralHUD({onOpen:()=>opened++});hud.load({events:[],essays:[],sources:[]});
  hud.update({playingPage:3,browsedPage:3},snapshot(31));assert.equal($('structural-hud').children.length,4);
  const harmonyCard=$('structural-hud').children[0],formCard=$('structural-hud').children[3];
  const background=harmonyCard.children[1].children[1],formNode=formCard.children[1];
  const backgroundText=background.textContent,formText=formNode.textContent;
  hud.update({playingPage:3,browsedPage:12},snapshot(31.25));
  assert.equal(harmonyCard.children[1].children[1],background);assert.equal(background.textContent,backgroundText);
  assert.equal(formCard.children[1],formNode);assert.equal(formNode.textContent,formText);
  harmonyCard.children[1].onclick();assert.equal(opened,1);const evidence=$('hud-detail').children[0];
  hud.update({playingPage:12,browsedPage:12},snapshot(1321/8));assert.equal($('hud-detail').children[0],evidence);
  assert.equal($('essay-body').children[0],article);assert.equal($('essay-body').scrollTop,173);
  hud.reset();assert.equal($('hud-detail').hidden,true);assert.doesNotMatch($('structural-hud').textContent,/G小七|钢琴独奏/);
});
test('withheld figures and enharmonic spelling cannot silently become ordinary functional labels',()=>{
  assert.match(conditionalFigure({context:'B小调',figure:'bVI',pitch_classes_agree:false}),/待审查/);
  assert.match(surfaceLabel({pitch_classes:[4],pitches:['E1','Fb1']}),/E1.*Fb1/);
});
test('a located unpitched frame differs from an uncovered position and has no harmonic pitches',()=>{
  const v=model.view({playingPage:2},{data,quarter:10,frame:{measure_id:'xml-m0004',page:2,number:4,onset_q:'0',
    harmony_window_id:null,active_instruments:[{part_id:'P18',label:'打击乐组',pitches:[],roles:['节奏／音色层']}]} });
  assert.match(v.harmony.surface.label,/无有效定音/);assert.deepEqual(v.harmony.surface.pitches,[]);
  assert.equal(v.orchestration.activeParts[0].part_id,'P18');
  assert.equal(model.view({},{data,quarter:null,frame:null}).harmony.surface,null);
});
test('expanded cards retain every active part, layer reading and full structural model',()=>{
  const $=makeDOM(),hud=createStructuralHUD({});hud.load({events:[],essays:[],sources:[]});
  const snap=snapshot(188);hud.update({playingPage:15,browsedPage:15},snap);
  const cards=$('structural-hud').children;
  for(const p of snap.frame.active_instruments)assert.ok(cards[1].textContent.includes(p.label),p.label);
  for(const r of data.readings[snap.frame.harmony_window_id])if(r.kind!=='complete_vertical')assert.ok(cards[0].textContent.includes(r.label),r.label);
  for(const m of data.form.models)assert.ok(cards[3].textContent.includes(m.reading),m.name);
  assert.match(surfaceLabel(data.windows['xml-h-001206']),/第二转位/);
  assert.equal($('structural-hud').children.length,4);
});
