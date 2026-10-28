import { Application, Assets, Container, Filter, GlProgram, Graphics, NineSliceSprite,
         Particle, ParticleContainer, Rectangle, Sprite, Texture } from 'pixi.js';
import { AdvancedBloomFilter } from 'pixi-filters/advanced-bloom';
import { BevelFilter } from 'pixi-filters/bevel';
import { GlowFilter } from 'pixi-filters/glow';
import { createFlowEmitter, filamentExitFade, firstLiveParticle,
         sampleFlowParticle } from './flowMotion.js';
import { sampleFlameEnvelope } from './flameTiming.js';
import { bloomStrength, buildTailParticles, sampleTailParticle,
         tailParticleAlpha } from './tailBloom.js';
import { createFireExperiments } from './fireExperiments.js';
import { colorNumber } from './visualPreset.js';
import { sampleVisualPreset } from './visualTimeline.js';
import flameURL from '../assets/kenney/flame_06.png';
import starURL from '../assets/kenney/star_07.png';
import traceURL from '../assets/kenney/trace_06.png';
import lightURL from '../assets/kenney/light_01.png';
import blackKeyURL from '../assets/seemusic/BlackKeyUp.png';
import realFireAURL from '../assets/real-fire/flame-smooth-a.png';
import realFireBURL from '../assets/real-fire/flame-smooth-b.png';
import realFireCURL from '../assets/real-fire/flame-smooth-c.png';
import eclipsePhotoURL from '../assets/eclipse/nps-diamond-ring-2017.jpg';

const query = new URLSearchParams(location.search);
const width = Number(window.__WATERFALL_WIDTH__ || query.get('width') || 1280);
const height = Number(window.__WATERFALL_HEIGHT__ || query.get('height') || 720);
const preset = window.__WATERFALL_PRESET__;
if (!preset) throw new Error('A visual preset was not supplied');
const style = window.__WATERFALL_STYLE__;
if (!style) throw new Error('A visual style was not supplied');
const theme = {
  low: colorNumber(preset.colors.piano_low),
  high: colorNumber(preset.colors.piano_high),
  strike: colorNumber(preset.colors.strike),
  background: '#000000',
};
const timeline = window.__WATERFALL_TIMELINE__;
if (!timeline) throw new Error('Timeline was not supplied to the local renderer');
const visualSections = timeline.visual_sections || [];
const usePhotoEclipse = visualSections.some(section =>
  section.preset?.appearance?.eclipse_image === 'photo');
const notePaletteCuts = timeline.note_palette_cuts || [];
const intro = timeline.intro || null;
const outro = timeline.outro || null;
const eclipseFade = timeline.eclipse_fade || null;
const eclipseLaneCleanupStart = timeline.eclipse_lane_cleanup_start_seconds ?? null;
const tailBloom = timeline.tail_particle_bloom || null;
function visualAt(time) {
  return sampleVisualPreset(Math.max(0, time), visualSections, preset);
}
function appearanceOf(look) {
  return look.appearance || {
    material: 'glass', material_amount: 1, material_speed: 1,
    keyboard_tint: '#ffffff', horizon_tint: '#ffddc0', color_variation: .08,
    orchestra_base_alpha: .55, orchestra_lead_alpha: .55,
    orchestra_lead_start: 0, orchestra_lead_end: 0,
    orchestra_emitter_scale: 0, impact_scale: 1, particle_white_mix: .8,
    orchestra_neutral_color: '#aeb7c2', orchestra_lead_color: '#aeb7c2',
    particle_style: 'spark', particle_life_scale: 1,
    edge_strength: 1, glow_strength: 1,
  };
}
function orchestraFeatured(note, time, look = visualAt(time)) {
  const appearance = appearanceOf(look);
  if (note.visual_role === 'lead') return true;
  if (note.visual_role === 'support') return false;
  return note.family !== 'piano' &&
    time >= appearance.orchestra_lead_start &&
    time < appearance.orchestra_lead_end;
}
const materialModes = { glass: 0, crystal: 1, metal: 2, gilded: 3, fracture: 4, fire: 5 };
const blackKeyImage = new Image();
blackKeyImage.src = blackKeyURL;
await blackKeyImage.decode();
let eclipsePhotoImage = null;
if (usePhotoEclipse) {
  eclipsePhotoImage = new Image();
  eclipsePhotoImage.src = eclipsePhotoURL;
  await eclipsePhotoImage.decode();
}
const app = new Application();
await app.init({ width, height, preference: 'webgl', background: theme.background,
                 antialias: true, autoStart: false, preserveDrawingBuffer: true,
                 powerPreference: 'high-performance' });
document.body.appendChild(app.canvas);
app.canvas.id = 'waterfall-canvas';

const whiteClasses = new Set([0, 2, 4, 5, 7, 9, 11]);
const interval = timeline.render_interval;
const sampleStart = interval.start_seconds;
const minPitch = 21; // A0
const maxPitch = 108; // C8: the complete 88-key piano
const margin = 0;
const visualScale = width / 1280;
const keyHeight = Math.round(height * 0.19);
const strikeY = height - keyHeight;
const topY = 5;
const speed = (strikeY - topY) / interval.lookahead_seconds;
const whitePitches = [];
for (let p = minPitch; p <= maxPitch; p++) if (whiteClasses.has(p % 12)) whitePitches.push(p);
const whiteWidth = (width - 2 * margin) / whitePitches.length;
const keys = new Map();
let whiteIndex = 0;
for (let p = minPitch; p <= maxPitch; p++) {
  if (whiteClasses.has(p % 12)) {
    const x0 = margin + whiteIndex++ * whiteWidth;
    keys.set(p, { x0, x1: x0 + whiteWidth, black: false });
  } else {
    const center = margin + whiteIndex * whiteWidth;
    keys.set(p, { x0: center - whiteWidth * 0.29, x1: center + whiteWidth * 0.29, black: true });
  }
}

