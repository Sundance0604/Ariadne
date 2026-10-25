import assert from 'node:assert/strict';
import {test} from 'node:test';
import fs from 'node:fs';
import {measureNumberLabel,measureForNumber,numberedMeasureAtPoint} from '../review/measure-numbers.mjs';
import {prepareScoreRegions,scoreRegionAt} from '../review/score-follow.mjs';

test('candidate numbers, corrected numbers and multibar labels remain distinct',()=>{
  const note={score_measure_number:12,count_span:1,numbering_status:'inferred'};
  assert.equal(measureNumberLabel(note),'≈12');
  assert.equal(measureNumberLabel({...note,numbering_status:'corrected'}),'12');
  assert.equal(measureNumberLabel({...note,count_span:3}),'≈12–14');
  const measures=[{...note,movement:1},{...note,movement:2,count_span:3}];
  assert.equal(measureForNumber(measures,2,14),measures[1]);
  assert.equal(measureForNumber(measures,1,14),null);
  assert.equal(measureForNumber(measures,2,-1),null);
});

test('real physical measure rectangles drive fine highlighting and keep manual times',()=>{
  const read=p=>JSON.parse(fs.readFileSync(new URL(p,import.meta.url)));
  const doc=read('../works/mahler-4/measure-map.json'),alignment=read('../works/mahler-4/alignment.json');
  const index=read('../works/mahler-4/score-measures.json');
  const regions=prepareScoreRegions(doc,alignment,null,index);
  const first=regions.find(r=>r.region_id==='pdf-005-system-0-measure-0');
  assert.equal(scoreRegionAt(regions,(first.audioStart+first.audioEnd)/2).region_id,first.region_id);
  const hit=numberedMeasureAtPoint(index.measures,5,220/672,300/864);
  assert.equal(hit.region_id,first.region_id);
  assert.equal(hit.score_measure_number,1);
  assert.equal(regions.some(r=>r.region_id==='pdf-124-system-2'),false);
  const overridden=prepareScoreRegions(doc,alignment,{anchors:[{region_id:first.region_id,start_seconds:10,end_seconds:15}]},index);
  assert.equal(scoreRegionAt(overridden,12).region_id,first.region_id);
  assert.equal(scoreRegionAt(overridden,12).manual_timing,true);
  const parent=prepareScoreRegions(doc,alignment,{anchors:[{region_id:first.parent_region_id,start_seconds:0,end_seconds:60}]},index);
  assert.equal(parent.some(r=>r.parent_region_id===first.parent_region_id),false);
});
