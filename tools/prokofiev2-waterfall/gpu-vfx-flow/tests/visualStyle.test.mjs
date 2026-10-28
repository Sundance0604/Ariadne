import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
import test from 'node:test';
import { validateVisualStyle } from '../src/visualStyle.js';

const path = fileURLToPath(new URL('../visual-style.json', import.meta.url));
const style = JSON.parse(readFileSync(path, 'utf8'));

test('the approved visual style is a complete valid runtime configuration', () => {
  assert.equal(validateVisualStyle(style), style);
  assert.equal(style.geometry.piano_white_width, .70);
  assert.equal(style.geometry.piano_corner_radius, 14);
});

test('an invalid glow setting fails before rendering', () => {
  const invalid = structuredClone(style);
  invalid.light.note_bloom_brightness = 10;
  assert.throws(() => validateVisualStyle(invalid), /note_bloom_brightness/);
});
