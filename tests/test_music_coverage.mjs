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