function colorParts(hex) { return [(hex >> 16) & 255, (hex >> 8) & 255, hex & 255]; }
function lerpColor(first, second, amount) {
  const a = colorParts(first), b = colorParts(second);
  return ((Math.round(a[0] + (b[0] - a[0]) * amount) << 16) |
          (Math.round(a[1] + (b[1] - a[1]) * amount) << 8) |
           Math.round(a[2] + (b[2] - a[2]) * amount));
}
// Saturation belongs in the emissive finish, not the score palette: a pale
// section colour can still produce the vivid, luminous edge seen in the refs.
function emissionColor(color) {
  const rgb = colorParts(color), hi = Math.max(...rgb), lo = Math.min(...rgb);
  if (hi - lo < 8) return color;
  const saturation = 1 - lo / hi;
  // Keep the emissive boost continuous as a section palette passes through
  // pale colours. The old .22 threshold made every falling note flash.
  const linear = Math.max(0, Math.min(1, (saturation - .10) / .28));
  const eased = linear * linear * (3 - 2 * linear);
  const targetSaturation = saturation +
    (Math.max(saturation, .60) - saturation) * eased;
  const top = Math.min(250, Math.max(235, hi * 1.06));
  const bottom = top * (1 - targetSaturation);
  const out = rgb.map(channel => Math.round(bottom +
    (channel - lo) / (hi - lo) * (top - bottom)));
  return (out[0] << 16) | (out[1] << 8) | out[2];
}
function colorFor(note, time = note.audio_start, look = visualAt(time)) {
  let base;
  const appearance = appearanceOf(look);
  if (note.family !== 'piano' && note.accent_color &&
      orchestraFeatured(note, time, look)) {
    base = colorNumber(note.accent_color);
  } else if (note.family !== 'piano' && appearance.orchestra_neutral_color) {
    base = colorNumber(orchestraFeatured(note, time, look) ?
      appearance.orchestra_lead_color : appearance.orchestra_neutral_color);
  } else if (note.family === 'strings') base = colorNumber(look.colors.strings);
  else if (note.family === 'woodwind') base = colorNumber(look.colors.woodwind);
  else if (note.family === 'brass') base = colorNumber(look.colors.brass);
  else {
    const blend = Math.max(0, Math.min(1, (note.midi_pitch - 48) / 37));
    let palette = look.colors;
    for (const cut of notePaletteCuts) {
      if (note.audio_start >= cut.before_start_seconds &&
          note.audio_start < cut.until_seconds) {
        // A hard musical cut is assigned in onset space. A note already
        // falling keeps its warm finish; a later note is cold from its first
        // visible frame, even if that frame precedes the audible attack.
        palette = note.audio_start < cut.at_seconds ? cut.before : cut.after;
      }
    }
    base = lerpColor(colorNumber(palette.piano_low),
                     colorNumber(palette.piano_high), blend);
    if (note.piano_unify_strength)
      base = lerpColor(base, colorNumber(note.piano_unify_color),
                       note.piano_unify_strength);
  }
  const variation = note.family !== 'piano' && !orchestraFeatured(note, time, look) ?
    appearance.color_variation * .2 : appearance.color_variation;
  const glimmer = .5 + .5 * Math.sin(time * .53 + note.midi_pitch * .36 +
    .7 * Math.sin(time * .19 + note.audio_start * 1.11));
  return lerpColor(base, 0xffffff, variation * glimmer);
}
function makeCanvas(w, h) {
  const canvas = document.createElement('canvas');
  canvas.width = w; canvas.height = h;
  return [canvas, canvas.getContext('2d')];
}
function trackedText(ctx, text, y, size, spacing, weight = 'normal') {
  ctx.font = `${weight} ${size}px Georgia, 'Times New Roman', serif`;
  const letters = [...text];
  const total = letters.reduce((sum, letter) => sum + ctx.measureText(letter).width, 0) +
                (letters.length - 1) * spacing;
  let x = 960 - total / 2;
  for (const letter of letters) {
    ctx.fillText(letter, x, y);
    x += ctx.measureText(letter).width + spacing;
  }
}
function titleTexture(card) {
  const [canvas, ctx] = makeCanvas(1920, 1080);
  ctx.textBaseline = 'middle';
  ctx.fillStyle = '#f7f4ee';
  trackedText(ctx, card.title, 312, 106, 15, 'bold');
  trackedText(ctx, card.subtitle, 410, 34, 8);
  trackedText(ctx, card.composer, 655, 61, 14, 'bold');
  ctx.strokeStyle = 'rgba(247,244,238,.72)';
  ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.moveTo(325, 655); ctx.lineTo(650, 655);
  ctx.moveTo(1270, 655); ctx.lineTo(1595, 655); ctx.stroke();
  ctx.fillStyle = 'rgba(247,244,238,.66)';
  trackedText(ctx, card.credit, 925, 25, 6);
  return Texture.from(canvas);
}
function easeBetween(time, from, to) {
  const x = Math.max(0, Math.min(1, (time - from) / (to - from)));
  return x * x * (3 - 2 * x);
}
const PIANO_CORNER_RADIUS = style.geometry.piano_corner_radius;
function noteTexture(lightOnly = false, radius = 11, cropped = false) {
  const [canvas, ctx] = makeCanvas(cropped ? 48 : 56, cropped ? 80 : 84);
  const x = cropped ? 0 : 4, y = cropped ? 0 : 2, w = 48, h = 80;
  const body = ctx.createLinearGradient(x, 0, x + w, 0);
  if (lightOnly) {
    body.addColorStop(0, 'rgba(255,255,255,.98)');
    body.addColorStop(.12, 'rgba(255,255,255,.04)');
    body.addColorStop(.88, 'rgba(255,255,255,.04)');
    body.addColorStop(1, 'rgba(255,255,255,.92)');
  } else {
    body.addColorStop(0, 'rgba(255,255,255,.82)');
    body.addColorStop(.1, 'rgba(255,255,255,.35)');
    body.addColorStop(.38, 'rgba(255,255,255,.28)');
    body.addColorStop(.62, 'rgba(255,255,255,.32)');
    body.addColorStop(.9, 'rgba(255,255,255,.39)');
    body.addColorStop(1, 'rgba(255,255,255,.82)');
  }
  ctx.beginPath(); ctx.roundRect(x, y, w, h, radius);
  ctx.fillStyle = body; ctx.fill();
  const rim = ctx.createLinearGradient(x, y, x + w, y + h);
  rim.addColorStop(0, 'rgba(255,255,255,1)');
  rim.addColorStop(.58, 'rgba(255,255,255,.93)');
  rim.addColorStop(1, 'rgba(255,255,255,.56)');
  ctx.strokeStyle = lightOnly && cropped ? rim :
    lightOnly ? 'rgba(255,255,255,1)' : 'rgba(255,255,255,.94)';
  ctx.lineWidth = lightOnly ? 3.0 : 1.5;
  ctx.stroke();
  if (lightOnly && cropped) {
    ctx.save(); ctx.clip();
    const topSheen = ctx.createLinearGradient(x + 4, y, x + 4, y + 13);
    topSheen.addColorStop(0, 'rgba(255,255,255,.94)');
    topSheen.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = topSheen; ctx.fillRect(x + 6, y + 1, w - 12, 12);
    ctx.restore();
  }
  if (!lightOnly) {
    ctx.save(); ctx.clip();
    ctx.fillStyle = 'rgba(255,255,255,.38)'; ctx.fillRect(x + 3, y + 3, 1, h - 6);
    ctx.fillStyle = 'rgba(255,255,255,.16)'; ctx.fillRect(x + w - 5, y + 3, 1, h - 6);
    ctx.fillStyle = 'rgba(255,255,255,.1)'; ctx.fillRect(x + w / 2, y + 5, 1, h - 10);
    ctx.fillStyle = 'rgba(255,255,255,.77)'; ctx.fillRect(x + 2, y + 2, w - 4, 1);
    ctx.fillStyle = 'rgba(255,255,255,.4)'; ctx.fillRect(x + 2, y + h - 3, w - 4, 1);
    ctx.restore();
  }
  return Texture.from(canvas);
}
// A softly bevelled colour body. The reference's depth comes from its
// perimeter and a restrained moving reflection, not photographed texture or
// polygonal facets across the whole face.
function pianoMetalTexture() {
  const [canvas, ctx] = makeCanvas(48, 80);
  const outer = ctx.createLinearGradient(0, 0, 48, 0);
  outer.addColorStop(0, 'rgba(255,255,255,1)');
  outer.addColorStop(.52, 'rgba(255,255,255,.91)');
  outer.addColorStop(1, 'rgba(255,255,255,.76)');
  ctx.beginPath(); ctx.roundRect(0, 0, 48, 80, PIANO_CORNER_RADIUS);
  ctx.fillStyle = outer; ctx.fill();
  ctx.save(); ctx.clip();
  const inset = ctx.createLinearGradient(3, 5, 45, 75);
  inset.addColorStop(0, 'rgb(205,215,217)');
  inset.addColorStop(.43, 'rgb(143,156,160)');
  inset.addColorStop(1, 'rgb(169,180,183)');
  ctx.beginPath(); ctx.roundRect(3.5, 4, 41, 72, PIANO_CORNER_RADIUS - 2.5);
  ctx.fillStyle = inset; ctx.fill();
  ctx.strokeStyle = 'rgba(45,61,67,.18)'; ctx.lineWidth = 1.2; ctx.stroke();
  const cap = ctx.createLinearGradient(0, 3, 0, 21);
  cap.addColorStop(0, 'rgba(255,255,255,.36)');
  cap.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = cap; ctx.fillRect(4, 4, 40, 17);
  ctx.restore();
  return Texture.from(canvas);
}
// A flat satin core keeps accompaniment legible without the muddy, semi-
// transparent horizontal gradient used before. Its light is almost entirely
// in the edge, leaving foreground piano reflections visually distinct.
function supportNoteTexture() {
  const [canvas, ctx] = makeCanvas(56, 84);
  ctx.beginPath(); ctx.roundRect(5, 2, 46, 80, 13);
  ctx.fillStyle = 'rgba(207,217,223,.83)'; ctx.fill();
  ctx.save(); ctx.clip();
  ctx.fillStyle = 'rgba(255,255,255,.24)'; ctx.fillRect(8, 10, 2, 64);
  ctx.fillStyle = 'rgba(33,47,56,.16)'; ctx.fillRect(48, 10, 2, 64);
  ctx.restore();
  ctx.strokeStyle = 'rgba(255,255,255,.43)'; ctx.lineWidth = 1; ctx.stroke();
  return Texture.from(canvas);
}
// The sustained brass melody has a bevelled pillar silhouette and a slim
// central vein, distinct from the rounded piano glass and muted support.
function leadNoteTexture() {
  const [canvas, ctx] = makeCanvas(56, 84);
  const body = ctx.createLinearGradient(4, 0, 52, 0);
  body.addColorStop(0, 'rgba(255,255,255,.94)');
  body.addColorStop(.12, 'rgba(255,255,255,.52)');
  body.addColorStop(.45, 'rgba(255,255,255,.60)');
  body.addColorStop(.72, 'rgba(255,255,255,.91)');
  body.addColorStop(1, 'rgba(255,255,255,.97)');
  ctx.beginPath();
  ctx.moveTo(10, 2); ctx.lineTo(46, 2); ctx.lineTo(52, 8);
  ctx.lineTo(52, 76); ctx.lineTo(46, 82); ctx.lineTo(10, 82);
  ctx.lineTo(4, 76); ctx.lineTo(4, 8); ctx.closePath();
  ctx.fillStyle = body; ctx.fill();
  ctx.strokeStyle = 'rgba(255,255,255,.85)'; ctx.lineWidth = 1.5; ctx.stroke();
  ctx.fillStyle = 'rgba(255,255,255,.47)'; ctx.fillRect(39, 8, 2, 68);
  ctx.fillStyle = 'rgba(255,255,255,.28)'; ctx.fillRect(14, 8, 1, 68);
  return Texture.from(canvas);
}
function innerGlazeTexture(radius = 11, cropped = false) {
  const [canvas, ctx] = makeCanvas(cropped ? 40 : 56, cropped ? 74 : 84);
  const x = cropped ? 0 : 8, y = cropped ? 0 : 5;
  const outer = ctx.createLinearGradient(x, 0, x + 40, 0);
  outer.addColorStop(0, 'rgba(255,255,255,0)');
  outer.addColorStop(.19, 'rgba(255,255,255,.17)');
  outer.addColorStop(.45, 'rgba(255,255,255,.055)');
  outer.addColorStop(.76, 'rgba(255,255,255,.22)');
  outer.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.beginPath(); ctx.roundRect(x, y, 40, 74, radius);
  ctx.fillStyle = outer; ctx.fill();
  const center = ctx.createLinearGradient(0, y + 1, 0, y + 73);
  center.addColorStop(0, 'rgba(255,255,255,.10)');
  center.addColorStop(.3, 'rgba(255,255,255,.015)');
  center.addColorStop(.72, 'rgba(255,255,255,.12)');
  center.addColorStop(1, 'rgba(255,255,255,.035)');
  ctx.beginPath(); ctx.roundRect(x + 7, y + 2, 23, 70, Math.min(radius, 9));
  ctx.fillStyle = center; ctx.fill();
  return Texture.from(canvas);
}
function auraTexture() {
  const [canvas, ctx] = makeCanvas(128, 176);
  // A signed-distance field makes the halo fall off by distance from *every*
  // edge, including the end caps. It avoids the horizontal smear of a stretched
  // blur texture and leaves the note's lit face sharp.
  const pixels = ctx.createImageData(128, 176);
  for (let y = 0; y < 176; y++) for (let x = 0; x < 128; x++) {
    const qx = Math.abs(x + .5 - 64) - 13;
    const qy = Math.abs(y + .5 - 88) - 35;
    const d = Math.hypot(Math.max(qx, 0), Math.max(qy, 0)) +
      Math.min(Math.max(qx, qy), 0) - 11;
    const outward = Math.max(0, d);
    const tight = .24 * Math.exp(-.5 * (outward / 10) ** 2);
    const wide = .12 * Math.exp(-.5 * (outward / 24) ** 2);
    const i = 4 * (y * 128 + x);
    pixels.data[i] = pixels.data[i + 1] = pixels.data[i + 2] = 255;
    pixels.data[i + 3] = Math.round(255 * (tight + wide));
  }
  ctx.putImageData(pixels, 0, 0);
  return Texture.from(canvas);
}
function materialTexture(radius = 12, cropped = false) {
  const [canvas, ctx] = makeCanvas(cropped ? 48 : 56, cropped ? 108 : 112);
  const x = cropped ? 0 : 4, y = cropped ? 0 : 2;
  const body = ctx.createLinearGradient(x, 0, x + 48, 0);
  body.addColorStop(0, 'rgba(255,255,255,.16)');
  body.addColorStop(.19, 'rgba(255,255,255,.84)');
  body.addColorStop(.5, 'rgba(255,255,255,.88)');
  body.addColorStop(.81, 'rgba(255,255,255,.84)');
  body.addColorStop(1, 'rgba(255,255,255,.16)');
  ctx.fillStyle = body;
  ctx.beginPath(); ctx.roundRect(x, y, 48, 108, radius); ctx.fill();
  return Texture.from(canvas);
}
function pianoMaterialTexture() {
  const [canvas, ctx] = makeCanvas(48, 108);
  ctx.beginPath(); ctx.roundRect(0, 0, 48, 108, PIANO_CORNER_RADIUS);
  ctx.fillStyle = 'rgba(255,255,255,.76)'; ctx.fill();
  return Texture.from(canvas);
}
function supportMaterialTexture() {
  const [canvas, ctx] = makeCanvas(48, 108);
  ctx.beginPath(); ctx.roundRect(0, 0, 48, 108, 13);
  ctx.fillStyle = 'rgba(255,255,255,.52)'; ctx.fill();
  return Texture.from(canvas);
}
function keyboardTexture(blackOnly = false) {
  const [canvas, ctx] = makeCanvas(width, height);
  const bottom = height - 17;
  if (!blackOnly) {
    ctx.fillStyle = '#050811';
    ctx.fillRect(0, strikeY - 5, width, keyHeight + 15);
    for (const [pitch, key] of keys) {
      if (key.black) continue;
      const inset = 1.35 * visualScale;
      const x = pitch === minPitch ? 0 : key.x0 + inset;
      const right = pitch === maxPitch ? width : key.x1 - inset;
      const w = right - x;
      const face = ctx.createLinearGradient(0, strikeY, 0, bottom);
      face.addColorStop(0, '#fbfdff'); face.addColorStop(1, '#b7c3d5');
      ctx.fillStyle = face;
      if (pitch === minPitch || pitch === maxPitch) {
        ctx.fillRect(x, strikeY + 7, w, bottom - strikeY - 7);
      } else {
        ctx.beginPath(); ctx.roundRect(x, strikeY + 7, w, bottom - strikeY - 7, 4.5); ctx.fill();
      }
      if (pitch !== maxPitch) {
        ctx.fillStyle = 'rgba(36,51,74,.65)';
        ctx.fillRect(x + w - 1, strikeY + 10, 1, bottom - strikeY - 13);
      }
    }
  }
  for (const key of keys.values()) {
    if (!key.black) continue;
    const x = key.x0, w = key.x1 - key.x0, h = (bottom - strikeY - 7) * .61;
    ctx.drawImage(blackKeyImage, x, strikeY + 7, w, h);
  }
  return Texture.from(canvas);
}
function horizonHazeTexture() {
  const [canvas, ctx] = makeCanvas(1024, 128);
  // A two-scale cloud field gives the low shelf a shifting, uneven edge.
  // The old blurred ellipses produced an almost uniform grey strip.
  function hash(x, y) {
    const n = Math.sin(x * 127.1 + y * 311.7) * 43758.5453;
    return n - Math.floor(n);
  }
  function noise(x, y) {
    const ix = Math.floor(x), iy = Math.floor(y);
    let fx = x - ix, fy = y - iy;
    fx = fx * fx * (3 - 2 * fx); fy = fy * fy * (3 - 2 * fy);
    const a = hash(ix, iy), b = hash(ix + 1, iy);
    const c = hash(ix, iy + 1), d = hash(ix + 1, iy + 1);
    return (a * (1 - fx) + b * fx) * (1 - fy) +
           (c * (1 - fx) + d * fx) * fy;
  }
  const pixels = ctx.createImageData(1024, 128);
  for (let y = 0; y < 128; y++) for (let x = 0; x < 1024; x++) {
    const drift = 16 * (noise(x / 133, 2.1) - .5);
    const large = noise(x / 87, (y + drift) / 34);
    const small = noise(x / 31 + 13.7, y / 19 + 5.2);
    const cloud = .68 * large + .32 * small;
    const lift = Math.exp(-Math.pow((127 - y) / 39, 2));
    const rim = Math.exp(-Math.pow((y - 116 - drift * .38) / 14, 2));
    const flecks = Math.pow(noise(x / 7.5 + 31, y / 8.5 + 19), 7);
    const alpha = Math.min(255, 255 * (
      .18 * lift * (.48 + .52 * cloud) +
      .17 * rim * (.40 + .60 * cloud) +
      .12 * rim * flecks));
    const i = 4 * (y * 1024 + x);
    pixels.data[i] = pixels.data[i + 1] = pixels.data[i + 2] = 255;
    pixels.data[i + 3] = alpha;
  }
  ctx.putImageData(pixels, 0, 0);
  // Uneven pin lights sit inside the smoke shelf, not on a repeating key grid.
  for (let i = 0; i < 85; i++) {
    const x = 12 + 1000 * hash(i + 17, 3);
    const y = 102 + 23 * hash(i + 9, 7);
    const radius = 2.5 + 5.5 * hash(i + 31, 11);
    const glimmer = .10 + .13 * hash(i + 53, 19);
    const halo = ctx.createRadialGradient(x, y, 0, x, y, radius);
    halo.addColorStop(0, `rgba(255,255,255,${glimmer})`);
    halo.addColorStop(.35, `rgba(255,255,255,${glimmer * .31})`);
    halo.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = halo;
    ctx.beginPath(); ctx.arc(x, y, radius, 0, Math.PI * 2); ctx.fill();
  }
  return Texture.from(canvas);
}
function smokePuffTexture() {
  const [canvas, ctx] = makeCanvas(256, 256);
  for (let i = 0; i < 9; i++) {
    const cx = 128 + 29 * Math.sin(i * 2.43);
    const cy = 128 + 16 * Math.cos(i * 4.17);
    const radius = 48 + (i % 4) * 12;
    const cloud = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius);
    cloud.addColorStop(0, 'rgba(255,255,255,.20)');
    cloud.addColorStop(.45, 'rgba(255,255,255,.11)');
    cloud.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = cloud;
    ctx.beginPath(); ctx.arc(cx, cy, radius, 0, Math.PI * 2); ctx.fill();
  }
  return Texture.from(canvas);
}
function emberTexture() {
  const [canvas, ctx] = makeCanvas(64, 64);
  const ember = ctx.createRadialGradient(32, 32, 0, 32, 32, 31);
  ember.addColorStop(0, 'rgba(255,255,255,1)');
  ember.addColorStop(.22, 'rgba(255,255,255,.96)');
  ember.addColorStop(.48, 'rgba(255,255,255,.42)');
  ember.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = ember; ctx.fillRect(0, 0, 64, 64);
  return Texture.from(canvas);
}
function strikeFlashTexture() {
  const [canvas, ctx] = makeCanvas(256, 64);
  ctx.save(); ctx.translate(128, 32); ctx.scale(1, .24);
  const halo = ctx.createRadialGradient(0, 0, 0, 0, 0, 124);
  halo.addColorStop(0, 'rgba(255,255,255,1)');
  halo.addColorStop(.12, 'rgba(255,255,255,.88)');
  halo.addColorStop(.38, 'rgba(255,255,255,.34)');
  halo.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = halo; ctx.fillRect(-128, -135, 256, 270);
  ctx.restore();
  const line = ctx.createLinearGradient(43, 0, 213, 0);
  line.addColorStop(0, 'rgba(255,255,255,0)');
  line.addColorStop(.5, 'rgba(255,255,255,.95)');
  line.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = line; ctx.fillRect(43, 29, 170, 5);
  return Texture.from(canvas);
}

