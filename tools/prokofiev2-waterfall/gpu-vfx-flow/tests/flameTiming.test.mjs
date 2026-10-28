import assert from 'node:assert/strict';
import test from 'node:test';
import { sampleFlameEnvelope } from '../src/flameTiming.js';

test('a flame grows upward from zero at contact', () => {
  const start = sampleFlameEnvelope(0, 1);
  const early = sampleFlameEnvelope(.04, 1);
  const middle = sampleFlameEnvelope(.14, 1);
  const held = sampleFlameEnvelope(.5, 1);
  assert.deepEqual(start, { growth: 0, intensity: 0 });
  assert.ok(0 < early.growth && early.growth < middle.growth);
  assert.ok(middle.growth < held.growth);
  assert.equal(held.growth, 1);
  assert.ok(early.intensity < held.intensity);
});

test('a released flame fades instead of vanishing at note end', () => {
  const held = sampleFlameEnvelope(.99, 1);
  const released = sampleFlameEnvelope(1.13, 1);
  const gone = sampleFlameEnvelope(1.26, 1);
  assert.equal(held.intensity, 1);
  assert.ok(released.intensity > 0 && released.intensity < held.intensity);
  assert.ok(released.growth > 0 && released.growth < held.growth);
  assert.deepEqual(gone, { growth: 0, intensity: 0 });
});
