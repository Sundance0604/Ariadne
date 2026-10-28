import assert from 'node:assert/strict';
import test from 'node:test';
import { buildTailParticles, sampleTailParticle,
         tailParticleAlpha } from '../src/tailBloom.js';

const config = { start_seconds: 640, full_seconds: 659,
  palette: { ice: '#70d7ff', cyan: '#5fffea', violet: '#9aa8ff',
             red: '#df4e66', gold: '#ffc776' } };
const notes = [639, 641, 650, 659, 665.7].map((time, index) => ({
  event_id: `note-${index}`, family: 'piano', midi_pitch: 60,
  audio_start: time, audio_end: time + .4,
}));

test('coda plumes grow denser and longer while launch speed falls', () => {
  const seeds = buildTailParticles(notes, config);
  const groups = notes.slice(1).map(note => seeds.filter(seed =>
    note.audio_start <= seed.birth && seed.birth < note.audio_end));
  assert.ok(groups[0].length < groups[2].length);
  const mean = (items, key) => items.reduce((sum, item) => sum + item[key], 0) / items.length;
  assert.ok(mean(groups[2], 'life') > 2 * mean(groups[0], 'life'));
  assert.ok(mean(groups[2], 'speed') < mean(groups[0], 'speed') * .75);
  assert.ok(groups[3].some(seed => seed.birth + seed.life > 672.05));
  assert.ok(!seeds.some(seed => seed.birth < 640));
});

test('the tail bends, sometimes drifts downward, and fades gradually', () => {
  const seeds = buildTailParticles(notes, config).filter(seed => seed.birth >= 659);
  let lateralReversals = 0, verticalReversals = 0;
  for (const seed of seeds) {
    const points = Array.from({ length: 24 }, (_, i) =>
      sampleTailParticle(seed, i * seed.life / 24));
    const dx = points.slice(1).map((point, i) => point.x - points[i].x);
    const dy = points.slice(1).map((point, i) => point.y - points[i].y);
    if (dx.some((value, i) => i && value * dx[i - 1] < 0)) lateralReversals++;
    if (dy.some((value, i) => i && value * dy[i - 1] < 0)) verticalReversals++;
    assert.ok(tailParticleAlpha(seed, seed.life - .05) <
              tailParticleAlpha(seed, seed.life - .7));
  }
  assert.ok(lateralReversals > seeds.length * .7);
  assert.ok(verticalReversals > 0);
});

test('expanded coda fills the stage while its ribbons expire first', () => {
  const expanded = { ...config, density_multiplier: 3,
    horizontal_spread_multiplier: 2.5, loft_multiplier: 1,
    ribbon_life_seconds: 2.6 };
  const lateNote = [notes.at(-1)];
  const prior = buildTailParticles(lateNote, config);
  const seeds = buildTailParticles(lateNote, expanded);
  assert.ok(seeds.length > prior.length * 2.7);
  assert.ok(seeds.every(seed => seed.ribbonLife < seed.life));
  const points = seeds.map(seed => sampleTailParticle(seed, 6));
  const xs = points.map(point => point.x);
  const ys = points.map(point => point.y);
  assert.ok(Math.max(...xs) - Math.min(...xs) > 600);
  assert.ok(Math.min(...ys) < -350);
});

test('late colour weights keep the large plume predominantly cool', () => {
  const cool = { ...config, density_multiplier: 3,
    palette_weights: [.44, .38, .12, .04, .02] };
  const repeated = Array.from({ length: 60 }, (_, i) => ({
    ...notes.at(-1), event_id: `palette-${i}`,
  }));
  const particles = buildTailParticles(repeated, cool);
  const warm = particles.filter(seed =>
    seed.color === config.palette.red || seed.color === config.palette.gold);
  assert.ok(warm.length / particles.length < .08);
  assert.ok(warm.length > 0);
});
