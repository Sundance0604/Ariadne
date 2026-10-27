import test from 'node:test';
import assert from 'node:assert/strict';
import {createExportRenderer} from '../review/video-export.mjs';
import {buildPlaybackRegions,playheadPosition} from '../review/playhead.mjs';

function input(){
  const box=(id,page)=>({measure_id:id,page_number:page,system_index:0,page_width_pt:100,page_height_pt:200,rect_pt:[10,20,70,140],resolution:'bar'});
  return {config:{segments:[{video_start:0,video_end:20}],music_start_video:5,layout:{score:{x:100,y:20,w:100,h:200}}},
    annotations:[{slot:'interpretation',video_start:9,video_end:12}],
    project:{mapping:{measures:[box('a',1),box('b',2)]},alignment:{score_time_coverage:{start_seconds:5,end_seconds:20},
      time_map:[{audio_seconds:5,midi_seconds:0},{audio_seconds:10,midi_seconds:5},{audio_seconds:20,midi_seconds:10}],
      measures:[{measure_id:'a',start_seconds:5,end_seconds:10,midi_start_seconds:0,midi_end_seconds:5},
        {measure_id:'b',start_seconds:10,end_seconds:20,midi_start_seconds:5,midi_end_seconds:10}]}}};
}

test('renderAt is deterministic under reverse-order seeks; three clocks are explicit',()=>{
  const renderer=createExportRenderer(input()),first=renderer.renderAt(13);
  renderer.renderAt(18);renderer.renderAt(3);renderer.renderAt(11);
  assert.deepEqual(renderer.renderAt(13),first);
  assert.equal(first.outputTime,13);assert.equal(first.videoTime,13);assert.equal(first.musicTime,8);
});
test('intro stays clear, interpretation hides paper and restores the current page',()=>{
  const r=createExportRenderer(input());
  assert.equal(r.renderAt(3).visible,false);assert.equal(r.renderAt(9.5).visible,false);
  assert.equal(r.renderAt(11).page,2);assert.equal(r.renderAt(12).visible,true);assert.equal(r.renderAt(12).page,2);
  for(const t of [0,5,9,12,19])assert.deepEqual(r.renderAt(t).viewport,{x:100,y:20,w:100,h:200});
});
test('playhead uses the player algorithm rather than uniform bar timing',()=>{
  const data=input(),r=createExportRenderer(data),box=data.project.mapping.measures[1];
  const regions=buildPlaybackRegions(data.project.alignment.measures,new Map(data.project.mapping.measures.map(b=>[b.measure_id,b])));
  const p=playheadPosition(data.project.alignment.time_map,15,box,regions.get('b'));
  assert.equal(r.renderAt(15).playhead.x,100+p.leftPercent);
});
test('cuts preserve original video time; hidden interval still advances',()=>{
  const data=input();data.config.segments=[{video_start:0,video_end:8},{video_start:12,video_end:16}];
  const r=createExportRenderer(data);assert.equal(r.renderAt(8).videoTime,12);assert.equal(r.renderAt(8).page,2);
  assert.equal(r.renderAt(12),null);
});
test('whole-page errors and low-confidence positions never draw a large false highlight',()=>{
  const data=input();data.project.mapping.measures[0].rect_pt=[0,0,100,200];
  data.project.alignment.measures[1].flags=['weak_independent_pitch_evidence'];
  const r=createExportRenderer(data);
  assert.equal(r.renderAt(6).highlight,null);assert.equal(r.renderAt(6).issue,'invalid_or_whole_page_highlight');
  assert.equal(r.renderAt(15).playhead,null);assert.equal(r.renderAt(15).visible,true);
});
test('continuous line plan has knots at actual DTW changes and is finite',()=>{
  const plan=createExportRenderer(input()).plan();
  assert.ok(plan.events.some(e=>Math.abs(e.start-10)<1e-7));
  assert.ok(plan.events.every(e=>e.end>e.start&&e.viewport.w===100));
});
test('enlarged score follows a later system without changing viewport size or accumulating scroll',()=>{
  const data=input();data.config.score_zoom=2;data.project.mapping.measures[1].page_number=1;
  data.project.mapping.measures[1].rect_pt=[10,150,70,40];
  const r=createExportRenderer(data),late=r.renderAt(15);
  assert.ok(late.pageGeometry.scroll.top>0);assert.equal(late.viewport.h,200);
  r.renderAt(6);r.renderAt(18);assert.deepEqual(r.renderAt(15),late);
});
test('a shared cadenza suppresses the horizontal line without hiding its real score region',()=>{
  const data=input();data.project.mapping.measures[1].suppress_playhead=true;
  const r=createExportRenderer(data);assert.equal(r.renderAt(15).playhead,null);assert.ok(r.renderAt(15).highlight);
});
test('separately placed interpretation may keep PDF and the current score page visible',()=>{
  const data=input();data.config.interpretation_hides_score=false;
  assert.equal(createExportRenderer(data).renderAt(11).visible,true);
});

test('right aligned score paper reaches the viewport edge even when fitted by height',()=>{
  const data=input();data.config.layout.score={x:1320,y:320,w:600,h:736,align:'right'};
  const state=createExportRenderer(data).renderAt(15),g=state.pageGeometry;
  assert.equal(state.viewport.x+g.x+g.width,1920);
});