// White-alpha eclipse artwork: section tint controls its colour without a
// separate bitmap for each palette. The offset glow and uneven rim make the
// backlight legible at video size while the moon remains dark.
function darkSunTexture() {
  const [canvas, ctx] = makeCanvas(1024, 1024);
  const cx = 512, cy = 512, radius = 156, brightAngle = -.57;
  const dx = Math.cos(brightAngle), dy = Math.sin(brightAngle);
  const outer = ctx.createRadialGradient(cx + 49 * dx, cy + 49 * dy, 112,
                                          cx + 49 * dx, cy + 49 * dy, 425);
  outer.addColorStop(0, 'rgba(255,255,255,.22)');
  outer.addColorStop(.25, 'rgba(255,255,255,.18)');
  outer.addColorStop(.55, 'rgba(255,255,255,.065)');
  outer.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = outer;
  ctx.fillRect(0, 0, 1024, 1024);
  const rim = ctx.createRadialGradient(cx, cy, radius - 20,
                                       cx, cy, radius + 47);
  rim.addColorStop(0, 'rgba(255,255,255,0)');
  rim.addColorStop(.31, 'rgba(255,255,255,.11)');
  rim.addColorStop(.47, 'rgba(255,255,255,.21)');
  rim.addColorStop(.65, 'rgba(255,255,255,.10)');
  rim.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = rim;
  ctx.fillRect(0, 0, 1024, 1024);
  // A continuous, irregular crescent with its strongest backlight above right.
  ctx.save();
  ctx.lineCap = 'round';
  ctx.shadowColor = 'rgba(255,255,255,.9)';
  ctx.shadowBlur = 26;
  for (let i = 0; i < 320; i++) {
    const a = -Math.PI + i * Math.PI * 2 / 320;
    const facing = Math.max(0, Math.cos(a - brightAngle));
    const lobe = Math.pow(facing, 5.5);
    const irregular = .90 + .08 * Math.sin(a * 11 + .5) +
                      .06 * Math.sin(a * 23 - .8);
    const strength = (.075 + .86 * lobe) * irregular;
    ctx.strokeStyle = `rgba(255,255,255,${strength})`;
    ctx.lineWidth = 3.7 + 8.0 * lobe;
    ctx.beginPath();
    ctx.arc(cx, cy, radius + 1.8 * Math.sin(a * 7),
            a, a + Math.PI * 2 / 320 * 1.15);
    ctx.stroke();
  }
  ctx.restore();
  // A soft leak and short, sparse rays break the flat circular silhouette.
  const leakX = cx + radius * dx, leakY = cy + radius * dy;
  const leak = ctx.createRadialGradient(leakX, leakY, 0, leakX, leakY, 113);
  leak.addColorStop(0, 'rgba(255,255,255,.67)');
  leak.addColorStop(.18, 'rgba(255,255,255,.31)');
  leak.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = leak;
  ctx.fillRect(leakX - 113, leakY - 113, 226, 226);
  ctx.save();
  ctx.translate(leakX, leakY);
  ctx.rotate(brightAngle);
  ctx.scale(1, .22);
  const flare = ctx.createRadialGradient(0, 0, 0, 0, 0, 182);
  flare.addColorStop(0, 'rgba(255,255,255,.83)');
  flare.addColorStop(.11, 'rgba(255,255,255,.47)');
  flare.addColorStop(.45, 'rgba(255,255,255,.095)');
  flare.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = flare;
  ctx.fillRect(-182, -182, 364, 364);
  ctx.restore();
  for (let i = 0; i < 17; i++) {
    const a = brightAngle + (i - 8) * .11;
    const reach = 39 + 79 * (.5 + .5 * Math.sin(i * 13.37));
    const start = radius + 7;
    const ray = ctx.createLinearGradient(
      cx + start * Math.cos(a), cy + start * Math.sin(a),
      cx + (start + reach) * Math.cos(a), cy + (start + reach) * Math.sin(a));
    ray.addColorStop(0, 'rgba(255,255,255,.16)');
    ray.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.strokeStyle = ray;
    ctx.lineWidth = 1.6 + (i % 3) * .7;
    ctx.beginPath();
    ctx.moveTo(cx + start * Math.cos(a), cy + start * Math.sin(a));
    ctx.lineTo(cx + (start + reach) * Math.cos(a),
               cy + (start + reach) * Math.sin(a));
    ctx.stroke();
  }
  // Recut the foreground disk after all light passes so no halo spills into it.
  ctx.globalCompositeOperation = 'destination-out';
  ctx.beginPath(); ctx.arc(cx, cy, radius - 9, 0, Math.PI * 2);
  ctx.fillStyle = '#000'; ctx.fill();
  ctx.globalCompositeOperation = 'source-over';
  return Texture.from(canvas);
}

function eclipseOcclusionTexture() {
  const [canvas, ctx] = makeCanvas(1024, 1024);
  const shade = ctx.createRadialGradient(512, 512, 153, 512, 512, 418);
  shade.addColorStop(0, 'rgba(0,0,0,1)');
  shade.addColorStop(.30, 'rgba(0,0,0,1)');
  shade.addColorStop(.75, 'rgba(0,0,0,.78)');
  shade.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = shade;
  ctx.fillRect(0, 0, 1024, 1024);
  return Texture.from(canvas);
}

function eclipsePhotoTexture(image) {
  const [canvas, ctx] = makeCanvas(1024, 1024);
  const side = Math.min(image.width, image.height) * .82;
  // Preserve the photograph's crisp one-sided backlight. Opacity and
  // musical fade are controlled separately by the cue sheet.
  ctx.drawImage(image, (image.width - side) / 2, (image.height - side) / 2,
                side, side, 0, 0, 1024, 1024);
  // Fade only the photograph's outer boundary, keeping the real corona and
  // its bright one-sided leak intact. This prevents a rectangular seam.
  const feather = ctx.createRadialGradient(512, 512, 332, 512, 512, 512);
  feather.addColorStop(0, 'rgba(255,255,255,1)');
  feather.addColorStop(.58, 'rgba(255,255,255,.92)');
  feather.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.globalCompositeOperation = 'destination-in';
  ctx.fillStyle = feather;
  ctx.fillRect(0, 0, 1024, 1024);
  ctx.globalCompositeOperation = 'source-over';
  return Texture.from(canvas);
}

function eclipseGoldTexture(image) {
  const [canvas, ctx] = makeCanvas(1024, 1024);
  const side = Math.min(image.width, image.height) * .82;
  ctx.drawImage(image, (image.width - side) / 2, (image.height - side) / 2,
                side, side, 0, 0, 1024, 1024);
  // Keep the photographic diamond-ring rays and add gold only around their
  // one-sided source, leaving the opposite corona deep red.
  const mask = ctx.createRadialGradient(685, 475, 22, 685, 475, 350);
  mask.addColorStop(0, 'rgba(255,255,255,1)');
  mask.addColorStop(.34, 'rgba(255,255,255,.92)');
  mask.addColorStop(.72, 'rgba(255,255,255,.32)');
  mask.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.globalCompositeOperation = 'destination-in';
  ctx.fillStyle = mask;
  ctx.fillRect(0, 0, 1024, 1024);
  ctx.globalCompositeOperation = 'source-over';
  return Texture.from(canvas);
}

const [backgroundCanvas, backgroundCtx] = makeCanvas(width, height);
backgroundCtx.fillStyle = '#000000'; backgroundCtx.fillRect(0, 0, width, strikeY);
for (const key of keys.values()) if (key.black) {
  backgroundCtx.fillStyle = 'rgba(255,255,255,.006)';
  backgroundCtx.fillRect(key.x0, 0, key.x1 - key.x0, strikeY);
}
app.stage.addChild(new Sprite(Texture.from(backgroundCanvas)));
// A dim, low-frequency atmosphere remains behind the notes. Its broad fields
// and restrained upper-right halo suggest depth without drawing a literal moon.
const [atmosphereCanvas, atmosphereCtx] = makeCanvas(1280, 720);
for (const [x, y, radius, opacity] of [
  [1010, 164, 450, .28], [224, 490, 570, .11], [766, 344, 690, .07],
]) {
  const gradient = atmosphereCtx.createRadialGradient(x, y, 0, x, y, radius);
  gradient.addColorStop(0, `rgba(255,255,255,${opacity})`);
  gradient.addColorStop(.42, `rgba(255,255,255,${opacity * .30})`);
  gradient.addColorStop(1, 'rgba(255,255,255,0)');
  atmosphereCtx.fillStyle = gradient;
  atmosphereCtx.fillRect(0, 0, 1280, 720);
}
const halo = atmosphereCtx.createRadialGradient(1035, 173, 47, 1035, 173, 91);
halo.addColorStop(0, 'rgba(255,255,255,0)');
halo.addColorStop(.45, 'rgba(255,255,255,.045)');
halo.addColorStop(1, 'rgba(255,255,255,0)');
atmosphereCtx.fillStyle = halo;
atmosphereCtx.fillRect(920, 58, 230, 230);
const atmosphere = new Sprite(Texture.from(atmosphereCanvas));
atmosphere.width = width; atmosphere.height = strikeY;
app.stage.addChild(atmosphere);
const darkSun = new Sprite(darkSunTexture());
darkSun.anchor.set(.5);
darkSun.width = width * .36;
darkSun.height = darkSun.width;
darkSun.x = width * .84;
darkSun.y = strikeY * .21;
darkSun.alpha = 0;
const eclipsePhoto = eclipsePhotoImage ?
  new Sprite(eclipsePhotoTexture(eclipsePhotoImage)) : null;
const eclipseGold = eclipsePhotoImage ?
  new Sprite(eclipseGoldTexture(eclipsePhotoImage)) : null;
if (eclipsePhoto) {
  eclipsePhoto.anchor.set(.5);
  eclipsePhoto.width = width * .32;
  eclipsePhoto.height = eclipsePhoto.width;
  eclipsePhoto.alpha = 0;
}
if (eclipseGold) {
  eclipseGold.anchor.set(.5);
  eclipseGold.width = width * .32;
  eclipseGold.height = eclipseGold.width;
  eclipseGold.tint = 0xffd17b;
  eclipseGold.alpha = 0;
}
const lanes = new Graphics();
const eclipseUpperLanes = new Graphics();
const eclipseLaneBottom = strikeY * .68;
for (const [pitch, key] of keys) {
  if (key.black || pitch % 12 !== 0) continue;
  if (eclipseLaneCleanupStart !== null && key.x0 >= width * .64) {
    eclipseUpperLanes.moveTo(key.x0, 0).lineTo(key.x0, eclipseLaneBottom)
      .stroke({ color: 0x9ca5ae, alpha: .08, width: 1 });
    lanes.moveTo(key.x0, eclipseLaneBottom).lineTo(key.x0, strikeY)
      .stroke({ color: 0x9ca5ae, alpha: .08, width: 1 });
  } else {
    lanes.moveTo(key.x0, 0).lineTo(key.x0, strikeY)
      .stroke({ color: 0x9ca5ae, alpha: .08, width: 1 });
  }
}
app.stage.addChild(lanes, eclipseUpperLanes);
// The black centre covers the faint lane guides before the corona is drawn.
// It only appears with the eclipse cue and has a soft edge.
const eclipseOcclusion = new Sprite(eclipseOcclusionTexture());
eclipseOcclusion.anchor.set(.5);
eclipseOcclusion.width = darkSun.width * 1.06;
eclipseOcclusion.height = eclipseOcclusion.width;
eclipseOcclusion.x = darkSun.x;
eclipseOcclusion.y = darkSun.y;
eclipseOcclusion.alpha = 0;
app.stage.addChild(eclipseOcclusion, darkSun);
if (eclipsePhoto) app.stage.addChild(eclipsePhoto);
if (eclipseGold) app.stage.addChild(eclipseGold);

// A quiet, wind-drifting smoke shelf exists even when no key is pressed.
const ambientLayer = new Container(); app.stage.addChild(ambientLayer);
const horizonHaze = new Sprite(horizonHazeTexture());
horizonHaze.blendMode = 'add';
horizonHaze.width = width + 120 * visualScale;
horizonHaze.height = 86 * visualScale;
horizonHaze.y = strikeY - horizonHaze.height;
ambientLayer.addChild(horizonHaze);
const ambientSmoke = [];

