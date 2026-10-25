import assert from 'node:assert/strict';
import {test} from 'node:test';
import {prepareScoreRegions,scoreRegionAt,scoreRegionAtPoint} from '../review/score-follow.mjs';
import {playheadPosition} from '../review/playhead.mjs';

const alignment={time_map:[{midi_seconds:0,audio_seconds:20},{midi_seconds:10,audio_seconds:32},{midi_seconds:20,audio_seconds:50}]};
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
