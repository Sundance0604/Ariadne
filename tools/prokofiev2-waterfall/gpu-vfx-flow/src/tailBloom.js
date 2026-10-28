// A bounded, deterministic overlay for the final coda. It does not multiply
// every note's main emitter, so long-lived sparks remain affordable at 4K.
function hash(text) {
  let value = 2166136261;
  for (let i = 0; i < text.length; i++)
    value = Math.imul(value ^ text.charCodeAt(i), 16777619);
  return value >>> 0;
}

function random(seed) {
  let value = seed;
  return () => {
    value += 0x6D2B79F5;
    let t = value;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function bloomStrength(time, config) {
  if (!config) return 0;
  const raw = Math.max(0, Math.min(1,
    (time - config.start_seconds) /
    (config.full_seconds - config.start_seconds)));
  return raw * raw * (3 - 2 * raw);
}

export function buildTailParticles(notes, config) {
  if (!config) return [];
  const result = [];
  for (const note of notes) {
    if (note.family !== 'piano' || note.audio_start < config.start_seconds)
      continue;
    const strength = bloomStrength(note.audio_start, config);
    const rng = random(hash(note.event_id));
    const baseCount = 4 + 15 * strength +
      Math.min(1.5, note.audio_end - note.audio_start) * 3;
    const count = Math.round(baseCount *
      (1 + ((config.density_multiplier ?? 1) - 1) * strength));
    const groupPhase = rng() * Math.PI * 2;
    for (let i = 0; i < count; i++) {
      const birth = note.audio_start + rng() *
        Math.min(1.1, Math.max(.12, note.audio_end - note.audio_start));
      const power = bloomStrength(birth, config);
      const choice = rng();
      const weights = config.palette_weights ?? [.31, .28, .18, .13, .10];
      const cyanEnd = weights[0] + weights[1];
      const violetEnd = cyanEnd + weights[2];
      const redEnd = violetEnd + weights[3];
      const life = 2.3 + power * (4.8 + rng() * 1.8);
      const spread = 1 +
        ((config.horizontal_spread_multiplier ?? 1) - 1) * power;
      const loft = config.loft_multiplier ?
        (rng() < .30 ? 10 + rng() * 18 : rng() * 5) *
          config.loft_multiplier : 0;
      result.push({
        birth, pitch: note.midi_pitch,
        life,
        ribbonLife: Math.min(life,
          (config.ribbon_life_seconds ?? life) * (.82 + .36 * rng())),
        speed: (76 - 30 * power) * (.75 + rng() * .5),
        power, spread, loft, groupPhase, phase: rng() * Math.PI * 2,
        lane: rng() * 2 - 1, drift: (rng() * 2 - 1) * 6,
        size: .45 + rng() * 1.0,
        color: choice < weights[0] ? config.palette.ice :
          choice < cyanEnd ? config.palette.cyan :
          choice < violetEnd ? config.palette.violet :
          choice < redEnd ? config.palette.red : config.palette.gold,
        ribbon: rng() < (.015 + .045 * power),
      });
    }
  }
  return result.sort((a, b) => a.birth - b.birth);
}

export function sampleTailParticle(seed, age) {
  const t = Math.max(0, age);
  const power = seed.power;
  const lateralWind = power * (
    65 * (Math.sin(t * .74 + seed.groupPhase) - Math.sin(seed.groupPhase)) +
    27 * (Math.sin(t * 1.39 + seed.phase) - Math.sin(seed.phase)));
  const verticalWind = power * (
    43 * (Math.sin(t * .88 + seed.groupPhase * .81) -
          Math.sin(seed.groupPhase * .81)) +
    22 * (Math.sin(t * 1.66 + seed.phase) - Math.sin(seed.phase)));
  const spreading = t < 1 ? 18 * t :
    t < 2.5 ? 18 - 13 * (t - 1) / 1.5 :
    5 + (t - 2.5) * (8 + 4 * power);
  const twist = power * 19 *
    (Math.sin(t * 1.34 + seed.phase + t * t * .018) -
     Math.sin(seed.phase)) * Math.min(1, t / 1.2);
  return {
    x: (lateralWind + seed.drift * t +
        seed.lane * spreading * power + twist) * seed.spread,
    y: -seed.speed * t / (1 + .09 * t) + verticalWind -
       seed.loft * power * Math.pow(t, 1.2),
  };
}

export function tailParticleAlpha(seed, age) {
  const arrival = Math.min(1, age / .18);
  const release = Math.max(0, Math.min(1,
    (seed.life - age) / Math.min(1.8, seed.life * .34)));
  return arrival * arrival * (3 - 2 * arrival) *
    release * release * (3 - 2 * release);
}