const rollMask = new Graphics().rect(0, topY, width, strikeY - topY).fill(0xffffff);
app.stage.addChild(rollMask);
const noteAura = new Container(); noteAura.mask = rollMask;
app.stage.addChild(noteAura);
const noteLights = new Container(); noteLights.mask = rollMask;
noteLights.filters = [new AdvancedBloomFilter({
  threshold: style.light.note_bloom_threshold,
  bloomScale: style.light.note_bloom_scale,
  brightness: style.light.note_bloom_brightness,
  blur: style.light.note_bloom_blur, quality: 3 })];
app.stage.addChild(noteLights);
const noteBodies = new Container(); noteBodies.mask = rollMask;
noteBodies.filterArea = new Rectangle(0, topY, width, strikeY - topY);
noteBodies.filters = [new BevelFilter({ rotation: 128, thickness: .75 * visualScale,
  lightAlpha: .22, shadowAlpha: .18, lightColor: 0xffffff,
  shadowColor: 0x121d27 })];
app.stage.addChild(noteBodies);
const pianoBodies = new Container(); pianoBodies.mask = rollMask;
pianoBodies.filterArea = new Rectangle(0, topY, width, strikeY - topY);
pianoBodies.filters = [new BevelFilter({ rotation: 126, thickness: 1.5 * visualScale,
  lightAlpha: style.surface.piano_bevel_light,
  shadowAlpha: style.surface.piano_bevel_shadow, lightColor: 0xffffff,
  shadowColor: 0x15212a })];
app.stage.addChild(pianoBodies);
const noteMaterialLayer = new Container(); noteMaterialLayer.mask = rollMask;
noteMaterialLayer.filterArea = new Rectangle(0, topY, width, strikeY - topY);
const materialFlow = new Filter({
  glProgram: GlProgram.from({
    vertex: `
      in vec2 aPosition;
      out vec2 vTextureCoord;
      uniform highp vec4 uInputSize;
      uniform vec4 uOutputFrame;
      uniform vec4 uOutputTexture;
      void main(void) {
        vec2 position = aPosition * uOutputFrame.zw + uOutputFrame.xy;
        position.x = position.x * (2.0 / uOutputTexture.x) - 1.0;
        position.y = position.y * (2.0 * uOutputTexture.z / uOutputTexture.y) - uOutputTexture.z;
        gl_Position = vec4(position, 0.0, 1.0);
        vTextureCoord = aPosition * (uOutputFrame.zw * uInputSize.zw);
      }
    `,
    fragment: `
      in vec2 vTextureCoord;
      out vec4 finalColor;
      uniform sampler2D uTexture;
      uniform highp vec4 uInputSize;
      uniform float uTime;
      uniform float uScale;
      uniform float uMaterialMode;
      uniform float uMaterialAmount;
      float hash21(vec2 p) {
        p = fract(p * vec2(123.34, 345.45));
        p += dot(p, p + 34.345);
        return fract(p.x * p.y);
      }
      float noise(vec2 p) {
        vec2 i = floor(p), f = fract(p);
        f = f * f * (3.0 - 2.0 * f);
        return mix(mix(hash21(i), hash21(i + vec2(1.0, 0.0)), f.x),
                   mix(hash21(i + vec2(0.0, 1.0)), hash21(i + 1.0), f.x), f.y);
      }
      void main(void) {
        vec4 ink = texture(uTexture, vTextureCoord);
        vec2 p = vTextureCoord * uInputSize.xy / uScale;
        float warp = noise(vec2(p.x * 0.019 + uTime * 0.11,
                                p.y * 0.015 - uTime * 0.16));
        vec2 cell = vec2(p.x * 0.056 + (warp - 0.5) * 0.68 + uTime * 0.10,
                         p.y * 0.038 - uTime * 0.34 +
                         0.28 * sin(p.x * 0.027 + uTime * 0.42));
        float patch = noise(cell);
        float secondary = noise(vec2(p.x * 0.067 - uTime * 0.17,
                                      p.y * 0.043 + uTime * 0.21));
        float gleam = noise(vec2(p.x * 0.038 + uTime * 0.38,
                                  p.y * 0.021 - uTime * 0.52));
        // Slow, broken crystalline planes and fine metallic grain sit beneath
        // the moving broad patches; neither should read as a hard pattern.
        vec2 facetCell = vec2(p.x * 0.092 + p.y * 0.016 + uTime * 0.028,
                              p.y * 0.032 - p.x * 0.013 - uTime * 0.052);
        vec2 facetId = floor(facetCell);
        vec2 facetUV = fract(facetCell);
        float facetSeed = noise(facetId * 1.37);
        float facetPlane = (facetUV.x + facetUV.y < 1.0 ? 0.18 : -0.12) *
                           (0.40 + 0.60 * facetSeed);
        float facetSeam = 1.0 - smoothstep(0.016, 0.095,
                                          abs(facetUV.x + facetUV.y - 1.0));
        float grain = noise(vec2(p.x * 0.31 + uTime * 0.023,
                                  p.y * 0.25 - uTime * 0.014));
        float illuminated = smoothstep(0.43, 0.70, patch * 0.76 + gleam * 0.24);
        float shade = 0.29 + 0.76 * illuminated + 0.17 * secondary +
                      0.12 * sin(uTime * 1.10 + patch * 8.0 + p.y * 0.014) +
                      0.11 * facetPlane + 0.055 * (grain - 0.5);
        float glint = 0.0;
        if (uMaterialMode < 0.5) {
          float refraction = noise(vec2(p.x * 0.028 + uTime * 0.19,
                                        p.y * 0.024 - uTime * 0.21));
          shade += uMaterialAmount * (0.21 * refraction - 0.07);
          glint = smoothstep(.80, .98, gleam) * .24;
        } else if (uMaterialMode < 1.5) {
          float caustic = noise(vec2(p.x * .086 - uTime * .22,
                                     p.y * .051 + uTime * .17));
          float facets = abs(facetPlane) * (.25 + .35 * facetSeed);
          shade += uMaterialAmount * (.42 * facets + .19 * caustic - .08);
          glint = facetSeam * facetSeed * .34 + smoothstep(.76, .97, caustic) * .22;
        } else if (uMaterialMode < 2.5) {
          // Only one or two broad caustic pools cross a note at a time.
          // Their phase changes slowly even for a note held at a fixed x/y.
          float caustic = noise(vec2(p.x * .041 + uTime * .071,
                                      p.y * .024 - uTime * .103));
          float soft = noise(vec2(p.x * .062 - uTime * .054,
                                  p.y * .034 + uTime * .079));
          float pool = smoothstep(.47, .76, .68 * caustic + .32 * soft);
          shade = .45 + uMaterialAmount * (.34 * pool + .045 * soft);
          glint = smoothstep(.68, .87, caustic) * .21;
        } else if (uMaterialMode < 3.5) {
          float vein = noise(vec2(p.x * .074 + p.y * .012 - uTime * .12,
                                  p.y * .071 + uTime * .10));
          shade += uMaterialAmount * (.29 * vein + .19 * illuminated - .11);
          glint = smoothstep(.77, .94, vein) * .29;
        } else if (uMaterialMode < 4.5) {
          float crack = 1.0 - smoothstep(.025, .14,
            min(abs(facetUV.x + facetUV.y - 1.0),
                min(abs(facetUV.x - .5), abs(facetUV.y - .5))));
          float flare = pow(max(0.0, sin(uTime * .91 + patch * 11.0)), 5.0);
          shade += uMaterialAmount * (.11 * grain + .29 * flare - .08);
          glint = crack * (.23 + .23 * flare);
        } else {
          // Broad coherent tongues drift upward through the note. Two noise
          // scales avoid the fixed fine stripes that looked like plastic.
          float drift = noise(vec2(p.x * .031 + uTime * .27,
                                   p.y * .019 - uTime * .64));
          float tongue = noise(vec2(p.x * .076 + 1.4 * drift,
                                    p.y * .030 - uTime * .91));
          float hot = smoothstep(.43, .79, .70 * tongue + .30 * drift);
          float dark = smoothstep(.53, .79, 1.0 - tongue);
          shade += uMaterialAmount * (.63 * hot - .16 * dark);
          glint = .20 * hot * (1.0 - .38 * dark);
        }
        vec3 luminous = ink.rgb * shade;
        if (uMaterialMode > 4.5) {
          luminous += ink.rgb * ink.a * glint * uMaterialAmount * 1.15;
          luminous += vec3(1.0, .49, .12) * ink.a * glint * .22;
        } else {
          luminous += vec3(1.0, 0.96, 0.91) * ink.a * illuminated * 0.15;
          luminous += vec3(0.94, 0.97, 1.0) * ink.a * glint *
                      uMaterialAmount * (uMaterialMode > 1.5 &&
                      uMaterialMode < 2.5 ? 1.32 : 1.0);
        }
        float surfaceAlpha = uMaterialMode > 1.5 && uMaterialMode < 2.5 ?
                             .74 + .24 * smoothstep(.18, .78, shade) :
                             .27 + .72 * illuminated;
        finalColor = vec4(luminous, ink.a * surfaceAlpha);
      }
    `,
  }),
  resources: { flowUniforms: { uTime: { value: 0, type: 'f32' },
                                uScale: { value: visualScale, type: 'f32' },
                                uMaterialMode: { value: 0, type: 'f32' },
                                uMaterialAmount: { value: 1, type: 'f32' } } },
});
noteMaterialLayer.filters = [materialFlow];
app.stage.addChild(noteMaterialLayer);
// Piano surface follows the musical cue. Earlier exports accidentally pinned
// this layer to metal, making every supposedly different finish look alike.
const pianoMaterialLayer = new Container(); pianoMaterialLayer.mask = rollMask;
pianoMaterialLayer.filterArea = new Rectangle(0, topY, width, strikeY - topY);
const pianoMetalFlow = new Filter({ glProgram: materialFlow.glProgram,
  resources: { flowUniforms: { uTime: { value: 0, type: 'f32' },
    uScale: { value: visualScale, type: 'f32' },
    uMaterialMode: { value: 2, type: 'f32' },
    uMaterialAmount: { value: 1.45, type: 'f32' } } } });
