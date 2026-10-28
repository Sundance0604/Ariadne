import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { createFlowEmitter, filamentExitFade,
         sampleFlowParticle } from '../src/flowMotion.js';
import { validateVisualPreset } from '../src/visualPreset.js';

const preset = validateVisualPreset(JSON.parse(
  readFileSync(new URL('../visual-preset.json', import.meta.url), 'utf8')));

function mean(values) { return values.reduce((sum, value) => sum + value, 0) / values.length; }

test('a held key keeps releasing changing streams', () => {
  let turningStreams = 0;
  let changingSpeeds = 0;
  for (const id of ['a', 'b', 'c']) {
    const sparks = createFlowEmitter(id, .9, preset).seeds.filter(seed => seed.type === 0);
    const groups = [[0, .08], [.25, .33], [.6, .7]].map(([a, b]) =>
      sparks.filter(seed => seed.birth >= a && seed.birth < b));
    assert.ok(sparks.filter(seed => seed.birth >= .7 && seed.birth < .9).length > 15,
      'particles must still be born near the note end');
    const bearing = group => mean(group.map(seed => Math.atan2(seed.vx, -seed.vy)));
    const speed = group => mean(group.map(seed => Math.hypot(seed.vx, seed.vy)));
    const bearings = groups.map(bearing), speeds = groups.map(speed);
    if (Math.max(...bearings) - Math.min(...bearings) > .08) turningStreams++;
    if (Math.max(...speeds) - Math.min(...speeds) > 20) changingSpeeds++;
  }
  assert.equal(turningStreams, 3, 'every short note must turn its nozzle');
  assert.equal(changingSpeeds, 3, 'every short note must pulse its speed');
});

test('airborne embers change course and speed in the wind', () => {
  const emitter = createFlowEmitter('a', 2.4, preset);
  const embers = emitter.seeds.filter(seed => seed.type === 0 && seed.life > 1.7);
  let drifting = 0, reversing = 0, changingSpeed = 0;
  for (const seed of embers) {
    const first = sampleFlowParticle(seed, emitter, .25);
    const late = sampleFlowParticle(seed, emitter, 1.5);
    if (Math.abs(late.x - first.x) > 25) drifting++;
    const sidewaysSpeeds = [.2, .4, .6, .8, 1, 1.2, 1.4, 1.6]
      .map(t => sampleFlowParticle(seed, emitter, t).vx);
    if (sidewaysSpeeds.some((speed, i) =>
      i > 0 && speed * sidewaysSpeeds[i - 1] < 0)) reversing++;
    const speeds = [.2, .5, .8, 1.1, 1.4]
      .map(t => -sampleFlowParticle(seed, emitter, t).vy);
    if (Math.max(...speeds) - Math.min(...speeds) > 30) changingSpeed++;
  }
  assert.ok(drifting > embers.length * .50);
  assert.ok(reversing > embers.length * .70);
  assert.ok(changingSpeed > embers.length * .35);
});

test('each launch cohort opens, gathers, then unfolds widely', () => {
  function spread(emitter, age) {
    const sparks = emitter.seeds.filter(seed =>
      seed.type === 0 && seed.birth < .12 && seed.life > age);
    assert.ok(sparks.length >= 5);
    const positions = sparks.map(seed => sampleFlowParticle(seed, emitter, age).x);
    const center = mean(positions);
    return Math.sqrt(mean(positions.map(x => (x - center) ** 2)));
  }
  for (const id of ['a', 'b', 'c', 'd']) {
    const emitter = createFlowEmitter(id, 2, preset);
    const firstOpening = spread(emitter, .36);
    const gathering = spread(emitter, .82);
    const unfolding = spread(emitter, 1.5);
    assert.ok(firstOpening > 9);
    assert.ok(gathering < firstOpening * .35);
    assert.ok(unfolding > firstOpening * 3);
  }
});

test('preset raises fine ember births by about forty percent', () => {
  assert.equal(preset.density.ember_attack_count, 71);
  assert.equal(preset.density.ember_per_second, 197);
  const actual = createFlowEmitter('density-check', 2, preset).seeds
    .filter(seed => seed.type === 0).length;
  const baseline = validateVisualPreset({
    ...preset, density: { ...preset.density,
      ember_attack_count: 51, ember_per_second: 141 },
  });
  const before = createFlowEmitter('density-check', 2, baseline).seeds
    .filter(seed => seed.type === 0).length;
  assert.ok(actual >= before * 1.38 && actual <= before * 1.42);
});

