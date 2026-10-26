import assert from 'node:assert/strict';
import {test} from 'node:test';
import {indexResearch,activeEvents,spanMatches,spanNavigation} from '../review/research-model.mjs';
import {createStructuralHUD} from '../review/structural-hud.mjs';
import {makeDOM,fixture} from './research-dom.mjs';

test('dimension intervals, overlap, gaps and unlocated items remain separate',()=>{
  const index=indexResearch(fixture());
  assert.equal(activeEvents(index,{playingPage:1}).get('harmony').length,2);
  assert.equal(activeEvents(index,{playingPage:2}).get('harmony').length,0);
  assert.equal(activeEvents(index,{playingPage:2}).get('orchestration').length,1);
  assert.equal(spanMatches({precision:'unlocated'},{playingPage:1}),false);
  const span={precision:'score_segment',pdf_page_start:1,pdf_page_end:1,score_start:[1,0,20],score_end:[1,0,40]};
  assert.equal(spanMatches(span,{playingPage:1,systemIndex:0,x:20}),true);
  assert.equal(spanMatches(span,{playingPage:1,systemIndex:0,x:40}),false);
  assert.equal(spanMatches({...span,precision:'score_segment_candidate',region_ids:['region']},{playingPage:1,regionId:'other'}),false);
});
test('HUD discloses page background and does not rebuild unchanged dimensions',()=>{
  const $=makeDOM(),hud=createStructuralHUD({onEssay(){}});hud.load(fixture());
  hud.update({playingPage:1,browsedPage:8,time:10});
  assert.match($('hud-position').textContent,/播放位置.*1.*浏览页.*8/);
  assert.match($('structural-hud').textContent,/本页／本段背景/);
  assert.match($('structural-hud').textContent,/多条观点并列/);
  const orchestration=$('structural-hud').children[3].children[1];
  const count=orchestration.replacements;
  hud.update({playingPage:2,browsedPage:8,time:11});
  assert.equal(orchestration.replacements,count);
  assert.doesNotMatch($('structural-hud').textContent,/hypothesis A/);
  hud.update({playingPage:null,browsedPage:1});assert.match($('structural-hud').textContent,/待分析/);
  hud.reset();assert.doesNotMatch($('structural-hud').textContent,/instrument C/);
});
test('navigation never turns page precision or candidate times into exact seeking',()=>{
  const regions=[{region_id:'r',audioStart:12,manual_timing:true}];
  const verified={location:'verified',timing:'manual_reviewed'};
  const span={precision:'page_range',pdf_page_start:3,region_ids:['r']};
  assert.equal(spanNavigation(span,verified,regions).canSeek,false);
  assert.equal(spanNavigation({...span,precision:'score_segment'},verified,regions).time,12);
  assert.equal(spanNavigation({...span,precision:'score_segment'},{...verified,timing:'candidate_alignment'},regions).canSeek,false);
});

test('harmonic evidence shows concert-pitch distribution and actual inversion',()=>{
  const $=makeDOM(),data=fixture(),hud=createStructuralHUD({onEssay(){}});
  data.events[0].harmonic_analysis={system:'functional_tonal',key_context:'D major',root:'D',bass:'A3',
    roman_numeral:'I6/4',inversion:'second',pitch_collection:['D','F#','A'],omitted_tones:[],
    temporal_scope:'orchestral upbeat only',voices:[{instrument:'horns',pitches:['A3','D4'],role:'bass and filling'}],
    voice_leading:'bass D arrives later',nonchord_tones:'none in this sample'};
  hud.load(data);hud.update({playingPage:1});
  $('structural-hud').children[0].children[1].children.find(n=>n.tagName==='button').onclick();
  assert.match($('hud-detail').textContent,/实音/);
  assert.match($('hud-detail').textContent,/A3/);
  assert.match($('hud-detail').textContent,/第二转位/);
  assert.match($('hud-detail').textContent,/orchestral upbeat only/);
  assert.match($('hud-detail').textContent,/horns/);
  hud.reset();assert.equal($('hud-detail').hidden,true);
});
