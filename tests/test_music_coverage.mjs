import test from 'node:test';
import assert from 'node:assert/strict';
import {scoreTimeCovered} from '../review/playhead.mjs';

test('video applause and intro do not activate score-time evidence; old tracks retain coverage',()=>{
  const coverage={start_seconds:27.5,end_seconds:1162.5};
  for(const t of [0,8,27.49,1162.5,1190,NaN])assert.equal(scoreTimeCovered(coverage,t),false);
  for(const t of [27.5,30,334,1162.49])assert.equal(scoreTimeCovered(coverage,t),true);
  assert.equal(scoreTimeCovered(undefined,0),true);
  assert.equal(scoreTimeCovered(undefined,1090),true);
});

test('independent movement coverage excludes pauses inside the complete recording',()=>{
  const coverage={start_seconds:40,end_seconds:1900,segments:[
    {start_seconds:40,end_seconds:700},{start_seconds:725,end_seconds:860},
    {start_seconds:875,end_seconds:1265},{start_seconds:1285,end_seconds:1900}]};
  for(const t of [0,39.9,700,710,724.99,860,870,1265,1284.99,1900,2100])assert.equal(scoreTimeCovered(coverage,t),false,t);
  for(const t of [40,699.9,725,859.99,875,1264.99,1285,1899.99])assert.equal(scoreTimeCovered(coverage,t),true,t);
});