test('all particle paths move about half as fast while wind still changes course', () => {
  const normal = validateVisualPreset({
    ...preset, motion: { ...preset.motion, flight_speed_scale: 1 },
  });
  const slower = createFlowEmitter('speed-check', 2, preset);
  const prior = createFlowEmitter('speed-check', 2, normal);
  const ratios = slower.seeds.filter(seed => seed.type === 0 && seed.life > .8)
    .slice(0, 60).map(seed => {
      const index = slower.seeds.indexOf(seed);
      const a = sampleFlowParticle(seed, slower, .3);
      const b = sampleFlowParticle(prior.seeds[index], prior, .3);
      return Math.hypot(a.vx, a.vy) / Math.hypot(b.vx, b.vy);
    });
  assert.ok(mean(ratios) > .47 && mean(ratios) < .55);
});

test('larger two-axis gusts shorten the plume and sometimes roll sparks downward', () => {
  const heights = [], sideways = [];
  let reversed = 0;
  for (const id of ['a', 'b', 'c', 'd']) {
    const emitter = createFlowEmitter(id, 2.4, preset);
    for (const seed of emitter.seeds.filter(part => part.type === 0)) {
      let peak = 0, rising = false, pushedDown = false;
      for (let age = .1; age < seed.life; age += .1) {
        const point = sampleFlowParticle(seed, emitter, age);
        peak = Math.max(peak, -point.y);
        if (age > .3 && point.vy < -8) rising = true;
        if (age > .45 && point.vy > 8) pushedDown = true;
        assert.ok(point.y < 0, 'wind must not push embers through the keyboard');
      }
      heights.push(peak);
      if (rising && pushedDown) reversed++;
      const first = sampleFlowParticle(seed, emitter, .15);
      const later = sampleFlowParticle(seed, emitter, Math.min(1.5, seed.life * .8));
      sideways.push(Math.abs(later.x - first.x));
    }
  }
  assert.ok(mean(heights) > 65 && mean(heights) < 90);
  assert.ok(mean(sideways) > 20);
  assert.ok(reversed > 60);
});

test('short luminous filaments vary in length, width and path', () => {
  const trails = ['a', 'b', 'c'].flatMap(id => {
    const emitter = createFlowEmitter(id, 3, preset);
    return emitter.seeds.filter(seed => seed.type === 6)
      .map(seed => ({ seed, emitter }));
  });
  assert.ok(trails.length >= 10);
  assert.ok(Math.max(...trails.map(({ seed }) => seed.ribbonTail)) < .27);
  assert.ok(Math.max(...trails.map(({ seed }) => seed.ribbonTail)) -
            Math.min(...trails.map(({ seed }) => seed.ribbonTail)) > .08);
  assert.ok(Math.max(...trails.map(({ seed }) => seed.ribbonWidth)) -
            Math.min(...trails.map(({ seed }) => seed.ribbonWidth)) > .5);
  const turns = trails.map(({ seed, emitter }) => {
    const a = sampleFlowParticle(seed, emitter, .2);
    const b = sampleFlowParticle(seed, emitter, .7);
    return Math.abs(Math.atan2(a.vx, -a.vy) - Math.atan2(b.vx, -b.vy));
  });
  assert.ok(turns.some(turn => turn > .18));
});

test('a filament eases down to transparent during its final 0.62 seconds', () => {
  const life = 1.6;
  assert.equal(filamentExitFade(life, life - .62), 1);
  assert.ok(Math.abs(filamentExitFade(life, life - .31) - .5) < 1e-9);
  assert.ok(filamentExitFade(life, life - .10) < .08);
  assert.equal(filamentExitFade(life, life), 0);
});

test('editable preset changes motion and counts without changing the renderer', () => {
  const original = createFlowEmitter('preset-check', 1.5, preset);
  const slower = validateVisualPreset({
    ...preset, motion: { ...preset.motion,
      launch_speed_scale: preset.motion.launch_speed_scale * .8 },
  });
  const slowed = createFlowEmitter('preset-check', 1.5, slower);
  assert.ok(Math.abs(slowed.seeds[0].speed / original.seeds[0].speed - .8) < 1e-9);

  const sparse = validateVisualPreset({
    ...preset, density: { ...preset.density,
      ember_per_second: preset.density.ember_per_second * .5 },
  });
  const originalEmbers = original.seeds.filter(seed => seed.type === 0).length;
  const fewerEmbers = createFlowEmitter('preset-check', 1.5, sparse)
    .seeds.filter(seed => seed.type === 0).length;
  assert.ok(fewerEmbers < originalEmbers * .75);

  assert.throws(() => validateVisualPreset({
    ...preset, colors: { ...preset.colors, piano_low: 'bright yellow' },
  }), /colors.piano_low/);
});