pianoMaterialLayer.filters = [pianoMetalFlow];
app.stage.addChild(pianoMaterialLayer);
// A sharp rim is composited after the opaque face; the matching blurred copy
// sits behind it, so bloom no longer softens or hides the note silhouette.
const noteRims = new Container(); noteRims.mask = rollMask;
app.stage.addChild(noteRims);
const specularLayer = new Container(); specularLayer.mask = rollMask;
app.stage.addChild(specularLayer);
const supportGlass = supportNoteTexture();
const leadGlass = leadNoteTexture(), lumens = noteTexture(true);
// Shared piano caps keep black- and white-key notes the same shape.
const pianoGlass = pianoMetalTexture(), pianoLumens = noteTexture(true, PIANO_CORNER_RADIUS, true);
const innerGlass = innerGlazeTexture(), pianoInnerGlass = innerGlazeTexture(PIANO_CORNER_RADIUS, true);
const auraGlass = auraTexture();
const mineral = materialTexture(), pianoMineral = pianoMaterialTexture();
const supportMineral = supportMaterialTexture();
const noteObjects = timeline.notes.filter(note => keys.has(note.midi_pitch)).map(note => {
  const key = keys.get(note.midi_pitch);
  const piano = note.family === 'piano';
  const finalFireNote = appearanceOf(visualAt(note.audio_start)).material === 'fire';
  const ordinaryWidth = (key.x1 - key.x0) * (piano ?
    (key.black ? style.geometry.piano_black_width : style.geometry.piano_white_width) :
    note.visual_role === 'lead' ?
      (finalFireNote ? style.geometry.orchestra_fire_lead_width :
        style.geometry.orchestra_lead_width) : style.geometry.orchestra_support_width);
  const unifiedWidth = whiteWidth * .68;
  const w = Math.max(8, piano && note.piano_unify_strength ?
    ordinaryWidth + (unifiedWidth - ordinaryWidth) * note.piano_unify_strength :
    ordinaryWidth);
  const x = (key.x0 + key.x1 - w) / 2;
  const pianoSlice = Math.min(PIANO_CORNER_RADIUS, (w - 2) / 2);
  const base = new NineSliceSprite({ texture: piano ? pianoGlass : supportGlass,
                                    leftWidth: piano ? pianoSlice : 11,
                                    rightWidth: piano ? pianoSlice : 11,
                                    topHeight: 13,
                                    bottomHeight: 13, width: w, height: 27 });
  base.tint = piano ? lerpColor(emissionColor(colorFor(note)), 0xffffff,
                                  style.surface.piano_face_white_mix) : colorFor(note);
  base.alpha = piano ? style.surface.piano_face_opacity : .42;
  base.visible = false; (piano ? pianoBodies : noteBodies).addChild(base);
  const inner = new NineSliceSprite({ texture: piano ? pianoInnerGlass : innerGlass,
                                     leftWidth: piano ? Math.min(PIANO_CORNER_RADIUS, (w - 5) / 2) : 12,
                                     rightWidth: piano ? Math.min(PIANO_CORNER_RADIUS, (w - 5) / 2) : 12,
                                     topHeight: 13,
                                     bottomHeight: 13, width: w - 4, height: 21 });
  inner.tint = lerpColor(colorFor(note), 0xffffff,
                          piano ? style.surface.piano_inset_white_mix : .49);
  inner.alpha = Math.min(1, (piano ? style.surface.piano_inset_strength : .12) *
                           preset.brightness.note_material);
  inner.visible = false; (piano ? pianoBodies : noteBodies).addChild(inner);
  const material = new NineSliceSprite({ texture: piano ? pianoMineral :
                                        note.visual_role === 'lead' ? mineral : supportMineral,
                                        leftWidth: piano ? pianoSlice : 11,
                                        rightWidth: piano ? pianoSlice : 11,
                                        topHeight: 13,
                                        bottomHeight: 13, width: w + 6, height: 25 });
  material.tint = piano ? emissionColor(colorFor(note)) : colorFor(note);
  material.alpha = Math.min(1, (piano ? style.surface.piano_material_long : .12) *
                               preset.brightness.note_material);
  material.visible = false;
  (piano ? pianoMaterialLayer : noteMaterialLayer).addChild(material);
  const light = new NineSliceSprite({ texture: piano ? pianoLumens : lumens,
                                     leftWidth: piano ? pianoSlice : 11,
                                     rightWidth: piano ? pianoSlice : 11,
                                     topHeight: 13,
                                     bottomHeight: 13, width: w, height: 25 });
  light.tint = piano ? lerpColor(emissionColor(colorFor(note)), 0xffffff, .30) : colorFor(note);
  light.alpha = Math.min(1, (piano ? style.light.piano_rim_base : .12) *
                            preset.brightness.note_glow);
  light.blendMode = 'add';
  light.visible = false; noteRims.addChild(light);
  const glow = new NineSliceSprite({ texture: piano ? pianoLumens : lumens,
                                    leftWidth: piano ? pianoSlice : 11,
                                    rightWidth: piano ? pianoSlice : 11,
                                    topHeight: 13,
                                    bottomHeight: 13, width: w, height: 25 });
  glow.tint = light.tint;
  glow.blendMode = 'add';
  glow.visible = false; noteLights.addChild(glow);
  const aura = new NineSliceSprite({ texture: auraGlass, leftWidth: 40, rightWidth: 40,
                                    topHeight: 42, bottomHeight: 42, width: w + 80, height: 109 });
  aura.tint = colorFor(note);
  aura.alpha = Math.min(1, (piano ? style.light.piano_halo_base : .10) *
                           preset.brightness.note_glow);
  aura.blendMode = 'add';
  aura.visible = false; noteAura.addChild(aura);
  return { note, x, base, inner, material, light, glow, aura };
});
const bevelGlints = new Graphics();
bevelGlints.blendMode = 'add';
noteRims.addChild(bevelGlints);
function drawBevelGlints(x, y, w, h, color, phase, pulse) {
  const r = Math.min(w * .23, h * .44, 10 * visualScale / 1.5);
  const x0 = x + r, x1 = x + w - r;
  const y0 = y + r, y1 = y + h - r;
  const topSpan = Math.max(0, x1 - x0), sideSpan = Math.max(0, y1 - y0);
  const lineWidth = Math.max(1, visualScale * .86);
  const sheen = lerpColor(color, 0xffffff, .62);
  const weight = offset => Math.max(0, Math.cos(phase - offset)) * pulse;
  const trace = (ax, ay, bx, by, energy) => {
    if (energy < .13) return;
    bevelGlints.moveTo(ax, ay).lineTo(bx, by).stroke({
      color: sheen, width: lineWidth, alpha: Math.min(.46, .42 * energy),
    });
  };
  if (topSpan > 3) {
    const span = topSpan * .58;
    const from = x0 + (.5 + .5 * Math.sin(phase * 1.31)) * (topSpan - span);
    trace(from, y + 1.4 * visualScale / 1.5,
          from + span, y + 1.4 * visualScale / 1.5, weight(0));
    trace(x0, y + h - 1.4 * visualScale / 1.5,
          x0 + topSpan * .45, y + h - 1.4 * visualScale / 1.5,
          weight(Math.PI));
  }
  if (sideSpan > 3) {
    const span = Math.min(sideSpan, Math.max(3, sideSpan * .36));
    const travel = (.5 + .5 * Math.sin(phase * .91)) * (sideSpan - span);
    trace(x + w - 1.4 * visualScale / 1.5, y0 + travel,
          x + w - 1.4 * visualScale / 1.5, y0 + travel + span,
          weight(Math.PI / 2));
    trace(x + 1.4 * visualScale / 1.5, y1 - travel - span,
          x + 1.4 * visualScale / 1.5, y1 - travel,
          weight(Math.PI * 1.5));
  }
}
const textures = await Promise.all([
  Promise.resolve(emberTexture()), Assets.load(traceURL), Promise.resolve(smokePuffTexture()),
  Assets.load(flameURL), Assets.load(lightURL), Assets.load(starURL),
]);
const needsFireFootage = [preset, ...visualSections.map(section => section.preset)].some(
  look => look.appearance?.fire_render_mode === 'footage' &&
          (look.appearance?.fire_mix ?? 1) > 0) ||
  timeline.notes.some(note => note.accent_fire);
const realFireAtlases = needsFireFootage ? await Promise.all([
  Assets.load(realFireAURL), Assets.load(realFireBURL), Assets.load(realFireCURL),
]) : [];
for (let i = 0; i < 42; i++) {
  const sprite = new Sprite(textures[2]);
  sprite.anchor.set(.5);
  sprite.blendMode = 'add';
  sprite.tint = lerpColor(theme.low, 0xffffff, .76);
  ambientLayer.addChild(sprite);
  ambientSmoke.push({
    sprite,
    origin: ((i * .61803398875) % 1) * (width + 180 * visualScale),
    y: 8 + ((i * .7548776662) % 1) * 35,
    speed: (i % 2 ? 1 : -1) * (5 + (i % 7) * 2.5),
    size: 36 + (i % 9) * 7,
    phase: i * 2.39996,
  });
}
for (const object of noteObjects) if (object.note.family === 'piano') {
  object.hotspots = [];
  for (let i = 0; i < 2; i++) {
    const sprite = new Sprite(textures[4]);
    sprite.anchor.set(.5); sprite.blendMode = 'add'; sprite.visible = false;
    sprite.tint = lerpColor(colorFor(object.note), 0xffffff, .48 + .16 * i);
    specularLayer.addChild(sprite); object.hotspots.push(sprite);
  }
}
const particleLayer = new Container();
const particlePools = [];
const particleContainers = [];
for (const [index, capacity] of [7000, 450, 620, 700, 620, 180, 520].entries()) {
  const container = new ParticleContainer({ dynamicProperties: {
    position: true, vertex: true, rotation: true, color: true,
  } });
  container.blendMode = index === 3 ? 'normal' : 'add';
  const pool = [];
  for (let i = 0; i < capacity; i++) {
    const particle = new Particle({ texture: textures[index === 6 ? 1 : index], x: -1000, y: -1000,
                                    alpha: 0, scaleX: .01, scaleY: .01 });
    container.addParticle(particle);
    pool.push(particle);
  }
  particleLayer.addChild(container);
  particleContainers.push(container);
  particlePools.push(pool);
}
const contactLayer = new Container(); app.stage.addChild(contactLayer);
const strikeFlash = strikeFlashTexture();
for (const object of noteObjects) if (object.note.family === 'piano') {
  const contact = new Sprite(textures[4]);
  contact.anchor.set(.5); contact.blendMode = 'add'; contact.visible = false;
  contact.tint = colorFor(object.note);
  contactLayer.addChild(contact); object.contact = contact;
  const flash = new Sprite(strikeFlash);
  flash.anchor.set(.5); flash.blendMode = 'add'; flash.visible = false;
  flash.tint = lerpColor(colorFor(object.note), 0xffffff, .80);
  contactLayer.addChild(flash); object.flash = flash;
}
particleLayer.filters = [new AdvancedBloomFilter({ threshold: .12, bloomScale: 1.66,
                                                   brightness: 1.45, blur: 6, quality: 2 })];
app.stage.addChild(particleLayer);
// Held-key fire is drawn from a time-varying turbulent field. The source is a
// white rectangle; no painted flame image or repeated flame animation is used.
const fireLayer = new Container(); app.stage.addChild(fireLayer);
const proceduralFireProgram = GlProgram.from({
  vertex: `
    in vec2 aPosition;
    out vec2 vTextureCoord;
    uniform highp vec4 uInputSize;
    uniform highp vec4 uOutputFrame;
    uniform vec4 uOutputTexture;
    void main(void) {
      vec2 position = aPosition * uOutputFrame.zw + uOutputFrame.xy;
      position.x = position.x * (2.0 / uOutputTexture.x) - 1.0;
      position.y = position.y * (2.0 * uOutputTexture.z / uOutputTexture.y) - uOutputTexture.z;
      gl_Position = vec4(position, 0.0, 1.0);
      vTextureCoord = aPosition * (uOutputFrame.zw * uInputSize.zw);
    }
  `,
  fragment: `
    in vec2 vTextureCoord;
    out vec4 finalColor;
    uniform highp vec4 uInputSize;
    uniform highp vec4 uOutputFrame;
    uniform float uTime;
    uniform float uSeed;
    uniform float uLead;
    uniform float uStrength;
    uniform float uGrowth;
    float hash21(vec2 p) {
      p = fract(p * vec2(123.34, 456.21));
      p += dot(p, p + 34.345);
      return fract(p.x * p.y);
    }
    float noise(vec2 p) {
      vec2 i = floor(p), f = fract(p);
      f = f * f * (3.0 - 2.0 * f);
      return mix(mix(hash21(i), hash21(i + vec2(1.0, 0.0)), f.x),
                 mix(hash21(i + vec2(0.0, 1.0)), hash21(i + 1.0), f.x), f.y);
    }
    float turbulence(vec2 p) {
      float sum = .50 * noise(p);
      sum += .27 * noise(p * 2.07 + 11.7);
      sum += .15 * noise(p * 4.17 - 4.3);
      sum += .08 * noise(p * 8.21 + 17.1);
      return sum;
    }
    void main(void) {
      vec2 uv = vTextureCoord * uInputSize.xy / uOutputFrame.zw;
      float rise = 1.0 - uv.y;
      float time = uTime + uSeed * 2.73;
      // The whole plume bends in a slow gust while smaller eddies continuously
      // advect its interior upward. Both are spatial fields, not rigid rotation.
      float wind = turbulence(vec2(rise * 2.5 - time * .21,
                                   uSeed * .81 + time * .17));
      float curl = turbulence(vec2(rise * 5.3 + time * .31,
                                   uSeed * 1.17 - time * .39));
      float bend = (wind - .5) * (.15 + .53 * rise) +
                   (curl - .5) * (.07 + .19 * rise);
      float x = uv.x - .5 - bend;
      vec2 advected = vec2(uv.x * 5.1 + (curl - .5) * .67 + uSeed * .13,
                           rise * 5.8 - time * 1.02);
      float flow = turbulence(advected);
      float detail = turbulence(vec2(uv.x * 11.9 - time * .42,
                                     rise * 12.5 - time * 1.62 + uSeed));
      float width = .40 * pow(max(0.0, 1.0 - rise), .83) + .018;
      float jagged = (flow - .5) * .18 + (detail - .5) * .055;
      float body = 1.0 - smoothstep(width * .56, width + jagged, abs(x));
      float split = (.045 + .105 * rise) *
                    sin(rise * 7.1 + time * .81 + uSeed);
      float strandWidth = .057 * (1.0 - rise) + .012;
      float strandA = 1.0 - smoothstep(strandWidth * .34, strandWidth,
                                       abs(x - .095 - split));
      float strandB = 1.0 - smoothstep(strandWidth * .34, strandWidth,
                                       abs(x + .105 + split));
      float tip = 1.0 - smoothstep(.62 + .35 * wind + .10 * flow,
                                  .95 + .15 * wind, rise);
      tip *= 1.0 - smoothstep(.77, .99, rise);
      float fringe = smoothstep(.19, .78, detail);
      float flame = body * (.42 + .65 * flow) +
                    (.64 * strandA + .56 * strandB) * (.38 + .62 * detail);
      flame *= tip * (.80 + .20 * fringe);
      float root = smoothstep(-.015, .085, rise);
      float pulse = .86 + .14 * turbulence(vec2(time * 2.1, rise * 2.7 + uSeed));
      // Reveal only the region the newborn flame has reached. The advancing
      // front climbs from the key line instead of exposing a full plume at once.
      float front = 1.0 - smoothstep(max(0.0, uGrowth - .12),
                                     max(.001, uGrowth), rise);
      float alpha = clamp(flame * root * pulse * front * uStrength, 0.0, .94);
      float core = max(strandA, strandB) * tip * (1.0 - .55 * rise);
      float heat = clamp(.36 + .77 * flow + .31 * detail + .31 * core - rise * .32,
                         0.0, 1.0);
      vec3 gold = mix(vec3(.60, .065, .015), vec3(1.0, .39, .045), heat);
      gold = mix(gold, vec3(1.0, .95, .53),
                 smoothstep(.69, 1.0, heat) * (1.0 - .56 * rise) * .84);
      vec3 crimson = mix(vec3(.39, .012, .040), vec3(1.0, .07, .13), heat);
      crimson = mix(crimson, vec3(1.0, .48, .31),
                    smoothstep(.73, 1.0, heat) * .48);
      vec3 color = mix(gold, crimson, uLead);
      finalColor = vec4(color * alpha, alpha);
    }
  `,
});
fireLayer.filters = [new AdvancedBloomFilter({ threshold: .34, bloomScale: .69,
                                               brightness: 1.07, blur: 3, quality: 2 })];
