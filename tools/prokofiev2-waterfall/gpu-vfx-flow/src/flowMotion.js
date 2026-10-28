// A deterministic emitter: births continue for the entire held note. Sampling
// at absolute audio time gives the same result for video, stills, and seeks.
const STEP = 1 / 50;

function hash(text) {
  let value = 2166136261;
  for (let i = 0; i < text.length; i++) value = Math.imul(value ^ text.charCodeAt(i), 16777619);
  return value >>> 0;
}

function random(seed) {
  let value = seed >>> 0;
  return () => {
    value += 0x6D2B79F5;
    let t = value;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function corner(x, y) {
  let h = Math.imul(x, 374761393) + Math.imul(y, 668265263);
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}

function noise(x, y) {
  const ix = Math.floor(x), iy = Math.floor(y);
  let fx = x - ix, fy = y - iy;
  fx = fx * fx * (3 - 2 * fx);
  fy = fy * fy * (3 - 2 * fy);
  const a = corner(ix, iy), b = corner(ix + 1, iy);
  const c = corner(ix, iy + 1), d = corner(ix + 1, iy + 1);
  return (a + (b - a) * fx) * (1 - fy) + (c + (d - c) * fx) * fy;
}

function curl(x, y, t, phase) {
  const nx = x * .024 + t * .24 + phase;
  const ny = y * .024 - t * .16 + phase * .67;
  const e = .14;
  return [
    (noise(nx, ny + e) - noise(nx, ny - e)) / (2 * e),
    -(noise(nx + e, ny) - noise(nx - e, ny)) / (2 * e),
  ];
}

function nozzleBearing(emitter, birth) {
  // Every note starts on the steep part of its own sweep. Random phase only
  // shapes the smaller eddies, so short notes cannot land on a flat plateau.
  const motion = emitter.motion;
  const angle = emitter.bearingOffset +
                emitter.sweepSign * motion.launch_angle_sweep_radians *
                Math.sin(birth * motion.launch_angle_sweep_rate) +
                .026 * (Math.sin(birth * 7.7 + emitter.phase) - Math.sin(emitter.phase)) +
                .018 * Math.sin(birth * 1.1 + emitter.phase * .72);
  return Math.max(-.22, Math.min(.22, angle));
}

function nozzlePulse(emitter, birth) {
  const motion = emitter.motion;
  return Math.max(.60, Math.min(1.50,
    1 + motion.launch_speed_pulse *
        Math.sin(birth * motion.launch_speed_pulse_rate) +
        motion.launch_speed_pulse * .2105263158 *
        Math.sin(birth * 9.10 + emitter.phase * 2.08)));
}

export function plumeDisplacement(seed, emitter, age) {
  const strength = seed.type === 0 ? 1 : seed.type === 6 ? .75 :
                   seed.type === 1 ? .5 : 0;
  if (!strength || age <= 0) return 0;
  const motion = emitter.motion;
  const phaseAge = age * (motion.plume_breath_rate / 1.35) *
                   (1 + .055 * Math.sin(seed.plumePhase));
  const ease = x => { const u = Math.max(0, Math.min(1, x)); return u * u * (3 - 2 * u); };
  // Relative to one drifting centreline, the jet first opens a little,
  // narrows almost to a point, then slowly unfolds into the wider air.
  const early = motion.plume_early_spread_fraction;
  const gathered = motion.plume_gather_spread_fraction;
  let width;
  if (phaseAge < .36) width = early * ease(phaseAge / .36);
  else if (phaseAge < .82) width = early + (gathered - early) * ease((phaseAge - .36) / .46);
  else width = gathered + (1 - gathered) * ease((phaseAge - .82) / .93);
  return seed.plumeLane * strength * motion.plume_spread_pixels *
         motion.flight_speed_scale * width;
}

function plumeIndividuality(age) {
  const ease = x => { const u = Math.max(0, Math.min(1, x)); return u * u * (3 - 2 * u); };
  if (age < .36) return 1 - .72 * ease(age / .36);
  if (age < .82) return .28 - .22 * ease((age - .36) / .46);
  return .06 + .60 * ease((age - .82) / .93);
}

function traceRaw(seed, emitter, throughLife = seed.life) {
  const motion = emitter.motion;
  const dt = STEP * motion.flight_speed_scale;
  const steps = Math.ceil(throughLife / STEP);
  const path = new Float32Array((steps + 1) * 2);
  let x = seed.origin, y = -2, vx = seed.vx, vy = seed.vy;
  path[0] = x; path[1] = y;
  for (let i = 1; i <= steps; i++) {
    const elapsed = i * STEP;
    const t = i * dt;
    const absolute = seed.birth + elapsed;
    // The jet leaves in its birth-time direction. Airflow takes over with
    // altitude, so old particles keep changing course after a new gust starts.
    const altitude = Math.max(0, -y);
    const entrainment = 1 - Math.exp(-altitude / (76 * motion.flight_speed_scale));
    // Both components are coherent fields: nearby sparks share a gust, while
    // their different birth times and heights make the plume fold over itself.
    const windVelocity = motion.horizontal_wind_scale * (
                         145 * Math.sin(absolute * 1.13 + altitude * .0066 + emitter.phase) +
                         85 * Math.sin(absolute * 2.18 - altitude * .010 + emitter.phase * .61) +
                         35 * Math.sin(absolute * 3.41 + altitude * .012 + seed.groupPhase));
    const verticalGust = motion.vertical_wind_scale * (
                         155 * Math.sin(absolute * 1.16 - altitude * .013 + emitter.phase * 1.27) +
                         82 * Math.sin(absolute * 2.42 + altitude * .010 + seed.groupPhase * .73) +
                         65 * Math.sin(absolute * 3.67 - altitude * .017 + seed.groupPhase * .83));
    const [flowX, flowY] = curl(x, y, absolute, emitter.phase + seed.phase * .14);
    const targetX = windVelocity * entrainment + seed.groupOffset * 9;
    const ax = (targetX - vx) * (.48 + 1.58 * entrainment) * seed.steering +
               flowX * seed.turbulence * (.30 + entrainment) *
                 (motion.curl_multiplier ?? 1) +
               Math.sin(absolute * 3.31 + seed.phase) * seed.sway * entrainment;
    const speedPulse = 1 + motion.airborne_speed_pulse_scale * (
                       .26 * Math.sin(absolute * 3.12 + emitter.phase + altitude * .005) +
                       .14 * Math.sin(absolute * 5.7 + seed.groupPhase - altitude * .008));
    const targetY = -seed.speed * speedPulse +
                    verticalGust * entrainment * seed.windResponse +
                    seed.lift * Math.min(1, t * .8);
    const ay = (targetY - vy) * (1.52 + .25 * Math.sin(absolute * 2.2 + seed.phase)) +
               flowY * seed.turbulence * .48 * (motion.curl_multiplier ?? 1);
    // The air changes at its original pace; distance travelled per frame is
    // scaled, so the path slows without losing the occasional wind reversal.
    vx += ax * STEP;
    vy += ay * STEP;
    x += vx * dt;
    y += vy * dt;
    const serpentine = seed.type === 6 ?
      seed.ribbonAmplitude *
      (Math.sin(t * seed.ribbonFrequency + seed.phase) - Math.sin(seed.phase)) *
      Math.min(1, t * 3.2) : 0;
    path[2 * i] = x + serpentine;
    path[2 * i + 1] = y;
  }
  seed.rawPath = path;
}

function trace(seed, emitter) {
  const coherent = seed.type === 0 || seed.type === 1 || seed.type === 6;
  const leader = coherent ? emitter.cohortLeaders.get(seed.cohort) || seed : seed;
  if (coherent && !leader.rawPath) traceRaw(leader, emitter, emitter.maxLife);
  if (!seed.rawPath) traceRaw(seed, emitter);
  const steps = Math.ceil(seed.life / STEP);
  const path = new Float32Array((steps + 1) * 2);
  for (let i = 0; i <= steps; i++) {
    const age = i * STEP;
    const ownX = seed.rawPath[2 * i];
    const centreX = leader.rawPath[2 * i];
    path[2 * i] = coherent ? centreX + (ownX - centreX) *
      plumeIndividuality(age) +
      plumeDisplacement(seed, emitter, age) : ownX;
    path[2 * i + 1] = seed.rawPath[2 * i + 1];
  }
  seed.path = path;
}

export function createFlowEmitter(eventId, duration, preset) {
  if (!preset?.motion || !preset?.density)
    throw new Error('A visual preset with motion and density is required');
  const motion = preset.motion, density = preset.density;
  const rng = random(hash(eventId));
  const emitter = {
    motion,
    phase: rng() * Math.PI * 2,
    sweepSign: rng() < .5 ? -1 : 1,
    bearingOffset: (rng() - .5) * .07,
    seeds: [], maxLife: 3.8, cohortLeaders: new Map(),
  };
  const held = Math.max(.14, duration);
  const strength = .84 + rng() * .34;

  function makeSeed(type, birth) {
    const group = Math.floor(rng() * 3);
    const groupOffset = group - 1;
    const groupPhase = emitter.phase + group * 1.71;
    // A time-varying nozzle turns the nearly parallel plume as the key is held.
    const angle = Math.max(-.25, Math.min(.25,
      nozzleBearing(emitter, birth) + groupOffset * .025 +
      (rng() - .5) * motion.launch_angle_jitter_radians));
    const longFlight = type === 0 && rng() < .09;
    const baseSpeed = type === 0 ? (longFlight ? 205 : 128) + rng() * 87 :
                  type === 6 ? 165 + rng() * 67 :
                  type === 2 ? 45 + rng() * 40 : 140 + rng() * 80;
    const speed = baseSpeed * motion.launch_speed_scale *
                  nozzlePulse(emitter, birth) * (.82 + rng() * .31);
    const life = (type === 0 ? (longFlight ? 2.5 + rng() * 1.3 : .8 + rng() * 1.25) :
                 type === 2 ? .7 + rng() * .65 :
                 type === 4 ? .36 + rng() * .5 :
                 type === 6 ? 1.10 + rng() * .90 : .5 + rng() * .75) *
                 (preset.appearance?.particle_life_scale ?? 1);
    emitter.seeds.push({
      type, birth, life, speed, groupOffset, groupPhase,
      origin: (rng() - .5) * 18,
      plumeLane: (rng() < .5 ? -1 : 1) * (.25 + rng() * .75),
      cohort: Math.floor(birth / .14),
      plumePhase: emitter.phase + Math.floor(birth / .14) * .47,
      vx: Math.sin(angle) * speed,
      vy: -Math.cos(angle) * speed,
      steering: type === 6 ? 1.4 : 1.05 + rng() * .65,
      lift: type === 2 ? 5 : 10 + rng() * 14,
      windResponse: .76 + rng() * .46,
      turbulence: type === 6 ? 15 : 13 + rng() * 21,
      sway: type === 6 ? 66 : 7 + rng() * 11,
      size: .45 + rng() * 1.02,
      phase: rng() * Math.PI * 2,
      rotation: (rng() - .5) * .55,
      aspect: rng(),
      ribbonAmplitude: 7 + rng() * 16,
      ribbonFrequency: 4.2 + rng() * 4.0,
      ribbonTail: .10 + rng() * .16,
      ribbonWidth: .75 + rng() * 1.20,
      ribbonGlow: .70 + rng() * .65,
    });
  }

  // A modest attack accent, followed by independent continuous streams.
  for (let i = 0; i < density.ember_attack_count; i++) makeSeed(0, rng() * .12);
  for (let i = 0; i < density.streak_attack_count; i++) makeSeed(1, rng() * .11);
  for (let i = 0; i < density.filament_attack_count; i++) makeSeed(6, rng() * .13);
  // 0 embers; 1 streaks; 2 wisps; 3 flames; 4 light; 5 glints;
  // 6 sparse serpentine filaments.
  const rates = [density.ember_per_second, density.streak_per_second,
                 density.smoke_per_second, density.flame_per_second,
                 density.light_per_second, density.glint_per_second,
                 density.filament_per_second];
  for (let type = 0; type < rates.length; type++) {
    const count = Math.ceil(held * rates[type] * strength);
    for (let i = 0; i < count; i++) {
      const birth = (i + rng()) / (rates[type] * strength);
      if (birth <= held) makeSeed(type, birth);
    }
  }
  emitter.seeds.sort((a, b) => a.birth - b.birth);
  for (const seed of emitter.seeds)
    emitter.maxLife = Math.max(emitter.maxLife, seed.life);
  for (const seed of emitter.seeds) {
    if (seed.type === 0 && !emitter.cohortLeaders.has(seed.cohort))
      emitter.cohortLeaders.set(seed.cohort, seed);
  }
  return emitter;
}

export function firstLiveParticle(seeds, age, maxLife) {
  const threshold = age - maxLife;
  let lo = 0, hi = seeds.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (seeds[mid].birth < threshold) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

export function filamentExitFade(life, age) {
  const remaining = Math.max(0, Math.min(1, (life - age) / .62));
  return remaining * remaining * (3 - 2 * remaining);
}

export function sampleFlowParticle(seed, emitter, seconds) {
  if (seconds < 0 || seconds > seed.life) return null;
  if (!seed.path) trace(seed, emitter);
  const at = Math.min(seed.path.length / 2 - 2, seconds / STEP);
  const index = Math.floor(at), blend = at - index;
  const a = index * 2, b = a + 2;
  const x = seed.path[a] + (seed.path[b] - seed.path[a]) * blend;
  const y = seed.path[a + 1] + (seed.path[b + 1] - seed.path[a + 1]) * blend;
  return { x, y, vx: (seed.path[b] - seed.path[a]) / STEP,
           vy: (seed.path[b + 1] - seed.path[a + 1]) / STEP };
}
