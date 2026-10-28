import test from 'node:test';
import assert from 'node:assert/strict';
import { sampleVisualPreset } from '../src/visualTimeline.js';

test('musical transition eases numeric, color and discrete material controls', () => {
  const sections = [
    { start_seconds: 0, preset: { colors: { piano_low: '#000000' },
       density: { ember_per_second: 20 }, appearance: { material: 'metal', fire_mix: 0 } } },
    { start_seconds: 10, transition_seconds: 2, preset: {
      colors: { piano_low: '#ffffff' }, density: { ember_per_second: 100 },
      appearance: { material: 'fire', fire_mix: 1 } } },
  ];
  assert.equal(sampleVisualPreset(10, sections, {}).colors.piano_low, '#000000');
  const middle = sampleVisualPreset(11, sections, {});
  assert.equal(middle.colors.piano_low, '#808080');
  assert.equal(middle.density.ember_per_second, 60);
  assert.equal(middle.appearance.fire_mix, .5);
  assert.equal(middle.appearance.material, 'fire');
  assert.equal(sampleVisualPreset(12, sections, {}).colors.piano_low, '#ffffff');
});
