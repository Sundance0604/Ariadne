import assert from 'node:assert/strict';
import {test} from 'node:test';
import {prepareScoreRegions,scoreRegionAt,scoreRegionAtPoint} from '../review/score-follow.mjs';
import {playheadPosition} from '../review/playhead.mjs';

const alignment={time_map:[{midi_seconds:0,audio_seconds:20},{midi_seconds:10,audio_seconds:32},{midi_seconds:20,audio_seconds:50}]};

test('independent movement maps preserve the last bar before a source-free interlude',()=>{
  const a={time_map:[{midi_seconds:0,audio_seconds:20},{midi_seconds:10,audio_seconds:40},{midi_seconds:10,audio_seconds:100},{midi_seconds:20,audio_seconds:120}],
    time_maps:[{id:'first',time_map:[{midi_seconds:0,audio_seconds:20},{midi_seconds:10,audio_seconds:40}]}]};
  const geometry={score_regions:[{region_id:'last',midi_start_seconds:8,midi_end_seconds:10,alignment_segment:'first',page_number:1,page_width_pt:600,page_height_pt:800,rect_pt:[50,50,200,300]},
    {region_id:'cadenza',audio_start_seconds:40,audio_end_seconds:100,no_symbolic_projection:true,page_number:2,page_width_pt:600,page_height_pt:800,rect_pt:[50,50,400,300]}]};
  const regions=prepareScoreRegions(geometry,a);
  assert.equal(regions[0].audioEnd,40);assert.equal(scoreRegionAt(regions,39).region_id,'last');
  const cadenza=scoreRegionAt(regions,80);assert.equal(cadenza.region_id,'cadenza');
  assert.equal(playheadPosition(a.time_map,80,cadenza,cadenza),null);
});
const document={score_regions:[
  {region_id:'bar-a',midi_start_seconds:0,midi_end_seconds:8,page_number:5,
    page_width_pt:600,page_height_pt:800,rect_pt:[100,50,100,300],resolution:'bar'},
  {region_id:'bar-b',midi_start_seconds:10,midi_end_seconds:20,page_number:6,
    page_width_pt:600,page_height_pt:800,rect_pt:[50,400,400,300],resolution:'system_candidate'}]};

test('observed PDF regions follow nonlinear reference times, without filling unmatched gaps',()=>{
  const regions=prepareScoreRegions(document,alignment);
  assert.equal(regions[0].audioStart,20);assert.equal(regions[0].audioEnd,29.6);
  assert.equal(scoreRegionAt(regions,0),null);assert.equal(scoreRegionAt(regions,25).region_id,'bar-a');
  assert.equal(scoreRegionAt(regions,31),null);assert.equal(scoreRegionAt(regions,40).page_number,6);
  assert.equal(scoreRegionAt(regions,50),null);
});
test('coordinate clicks seek the matching physical region; playhead stays in its observed rectangle',()=>{
  const regions=prepareScoreRegions(document,alignment);
  const hit=scoreRegionAtPoint(regions,6,100/600,450/800);assert.equal(hit.region_id,'bar-b');
  assert.equal(scoreRegionAtPoint(regions,5,0,0),null);
  const position=playheadPosition(alignment.time_map,41,hit,hit);
  assert.equal(position.fraction,.5);assert.equal(position.leftPercent,250/600*100);
});
test('recomputing alignment updates time boundaries while preserving PDF coordinates',()=>{
  const regions=prepareScoreRegions(document,{time_map:alignment.time_map.map(p=>({...p,audio_seconds:p.audio_seconds+3}))});
  assert.equal(regions[0].audioStart,23);assert.deepEqual(regions[0].rect_pt,[100,50,100,300]);
});
test('clicking a repeated physical bar keeps the active occurrence',()=>{
  const first={...document.score_regions[0],audioStart:20,audioEnd:30};
  const repeat={...first,region_id:'second-visit',audioStart:100,audioEnd:110};
  assert.equal(scoreRegionAtPoint([first,repeat],5,150/600,100/800,105).region_id,'second-visit');
  assert.equal(scoreRegionAtPoint([first,repeat],5,150/600,100/800,25).region_id,'bar-a');
});
test('microsecond media seek rounding lands in the intended next bar',()=>{
  const regions=[{audioStart:2,audioEnd:6.013333333333333,rect_pt:[0,0,100,100],region_id:'before'},
    {audioStart:6.013333333333333,audioEnd:8,rect_pt:[0,0,100,100],region_id:'after'}];
  assert.equal(scoreRegionAt(regions,6.013333).region_id,'after');
  assert.equal(scoreRegionAt(regions,6.013).region_id,'before');
  assert.equal(scoreRegionAt(regions,8),null);
});
test('finer candidates fall back to their system and manual timing takes priority',()=>{
  const doc={score_regions:[document.score_regions[1]],bar_regions:[{...document.score_regions[1],
    region_id:'child',parent_region_id:'bar-b',midi_start_seconds:12,midi_end_seconds:14,
    rect_pt:[50,400,100,300],stable_candidate:true}]};
  let regions=prepareScoreRegions(doc,alignment);
  assert.equal(scoreRegionAt(regions,37).region_id,'child');
  assert.equal(scoreRegionAt(regions,45).region_id,'bar-b');
  assert.equal(scoreRegionAt(regions,45,true),null);
  regions=prepareScoreRegions(doc,alignment,{anchors:[{region_id:'bar-b',start_seconds:35,end_seconds:48}]});
  assert.equal(regions.length,1);assert.equal(scoreRegionAt(regions,40).region_id,'bar-b');
  assert.equal(scoreRegionAt(regions,40).manual_timing,true);
  const position=playheadPosition(alignment.time_map,41.5,regions[0],regions[0]);assert.equal(position.fraction,.5);
});