const fireTongues = [];
for (let pitch = minPitch; pitch <= maxPitch; pitch++) {
  const fireFilter = new Filter({ glProgram: proceduralFireProgram,
    resources: { fireUniforms: {
      uTime: { value: 0, type: 'f32' },
      uSeed: { value: pitch * .713, type: 'f32' },
      uLead: { value: 0, type: 'f32' },
      uStrength: { value: 1, type: 'f32' },
      uGrowth: { value: 0, type: 'f32' },
    } },
  });
  const sprite = new Sprite(Texture.WHITE);
  sprite.anchor.set(.5, 1); sprite.visible = false;
  sprite.filters = [fireFilter];
  fireLayer.addChild(sprite);
  fireTongues.push({ sprite, fireFilter });
}
const fireExperiments = createFireExperiments({ width, strikeY, scale: visualScale,
  smokeTexture: textures[2], lightTexture: textures[4], realFireAtlases });
app.stage.addChild(fireExperiments.layer);
const sparkFine = new Graphics(); app.stage.addChild(sparkFine);
const filamentGlow = new Graphics();
filamentGlow.filters = [new GlowFilter({ distance: 18, outerStrength: 2.8,
                                        quality: .25, color: 0xffffff })];
app.stage.addChild(filamentGlow);
const filamentCore = new Graphics(); app.stage.addChild(filamentCore);
const impact = new Graphics(); impact.filters = [new GlowFilter({ distance: 24, outerStrength: 2.2,
                                                                  quality: .25, color: 0xffffff })];
app.stage.addChild(impact);
const keyboard = new Sprite(keyboardTexture()); app.stage.addChild(keyboard);
const keySurface = new Graphics(); app.stage.addChild(keySurface);
const keyGlow = new Graphics(); keyGlow.filters = [new AdvancedBloomFilter({ threshold: .35,
                                        bloomScale: .8, blur: 5, quality: 2 })];
app.stage.addChild(keyGlow);
const pressedKeys = new Graphics(); app.stage.addChild(pressedKeys);
// White-key light is shaped around its neighbouring black keys. Redrawing the
// black caps above that light prevents bloom from recolouring an unpressed cap.
const blackCaps = new Sprite(keyboardTexture(true)); app.stage.addChild(blackCaps);
const blackKeyGlow = new Graphics();
blackKeyGlow.filters = [new AdvancedBloomFilter({ threshold: .35,
                              bloomScale: .8, blur: 5, quality: 2 })];
app.stage.addChild(blackKeyGlow);
const blackPressedKeys = new Graphics(); app.stage.addChild(blackPressedKeys);
const strikeGlow = new Graphics(); strikeGlow.filters = [new GlowFilter({ distance: 20,
                                        outerStrength: 2.4, quality: .2, color: 0xffffff })];
app.stage.addChild(strikeGlow);
const strikeCore = new Graphics(); app.stage.addChild(strikeCore);
const contactPoint = new Graphics();
contactPoint.filters = [new GlowFilter({ distance: 12, outerStrength: 2.1,
                                        quality: .2, color: 0xffffff })];
app.stage.addChild(contactPoint);

const flowEmitters = new Map();
for (const object of noteObjects) {
  const look = visualAt(object.note.audio_start);
  const featured = orchestraFeatured(object.note, object.note.audio_start, look);
  if (object.note.family !== 'piano' && !featured) continue;
  const scale = object.note.accent_emitter_scale ??
    (featured ? appearanceOf(look).orchestra_emitter_scale : 1);
  if (scale <= 0) continue;
  const emitterPreset = featured ? {
    ...look, density: Object.fromEntries(Object.entries(look.density).map(([key, value]) =>
      [key, key.endsWith('_count') ? Math.round(value * scale) : value * scale])),
  } : look;
  if (object.note.accent_particle_life_scale !== undefined)
    emitterPreset.appearance = {
      ...look.appearance,
      particle_life_scale: object.note.accent_particle_life_scale,
    };
  // Melodic orchestral notes can request distinct streams without invoking
  // the fire effect. The old low global orchestral scale hid their filaments.
  for (const [noteKey, densityKey] of [
    ['accent_filament_attack_count', 'filament_attack_count'],
    ['accent_filament_per_second', 'filament_per_second'],
    ['accent_light_per_second', 'light_per_second'],
  ]) if (object.note[noteKey] !== undefined)
    emitterPreset.density[densityKey] = object.note[noteKey];
  if (object.note.accent_fire) {
    emitterPreset.density.filament_attack_count =
      object.note.accent_filament_attack_count ?? 4;
    emitterPreset.density.filament_per_second =
      object.note.accent_filament_per_second ?? 7;
    emitterPreset.density.smoke_per_second =
      object.note.accent_smoke_per_second ?? 7;
    emitterPreset.density.light_per_second =
      object.note.accent_light_per_second ?? 5;
  }
  if (object.note.suppress_filament) emitterPreset.density = {
    ...emitterPreset.density,
    filament_attack_count: 0,
    filament_per_second: 0,
  };
  const emitter = createFlowEmitter(object.note.event_id,
    object.note.audio_end - object.note.audio_start, emitterPreset);
  if (tailBloom?.base_filament_life_multiplier &&
      object.note.audio_start >= tailBloom.start_seconds) {
    const strength = bloomStrength(object.note.audio_start, tailBloom);
    const lifeScale = 1 +
      (tailBloom.base_filament_life_multiplier - 1) * strength;
    for (const seed of emitter.seeds)
      if (seed.type === 6) seed.life *= lifeScale;
  }
  if (object.note.accent_fire) for (const seed of emitter.seeds) {
    if (seed.type === 0) seed.size *= 1.28;
    if (seed.type === 6) {
      seed.ribbonTail = Math.min(.55, seed.ribbonTail * 1.75);
      seed.ribbonWidth *= 1.22;
      seed.ribbonGlow *= 1.65;
    }
  }
  flowEmitters.set(object.note.event_id, emitter);
}
const localAccentFireWindows = noteObjects.filter(({ note }) => note.accent_fire)
  .map(({ note }) => [note.audio_start, note.audio_end + .30]);
const tailParticles = buildTailParticles(noteObjects.map(object => object.note),
  tailBloom).map(seed => ({ ...seed, tint: colorNumber(seed.color) }));

// Fade the existing stage layers individually. Reparenting masked note layers
// into a new container breaks their WebGL mask in some Pixi versions.
let titleCard;
let sceneLayers;
if (intro) {
  sceneLayers = app.stage.children.filter(child => child !== rollMask)
    .map(child => ({ child, alpha: child.alpha }));
  titleCard = new Sprite(titleTexture(intro));
  titleCard.width = width; titleCard.height = height;
  app.stage.addChild(titleCard);
}
const finalFade = new Graphics().rect(0, 0, width, height).fill({ color: 0x000000 });
finalFade.alpha = 0;
app.stage.addChild(finalFade);

function whiteKeyPath(graphics, pitch, y, bottom) {
  const key = keys.get(pitch);
  const leftBlack = keys.get(pitch - 1);
  const rightBlack = keys.get(pitch + 1);
  const left = pitch === minPitch ? 0 : key.x0 + 1.35 * visualScale;
  const right = pitch === maxPitch ? width : key.x1 - 1.35 * visualScale;
  const topLeft = leftBlack?.black ? Math.max(left, leftBlack.x1 + 1) : left;
  const topRight = rightBlack?.black ? Math.min(right, rightBlack.x0 - 1) : right;
  const shoulder = y + (height - 17 - strikeY - 7) * .61;
  return graphics.moveTo(topLeft, y).lineTo(topRight, y)
    .lineTo(topRight, shoulder).lineTo(right, shoulder)
    .lineTo(right, bottom).lineTo(left, bottom)
    .lineTo(left, shoulder).lineTo(topLeft, shoulder).closePath();
}

function renderAt(time, materialTime = time, presentationTime = time) {
  if (intro) {
    const sceneAlpha = easeBetween(presentationTime,
      intro.keyboard_fade_start_seconds, intro.keyboard_fade_end_seconds);
    for (const { child, alpha } of sceneLayers) child.alpha = alpha * sceneAlpha;
    titleCard.alpha = easeBetween(presentationTime, 0, intro.title_fade_in_seconds) *
      (1 - easeBetween(presentationTime,
        intro.title_fade_out_start_seconds, intro.title_fade_out_end_seconds));
  }
  const look = visualAt(time);
  const appearance = appearanceOf(look);
  const particleStyle = appearance.particle_style || 'spark';
  const fireMode = appearance.fire_render_mode || 'procedural';
  const fireMix = appearance.fire_mix ?? 1;
  const localAccentFire = localAccentFireWindows.some(([first, last]) =>
    first <= time && time <= last);
  fireLayer.visible = (particleStyle === 'fire' && fireMode === 'procedural' &&
                       fireMix > 0);
  const strikeColor = colorNumber(look.colors.strike);
  const saturatedEmbers = appearance.material === 'fracture' || particleStyle === 'fire';
  for (let index = 0; index < particleContainers.length; index++) {
    const mode = index === 3 || saturatedEmbers ? 'normal' : 'add';
    if (particleContainers[index].blendMode !== mode) particleContainers[index].blendMode = mode;
  }
  materialFlow.resources.flowUniforms.uniforms.uTime = materialTime * appearance.material_speed;
  materialFlow.resources.flowUniforms.uniforms.uMaterialMode = materialModes[appearance.material];
  materialFlow.resources.flowUniforms.uniforms.uMaterialAmount = appearance.material_amount;
  pianoMetalFlow.resources.flowUniforms.uniforms.uTime =
    materialTime * style.surface.piano_material_speed *
    (appearance.piano_material_speed ?? 1);
  pianoMetalFlow.resources.flowUniforms.uniforms.uMaterialMode =
    materialModes[appearance.piano_material || appearance.material] ?? 2;
  pianoMetalFlow.resources.flowUniforms.uniforms.uMaterialAmount =
    Math.min(2.5, (appearance.piano_material_amount ?? appearance.material_amount) *
      style.surface.piano_material_amount);
  keyboard.tint = colorNumber(appearance.keyboard_tint);
  atmosphere.tint = colorNumber(appearance.background_tint || '#677789');
  atmosphere.alpha = (appearance.background_atmosphere ?? .2) *
    (.92 + .08 * Math.sin(time * .11));
  const coronaOpacity = appearance.corona_opacity ??
                         appearance.background_motif_opacity ?? 0;
  const photoEclipse = appearance.eclipse_image === 'photo';
  // Musical cues can overlap. A photo tied to their interpolated target
  // opacity would jump when a new cue starts before the previous transition
  // finishes. Keep its own continuous envelope across those cue boundaries.
  const eclipseEnvelope = eclipseFade ?
    easeBetween(time, eclipseFade.fade_in_start_seconds,
                eclipseFade.fade_in_end_seconds) *
    (1 - easeBetween(time, eclipseFade.fade_out_start_seconds,
                        eclipseFade.fade_out_end_seconds)) : 0;
  const photoAlpha = eclipseFade ?
    eclipseFade.peak_alpha * eclipseEnvelope :
    Math.min(1, coronaOpacity * 1.32);
  if (eclipseLaneCleanupStart !== null)
    eclipseUpperLanes.alpha = 1 - easeBetween(time,
      eclipseLaneCleanupStart, eclipseLaneCleanupStart + 1.8);
  darkSun.tint = colorNumber(appearance.corona_tint ?? appearance.horizon_tint);
  darkSun.alpha = photoEclipse ? 0 : coronaOpacity *
    (.92 + .08 * Math.sin(time * .055));
  darkSun.x = width * .84 + width * .003 * Math.sin(time * .023);
  darkSun.y = strikeY * .21 + height * .002 * Math.sin(time * .031);
  if (eclipsePhoto) {
    eclipsePhoto.tint = colorNumber(appearance.corona_tint ?? '#ffffff');
    eclipsePhoto.alpha = photoEclipse ? photoAlpha : 0;
    eclipsePhoto.x = darkSun.x;
    eclipsePhoto.y = darkSun.y;
  }
  if (eclipseGold) {
    eclipseGold.alpha = photoEclipse ? photoAlpha *
      (appearance.eclipse_gold_mix ?? 0) : 0;
    eclipseGold.x = darkSun.x;
    eclipseGold.y = darkSun.y;
  }
  eclipseOcclusion.x = darkSun.x;
  eclipseOcclusion.y = darkSun.y;
  eclipseOcclusion.alpha = eclipseFade && photoEclipse ?
    eclipseFade.occlusion_alpha * eclipseEnvelope :
    Math.min(1, (appearance.background_motif_opacity ?? 0) * 4.2);
  horizonHaze.tint = colorNumber(appearance.horizon_tint);
  keySurface.clear();
  const finishColor = lerpColor(colorNumber(appearance.keyboard_tint), 0xffffff, .78);
  for (const [pitch, key] of keys) {
    if (key.black) continue;
    const x0 = key.x0 + 2 * visualScale;
    const x1 = key.x1 - 2 * visualScale;
    const y0 = strikeY + 12 * visualScale;
    const y1 = height - 20 * visualScale;
    // A shared slow light source drifts over neighbouring ivory keys; each
    // key has only a small phase offset, without independent fast flicker.
    const phase = time * appearance.material_speed * .105 + pitch * .19 +
                  .32 * Math.sin(time * .037 + pitch * .08);
    const shimmer = .50 + .50 * Math.sin(phase);
    const crystalAmount = appearance.keyboard_crystal_amount ?? 0;
    const metalAmount = appearance.keyboard_metal_amount ?? 0;
    const emberAmount = appearance.keyboard_ember_amount ?? 0;
    if (crystalAmount > .001 && (pitch * 7) % 11 < 5) {
      const lift = (pitch % 5) * 7 * visualScale;
      keySurface.moveTo(x0 + 2, y0 + 8 + lift).lineTo(x1 - 3, y0 + 27 + lift)
        .stroke({ color: finishColor, alpha: crystalAmount * .52 * shimmer,
                  width: 1.3 * visualScale });
      keySurface.moveTo(x0 + 4, y1 - 32 - lift).lineTo(x1 - 4, y1 - 13 - lift)
        .stroke({ color: finishColor, alpha: crystalAmount * .36 * shimmer,
                  width: .8 * visualScale });
    }
    if (metalAmount > .001) {
      const x = x0 + (x1 - x0) * (.31 + .28 * shimmer);
      keySurface.moveTo(x, y0).lineTo(x, y1)
        .stroke({ color: finishColor, alpha: metalAmount * (.42 + .42 * shimmer),
                  width: 1.15 * visualScale });
    }
    if (emberAmount > .001 && (pitch * 5) % 9 < 4) {
      const sway = 2.0 * Math.sin(time * .20 + pitch * .53) * visualScale;
      keySurface.moveTo(x0 + 4 + sway, y1 - 24 * visualScale)
        .bezierCurveTo(x0 + 3 - sway, y1 - 49 * visualScale,
                       x1 - 4 + sway, y1 - 68 * visualScale,
                       x1 - 5 - sway, y1 - 97 * visualScale)
        .stroke({ color: finishColor, alpha: emberAmount * (.36 + .25 * shimmer),
                  width: 1.0 * visualScale });
    }
  }
  horizonHaze.x = (-60 + 38 * Math.sin(time * .17)) * visualScale;
  horizonHaze.alpha = Math.min(1, (.88 + .10 * Math.sin(time * .47)) *
                        style.light.horizon_strength * (appearance.horizon_strength ?? 1));
  for (const fog of ambientSmoke) {
    const span = width + 180 * visualScale;
    fog.sprite.x = ((fog.origin + fog.speed * time * visualScale + span) % span) -
                   90 * visualScale + 7 * visualScale * Math.sin(time * .31 + fog.phase);
    fog.sprite.y = strikeY - (fog.y + 3 * Math.sin(time * .23 + fog.phase)) * visualScale;
    fog.sprite.width = fog.size * visualScale;
    fog.sprite.height = (17 + fog.size * .18) * visualScale;
    fog.sprite.alpha = .060 + .052 * (.5 + .5 * Math.sin(time * .67 + fog.phase));
    fog.sprite.tint = lerpColor(colorNumber(appearance.horizon_tint), 0xffffff, .52);
  }
  const active = new Map();
  const activeLead = new Map();
  const recentFirePiano = new Map();
  const recentFireLead = new Map();
  impact.clear(); keyGlow.clear(); pressedKeys.clear(); blackKeyGlow.clear();
  bevelGlints.clear();
  blackPressedKeys.clear(); strikeGlow.clear(); strikeCore.clear(); contactPoint.clear();
  sparkFine.clear(); filamentGlow.clear(); filamentCore.clear();
  const usedParticles = particlePools.map(() => 0);
  function emitParticle(type, x, y, sizeX, sizeY, rotation, color, alpha) {
    const index = usedParticles[type]++;
    const particle = particlePools[type][index];
    if (!particle) return;
    particle.x = x; particle.y = y;
    const textureSize = type === 0 ? 64 : type === 2 ? 256 : 512;
    const sizeScale = type === 6 ? look.size.filament : look.size.ember;
    const brightness = type === 6 ? look.brightness.filament : look.brightness.ember;
    particle.scaleX = sizeX * sizeScale / textureSize;
    particle.scaleY = sizeY * sizeScale / textureSize;
    particle.rotation = rotation; particle.tint = color;
    const oldFlameSuppression = particleStyle === 'fire' &&
      fireMode !== 'procedural' && (type === 3 || type === 4) ? .12 : 1;
    particle.alpha = Math.min(1, alpha * brightness * oldFlameSuppression);
  }
  for (const object of noteObjects) {
    const { note, base, inner, material, light, glow, aura, x } = object;
    const bottom = strikeY - (note.audio_start - time) * speed;
    const top = bottom - (note.audio_end - note.audio_start) * speed;
    const visible = top < strikeY && bottom > topY && note.audio_end >= time;
    base.visible = inner.visible = light.visible = glow.visible = aura.visible = material.visible = visible;
    if (visible) {
      const h = Math.max(15, bottom - top);
      const featured = orchestraFeatured(note, time, look);
      const color = colorFor(note, time, look);
      const luminousColor = note.family === 'piano' ? emissionColor(color) : color;
      if (note.family !== 'piano') {
      const targetTexture = featured ? leadGlass : supportGlass;
        if (base.texture !== targetTexture) base.texture = targetTexture;
      }
      base.tint = note.family === 'piano' ? lerpColor(luminousColor, 0xffffff,
        style.surface.piano_face_white_mix) : color;
      material.tint = aura.tint = luminousColor;
      light.tint = lerpColor(luminousColor, 0xffffff,
        note.family === 'piano' ? .30 : .12);
      glow.tint = luminousColor;
      inner.tint = lerpColor(color, 0xffffff,
        note.family === 'piano' ? style.surface.piano_inset_white_mix :
        appearance.material === 'fire' && featured ? .63 : .49);
      base.alpha = note.family === 'piano' ?
        Math.min(1, style.surface.piano_face_opacity *
          (appearance.edge_strength ?? 1)) :
        featured ? note.accent_tutti ? 1 : appearance.orchestra_lead_alpha :
          Math.min(1, appearance.orchestra_base_alpha * 1.4);
      inner.alpha = Math.min(1, (note.family === 'piano' ?
        style.surface.piano_inset_strength :
        featured ? appearance.material === 'fire' ? .52 : .31 : 0) *
        look.brightness.note_material);
      const edgePhase = materialTime * .52 + note.midi_pitch * .41 +
        note.audio_start * .17;
      const edgePulse = .26 + .74 * (.5 + .5 *
        Math.sin(materialTime * .31 + note.audio_start * 1.13 + note.midi_pitch * .23));
      light.alpha = Math.min(1, (note.family === 'piano' ?
        style.light.piano_rim_base + style.light.piano_rim_pulse * edgePulse :
        featured ? appearance.material === 'fire' ? .59 : .42 : 0) *
        look.brightness.note_glow *
        (appearance.glow_strength ?? 1) * (note.accent_tutti ? 1.4 : 1));
      glow.alpha = note.family === 'piano' ? Math.min(1,
        style.light.piano_glow * look.brightness.note_glow *
        (appearance.glow_strength ?? 1)) :
        light.alpha;
      base.x = light.x = glow.x = x; aura.x = x - 40;
      base.y = light.y = glow.y = top; aura.y = top - 42;
      base.height = light.height = glow.height = h; aura.height = h + 84;
      inner.x = x + 2; inner.y = top + 2;
      inner.width = Math.max(6, base.width - 4); inner.height = Math.max(8, h - 4);
      material.x = featured && note.family !== 'piano' ? x - 3 : x + 1;
      material.y = featured && note.family !== 'piano' ? top - 2 : top + 1;
      material.width = featured && note.family !== 'piano' ?
        Math.max(12, base.width + 6) : Math.max(8, base.width - 2);
      material.height = featured && note.family !== 'piano' ?
        h + 4 : Math.max(13, h - 2);
      material.alpha = Math.min(1,
        (note.family !== 'piano' ? featured ?
         appearance.material === 'fire' ? .48 : .33 : .14 :
         h > 38 ? style.surface.piano_material_long :
           style.surface.piano_material_short) *
        look.brightness.note_material *
        (note.family === 'piano' ? (appearance.piano_material_opacity ?? 1) :
         note.accent_tutti ? 1.25 : 1));
      if (note.family !== 'piano' && !featured) {
        inner.visible = false;
        light.visible = false;
        glow.visible = false;
        material.visible = false;
      }
      aura.alpha = Math.min(1,
        (note.family !== 'piano' ? featured ?
         appearance.material === 'fire' ? .31 : .18 : 0 :
         style.light.piano_halo_base + style.light.piano_halo_pulse *
           Math.sin(materialTime * .37 + note.midi_pitch * .39)) *
        look.brightness.note_glow * (appearance.glow_strength ?? 1) *
        (note.accent_tutti ? 1.4 : 1));
      if (note.family !== 'piano' && !featured) aura.visible = false;
      if (note.family === 'piano')
        drawBevelGlints(x, top, base.width, h, luminousColor,
                        edgePhase, edgePulse);
      if (object.hotspots) for (let i = 0; i < object.hotspots.length; i++) {
        const spot = object.hotspots[i];
        spot.tint = lerpColor(color, 0xffffff, .48 + .16 * i);
        const phase = note.audio_start * 4.17 + note.midi_pitch * .87 + i * 2.71;
        const wave = Math.sin(materialTime * (.86 + i * .31) + phase);
        spot.visible = true;
        spot.x = x + base.width * (.48 + .13 * Math.sin(materialTime * .43 + phase));
        spot.y = top + h * (.20 + .59 * (.5 + .5 * wave));
        spot.width = base.width * (1.55 + .25 * wave);
        spot.height = Math.min(h * .67, (68 + i * 20) * visualScale);
        spot.alpha = Math.min(1, (i === 0 ? .14 : .08) *
          (.64 + .36 * Math.sin(materialTime * 1.18 + phase) ** 2) *
          look.brightness.note_glow);
      }
    }
    if (!visible && object.hotspots) for (const spot of object.hotspots) spot.visible = false;
    if (note.family === 'piano' && note.audio_start <= time && note.audio_end > time)
      active.set(note.midi_pitch, note);
    if (note.family !== 'piano' && orchestraFeatured(note, time, look) &&
        note.audio_start <= time && note.audio_end > time)
      activeLead.set(note.midi_pitch, note);
    const age = time - note.audio_start;
    const duration = note.audio_end - note.audio_start;
    if ((particleStyle === 'fire' || note.accent_fire) &&
        age >= 0 && age < duration + .26 &&
        (note.family === 'piano' || orchestraFeatured(note, time, look))) {
      const candidates = note.family === 'piano' ? recentFirePiano : recentFireLead;
      const previous = candidates.get(note.midi_pitch);
      const held = note.audio_end > time;
      const previousHeld = previous?.audio_end > time;
      if (!previous || (held && !previousHeld) ||
          (held === previousHeld && note.audio_start > previous.audio_start))
        candidates.set(note.midi_pitch, note);
    }
    const emitter = flowEmitters.get(note.event_id);
    if (note.family === 'piano') {
      object.contact.visible = age >= 0 && age < duration + .26;
      object.flash.visible = object.contact.visible;
    }
    if (!emitter) continue;
    if (age < 0 || age >= duration + emitter.maxLife) continue;
    const key = keys.get(note.midi_pitch);
    const center = (key.x0 + key.x1) / 2;
    const color = colorFor(note, time, look);
    const localFire = note.accent_fire === true;
    if (note.family === 'piano' && object.contact.visible) {
      object.contact.tint = color;
      object.flash.tint = lerpColor(color, 0xffffff, .80);
      object.contact.x = center;
      object.contact.y = strikeY - 8 * visualScale;
      object.contact.width = (92 + 7 * Math.sin(time * .73 + center)) * visualScale;
      object.contact.height = 61 * visualScale;
      const release = age > duration ? Math.max(0, 1 - (age - duration) / .26) : 1;
      object.contact.alpha = (.18 + .36 * Math.exp(-age * 8)) * release;
      object.flash.x = center;
      object.flash.y = strikeY - 5 * visualScale;
      object.flash.width = Math.max(64 * visualScale, (key.x1 - key.x0) * 3.5);
      object.flash.height = 42 * visualScale;
      object.flash.alpha = Math.min(1,
        (.30 + .57 * Math.exp(-age * 11) + .04 * Math.sin(time * 6.1 + center)) *
        release * look.brightness.strike_flash * appearance.impact_scale);
    }
    const contact = Math.pow(Math.max(0, 1 - age / .48), 2);
    if (contact > 0) {
      impact.ellipse(center, strikeY - age * 6, (4 + age * 39) * visualScale,
                     (2 + age * 12) * visualScale)
        .stroke({ color, alpha: Math.min(1, .21 * contact * appearance.impact_scale),
                  width: 1.1 * visualScale });
      impact.circle(center, strikeY, (2 + age * 5) * visualScale)
        .fill({ color: 0xffffff, alpha: .28 * contact });
    }
    for (let i = firstLiveParticle(emitter.seeds, age, emitter.maxLife);
         i < emitter.seeds.length; i++) {
      const seed = emitter.seeds[i];
      if (seed.birth > age) break;
      const t = age - seed.birth;
      const motion = sampleFlowParticle(seed, emitter, t);
      if (!motion) continue;
      const progress = t / seed.life;
      const trailFade = seed.type === 6 ? filamentExitFade(seed.life, t) : 1;
      const envelope = Math.min(1, t * 7) * Math.pow(1 - progress,
        seed.type === 2 || seed.type === 4 ? 1.05 :
        seed.type === 0 ? .58 : seed.type === 6 ? .28 : 1.35) *
        (seed.type === 6 ? trailFade : 1);
      const pulse = .72 + .28 * Math.sin(seed.phase + t * 2.4);
      const x = center + motion.x * visualScale;
      const y = strikeY + motion.y * visualScale;
      const bright = lerpColor(color, 0xffffff,
        seed.type === 2 ? Math.min(.77, appearance.particle_white_mix + .15) :
        appearance.particle_white_mix);
      const tangent = Math.atan2(motion.vx, -motion.vy);
      if (seed.type === 0) {
        const size = (1 - .23 * progress) * seed.size;
        const thin = seed.aspect > .22;
        const fire = particleStyle === 'fire' || localFire;
        emitParticle(0, x, y, (thin ? 2.55 : 3.6) * size * visualScale * (fire ? .85 : 1),
                     (thin ? 6.6 : 4.0) * size * visualScale * (fire ? 1.3 : 1),
                     tangent + seed.rotation,
                     fire ? lerpColor(color, 0xff7b25, .39) : bright,
                     (.81 + .19 * seed.size) * envelope * pulse * (fire ? .60 : 1));
        if (seed.size > (fire ? .90 : .60)) sparkFine.circle(x, y,
          (.42 + .18 * seed.size) * visualScale * look.size.ember)
          .fill({ color: fire ? 0xff9d48 : lerpColor(color, 0xffffff,
                                  Math.min(1, appearance.particle_white_mix + .28)),
                  alpha: Math.min(1, (fire ? .48 : .87) * envelope * pulse * look.brightness.ember) });
      } else if (seed.type === 1) {
        emitParticle(1, x, y, 2.0 * seed.size * visualScale, 17 * seed.size * visualScale,
                     seed.rotation + tangent, bright, .68 * envelope);
      } else if (seed.type === 2) {
        emitParticle(2, x, y, 38 * seed.size * (1 + .5 * progress) * visualScale,
                     22 * seed.size * (1 + .4 * progress) * visualScale,
                     seed.rotation + t * .11,
                     particleStyle === 'fire' || localFire ? 0x5c2735 :
                       lerpColor(color, 0xe2e0e2, .82),
                     (particleStyle === 'fire' || localFire ? .32 : .09) *
                       envelope * pulse);
      } else if (seed.type === 3) {
        const fire = particleStyle === 'fire' || localFire;
        emitParticle(3, x, y, (fire ? 54 : 17) * seed.size * visualScale,
                     (fire ? 110 : 42) * seed.size * (1 - .5 * progress) * visualScale,
                     seed.rotation * .28 + tangent * .15,
                     fire ? lerpColor(color, 0xff7d1e, .55) : color,
                     (fire ? .76 : .12) * envelope *
                     (fire ? .7 + .3 * Math.sin(seed.phase + t * 8) ** 2 : 1));
      } else if (seed.type === 4) {
        const fire = particleStyle === 'fire' || localFire;
        emitParticle(4, x, y, (fire ? 62 : 96) * seed.size * (1 + .5 * progress) * visualScale,
                     (fire ? 62 : 96) * seed.size * (1 + .5 * progress) * visualScale,
                     0, fire ? 0xff722c : lerpColor(color, 0xffffff, .56),
                     (fire ? .20 : .35) * envelope * pulse);
      } else if (seed.type === 5) {
        const diameter = 8 * seed.size * (1 - .4 * progress);
        emitParticle(5, x, y, diameter * visualScale, diameter * visualScale, seed.rotation,
                     bright, .52 * envelope);
      } else {
        emitParticle(6, x, y, (1.5 + seed.size) * visualScale,
                     (6 + 8 * seed.size) * (1 - .5 * progress) * visualScale,
                     tangent, bright, .61 * envelope);
        const tail = Math.min(seed.ribbonTail, t);
        if (tail > .045) {
          let previous = sampleFlowParticle(seed, emitter, t - tail);
          const flicker = .72 + .28 * Math.sin(time * 8.1 + seed.phase);
          for (let j = 1; j <= 9; j++) {
            const point = sampleFlowParticle(seed, emitter, t - tail + tail * j / 9);
            const u = (j - .5) / 9;
            const taper = Math.pow(Math.sin(Math.PI * u), .72);
            const texture = .72 + .28 * Math.sin(j * 2.47 + seed.phase + time * 3.3);
            const opacity = texture * flicker * envelope * seed.ribbonGlow *
                            look.brightness.filament * (localFire ? 1.3 : 1);
            const coreWidth = Math.max(.18, seed.ribbonWidth * taper) *
                              (.62 + .38 * Math.sqrt(trailFade)) * visualScale *
                              look.size.filament;
            const x0 = center + previous.x * visualScale, y0 = strikeY + previous.y * visualScale;
            const x1 = center + point.x * visualScale, y1 = strikeY + point.y * visualScale;
            filamentGlow.moveTo(x0, y0).lineTo(x1, y1)
              .stroke({ color, alpha: Math.min(.82, .53 * opacity),
                        width: coreWidth * (3.2 + .6 * seed.aspect) });
            filamentCore.moveTo(x0, y0).lineTo(x1, y1)
              .stroke({ color: localFire ? lerpColor(color, 0xff897b, .28) :
                        lerpColor(bright, 0xffffff,
                                  appearance.particle_white_mix * .62),
                        alpha: Math.min(1, 1.21 * opacity), width: coreWidth });
            previous = point;
          }
        }
      }
    }
  }
  // A compact coda plume continues to curl after the final keystrokes. Its
  // paths are sampled from absolute score time, so section renders join cleanly.
  for (const seed of tailParticles) {
    const age = time - seed.birth;
    if (age < 0 || age >= seed.life) continue;
    const key = keys.get(seed.pitch);
    if (!key) continue;
    const center = (key.x0 + key.x1) / 2;
    const point = sampleTailParticle(seed, age);
    const previous = sampleTailParticle(seed, Math.max(0, age - .025));
    const tangent = Math.atan2(point.x - previous.x,
                               previous.y - point.y);
    const x = center + point.x * visualScale;
    const y = strikeY + point.y * visualScale;
    const alpha = tailParticleAlpha(seed, age) * (.50 + .34 * seed.power);
    const color = lerpColor(seed.tint, 0xffffff, .23);
    emitParticle(0, x, y, (1.7 + .85 * seed.size) * visualScale,
      (2.6 + 1.55 * seed.size) * visualScale, tangent, color, alpha);
    if (seed.ribbon && age < seed.ribbonLife) {
      const ribbonExit = Math.min(1, (seed.ribbonLife - age) / .65);
      const ribbonAlpha = alpha * ribbonExit * ribbonExit *
        (3 - 2 * ribbonExit);
      const tail = Math.min(age, .22 + .08 * seed.size);
      let last = sampleTailParticle(seed, age - tail);
      for (let j = 1; j <= 6; j++) {
        const next = sampleTailParticle(seed, age - tail + tail * j / 6);
        const taper = Math.sin(Math.PI * (j - .5) / 6);
        const width = (.35 + .95 * seed.size) * taper * visualScale;
        const x0 = center + last.x * visualScale;
        const y0 = strikeY + last.y * visualScale;
        const x1 = center + next.x * visualScale;
        const y1 = strikeY + next.y * visualScale;
        filamentGlow.moveTo(x0, y0).lineTo(x1, y1)
          .stroke({ color: seed.tint, alpha: ribbonAlpha * .46,
                    width: width * 3.2 });
        filamentCore.moveTo(x0, y0).lineTo(x1, y1)
          .stroke({ color, alpha: ribbonAlpha * .90, width });
        last = next;
      }
    }
  }
  for (let type = 0; type < particlePools.length; type++) {
    for (let index = usedParticles[type]; index < particlePools[type].length; index++) {
      particlePools[type][index].alpha = 0;
    }
  }
  for (const flame of fireTongues) flame.sprite.visible = false;
  if (fireLayer.visible) for (const [pitch, note] of
      new Map([...recentFireLead.entries(), ...recentFirePiano.entries()])) {
    if (particleStyle !== 'fire' && !note.accent_fire) continue;
    const key = keys.get(pitch);
    const center = (key.x0 + key.x1) / 2;
    const age = time - note.audio_start;
    const leadFlame = note.family !== 'piano';
    const envelope = sampleFlameEnvelope(age, note.audio_end - note.audio_start,
                                         leadFlame ? .46 : .36);
    if (envelope.intensity <= 0) continue;
    const flame = fireTongues[pitch - minPitch];
    const { sprite, fireFilter } = flame;
    sprite.visible = true;
    sprite.x = center;
    sprite.y = strikeY + 2 * visualScale;
    sprite.width = (leadFlame ? 52 : 66) * visualScale;
    sprite.height = (leadFlame ? 110 : 135) * visualScale;
    fireFilter.resources.fireUniforms.uniforms.uTime = materialTime;
    fireFilter.resources.fireUniforms.uniforms.uLead = leadFlame ? 1 : 0;
    fireFilter.resources.fireUniforms.uniforms.uGrowth = envelope.growth;
    fireFilter.resources.fireUniforms.uniforms.uStrength =
      (leadFlame ? .82 : 1.02) * envelope.intensity *
      (note.accent_fire ? .75 : fireMix);
  }
  function fireSourcesAt(sampleTime) {
    const fireEntry = timeline.fire_entry_seconds ?? -Infinity;
    const accentOnly = sampleTime < fireEntry;
    const latest = new Map();
    const sampleLook = visualAt(sampleTime);
    for (const { note } of noteObjects) {
      if (note.audio_start > sampleTime || note.audio_end + .26 < sampleTime) continue;
      if (accentOnly && !note.accent_fire) continue;
      if (note.family !== 'piano' && !note.accent_fire &&
          !orchestraFeatured(note, sampleTime, sampleLook)) continue;
      const previous = latest.get(note.midi_pitch);
      const held = note.audio_end > sampleTime;
      const previousHeld = previous?.audio_end > sampleTime;
      if (!previous || (held && !previousHeld) ||
          (held === previousHeld && note.audio_start > previous.audio_start))
        latest.set(note.midi_pitch, note);
    }
    return [...latest.values()].map(note => {
      const key = keys.get(note.midi_pitch);
      return { pitch: note.midi_pitch, x: (key.x0 + key.x1) / 2,
        start: Math.max(note.audio_start, note.accent_fire ? -Infinity : fireEntry),
        duration: note.audio_end - Math.max(note.audio_start, note.accent_fire ? -Infinity : fireEntry),
        lead: note.family !== 'piano', tutti: note.accent_tutti === true };
    });
  }
  fireExperiments.render(localAccentFire ? 'footage' :
    (particleStyle === 'fire' ? fireMode : 'procedural'),
    time, fireSourcesAt, appearance.fire_playback_speed ?? 1,
    localAccentFire ? Math.max(.82, fireMix) : fireMix);
  for (const [pitch, note] of active) {
    const key = keys.get(pitch), color = colorFor(note, time, look);
    const attack = Math.exp(-(time - note.audio_start) * 11);
    contactPoint.roundRect(key.x0 - 1, strikeY - 2 * visualScale,
                           key.x1 - key.x0 + 2, 3 * visualScale, 1.5 * visualScale)
      .fill({ color: lerpColor(color, 0xffffff, .72),
              alpha: Math.min(1, (.25 + .58 * attack) * look.brightness.strike_flash *
                                  appearance.impact_scale) });
    const y = strikeY + 7, h = key.black ? (keyHeight - 24) * .61 : keyHeight - 24;
    if (key.black) {
      blackKeyGlow.roundRect(key.x0 - 2, strikeY - 6, key.x1 - key.x0 + 4, h + 14, 2)
        .fill({ color, alpha: .25 });
      blackPressedKeys.roundRect(key.x0 + 1, y, key.x1 - key.x0 - 2, h, 1.5)
        .fill({ color, alpha: .57 });
      blackPressedKeys.moveTo(key.x0 + 3, y + 2).lineTo(key.x1 - 3, y + 2)
        .stroke({ color: 0xffffff, alpha: .72, width: 1 });
    } else {
      whiteKeyPath(keyGlow, pitch, y, y + h).fill({ color, alpha: .25 });
      whiteKeyPath(pressedKeys, pitch, y, y + h).fill({ color, alpha: .70 });
      const leftBlack = keys.get(pitch - 1), rightBlack = keys.get(pitch + 1);
      const x0 = leftBlack?.black ? Math.max(key.x0 + 1, leftBlack.x1 + 1) : key.x0 + 1;
      const x1 = rightBlack?.black ? Math.min(key.x1 - 1, rightBlack.x0 - 1) : key.x1 - 1;
      if (x1 - x0 > 5) pressedKeys.moveTo(x0 + 2, y + 2).lineTo(x1 - 2, y + 2)
        .stroke({ color: 0xffffff, alpha: .72, width: 1 });
    }
  }
  strikeGlow.moveTo(0, strikeY).lineTo(width, strikeY)
    .stroke({ color: strikeColor, width: 4, alpha: .46 });
  strikeCore.moveTo(0, strikeY).lineTo(width, strikeY)
    .stroke({ color: 0xffffff, width: 1.3, alpha: .85 });
  finalFade.alpha = outro ? easeBetween(time,
    outro.fade_start_seconds, outro.fade_end_seconds) : 0;
  app.render();
}

window.renderAt = renderAt;
window.renderPresentationAt = time => {
  const scoreTime = time - (intro?.lead_in_seconds ?? 0);
  renderAt(scoreTime, scoreTime, time);
};
window.exportFrame = time => {
  window.renderPresentationAt(time);
  return app.canvas.toDataURL('image/png');
};
window.waterfallInfo = { width, height, minPitch, maxPitch, renderer: app.renderer.type };
window.waterfallReady = true;
window.renderPresentationAt(sampleStart);
