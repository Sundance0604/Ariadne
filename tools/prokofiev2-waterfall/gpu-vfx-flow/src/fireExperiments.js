import { Container, Filter, GlProgram, Rectangle, Sprite, Texture } from 'pixi.js';
import { AdvancedBloomFilter } from 'pixi-filters/advanced-bloom';

const fract = value => value - Math.floor(value);
const random = (a, b = 0) => fract(Math.sin(a * 127.1 + b * 311.7) * 43758.5453);
const clamp = (value, low = 0, high = 1) => Math.max(low, Math.min(high, value));

// Three genuinely different fire renderers share only their musical sources:
// textured sprite combustion, an advected density field, and GPU metaballs.
export function createFireExperiments({ width, strikeY, scale, smokeTexture,
                                        lightTexture, realFireAtlases = [] }) {
  const layer = new Container();
  const spriteLayer = new Container();
  const ballLayer = new Container();
  const footageLayer = new Container();
  layer.addChild(spriteLayer, ballLayer, footageLayer);
  const spritePool = [];
  for (let i = 0; i < 520; i++) {
    const sprite = new Sprite(i % 4 === 0 ? lightTexture : smokeTexture);
    sprite.anchor.set(.5);
    sprite.blendMode = 'add';
    sprite.visible = false;
    spriteLayer.addChild(sprite);
    spritePool.push(sprite);
  }
  spriteLayer.filters = [new AdvancedBloomFilter({ threshold: .19,
    bloomScale: .64, brightness: 1.05, blur: 3, quality: 2 })];

  const metaballProgram = GlProgram.from({
    vertex: `
      in vec2 aPosition; out vec2 vTextureCoord;
      uniform highp vec4 uInputSize; uniform vec4 uOutputFrame;
      uniform vec4 uOutputTexture;
      void main(void) {
        vec2 pos = aPosition * uOutputFrame.zw + uOutputFrame.xy;
        gl_Position = vec4(pos.x * (2.0 / uOutputTexture.x) - 1.0,
          pos.y * (2.0 * uOutputTexture.z / uOutputTexture.y) - uOutputTexture.z, 0.0, 1.0);
        vTextureCoord = aPosition * (uOutputFrame.zw * uInputSize.zw);
      }
    `,
    fragment: `
      in vec2 vTextureCoord; out vec4 finalColor;
      uniform highp vec4 uInputSize; uniform highp vec4 uOutputFrame;
      uniform float uTime; uniform float uSeed; uniform float uLead;
      uniform float uStrength; uniform float uGrowth;
      float hash(float n) { return fract(sin(n * 27.43) * 43758.545); }
      void main(void) {
        vec2 uv = vTextureCoord;
        vec2 p = vec2((uv.x - .5) * 2.0, 1.0 - uv.y);
        float field = 0.0;
        float hot = 0.0;
        for (int i = 0; i < 9; i++) {
          float n = float(i);
          float phase = uTime * (.83 + hash(n + uSeed) * .45) + hash(n * 4.3 + uSeed) * 6.28;
          float rise = .05 + n * .078 + .026 * sin(phase * 1.8);
          float wind = .25 * sin(uTime * .91 + uSeed + rise * 5.1);
          float x = wind * rise + .31 * sin(phase + n * 2.1) * (1.0 - rise * .32);
          float rx = (.30 - .13 * rise) * (.8 + .25 * sin(phase * 1.3));
          float ry = .17 + .035 * sin(phase + n);
          vec2 d = (p - vec2(x, rise)) / vec2(rx, ry);
          float blob = exp(-dot(d, d) * 1.6);
          field += blob * (1.0 - .055 * n);
          hot += blob * (1.0 - rise);
        }
        float edge = smoothstep(.44, .91, field);
        float shape = edge * (1.0 - smoothstep(.63, .86, p.y));
        shape *= 1.0 - smoothstep(uGrowth - .10, uGrowth + .04, p.y);
        float glow = smoothstep(.18, .90, field) * .32;
        float alpha = clamp((shape + glow) * uStrength * .77, 0.0, .91);
        float temperature = clamp(hot * .29 + .16 * sin(uTime * 2.8 + p.x * 4.0), 0.0, 1.0);
        vec3 gold = mix(vec3(.57,.06,.015), vec3(1.0,.43,.065), temperature);
        gold = mix(gold, vec3(1.0,.90,.49), clamp(temperature * temperature * .8, 0.0, 1.0));
        vec3 red = mix(vec3(.38,.014,.025), vec3(1.0,.10,.065), temperature);
        red = mix(red, vec3(1.0,.43,.24), clamp(temperature * temperature * .65, 0.0, 1.0));
        finalColor = vec4(mix(gold, red, uLead) * alpha, alpha);
      }
    `,
  });
  ballLayer.filters = [new AdvancedBloomFilter({ threshold: .22,
    bloomScale: .53, brightness: 1.04, blur: 3, quality: 2 })];
  const balls = [];
  for (let i = 0; i < 88; i++) {
    const filter = new Filter({ glProgram: metaballProgram, resources: {
      fire: { uTime: { value: 0, type: 'f32' },
        uSeed: { value: i * .731, type: 'f32' },
        uLead: { value: 0, type: 'f32' },
        uStrength: { value: 0, type: 'f32' },
        uGrowth: { value: 0, type: 'f32' } },
    } });
    const sprite = new Sprite(Texture.WHITE);
    sprite.anchor.set(.5, 1);
    sprite.filters = [filter];
    sprite.visible = false;
    ballLayer.addChild(sprite);
    balls.push({ sprite, filter });
  }

  // Transparent flipbooks: the filmed 24 fps source was motion interpolated
  // to 96 fps before rendering. Two offset loops hide their wrap seam.
  const realFrames = realFireAtlases.map(atlas => Array.from({ length: 256 }, (_, i) =>
    new Texture({ source: atlas.source,
      frame: new Rectangle((i % 8) * 128, Math.floor(i / 8) * 128, 128, 128) })));
  const footage = [];
  if (realFrames.length) for (let i = 0; i < 88; i++) {
    const pair = [];
    for (let j = 0; j < 2; j++) {
      const sprite = new Sprite(realFrames[i % realFrames.length][0]);
      sprite.anchor.set(.5, 1); sprite.blendMode = 'add';
      sprite.visible = false;
      footageLayer.addChild(sprite);
      pair.push(sprite);
    }
    footage.push(pair);
  }
  footageLayer.filters = [new AdvancedBloomFilter({ threshold: .26,
    bloomScale: .60, brightness: 1.16, blur: 3, quality: 2 })];

  // A small Eulerian field, updated once per frame. Density is injected at
  // each held note, advected by buoyancy and curled crosswind, and dissipates.
  const gridW = Math.round(width / 2), gridH = 72;
  const fieldSize = gridW * gridH;
  let gold = new Float32Array(fieldSize), red = new Float32Array(fieldSize);
  let nextGold = new Float32Array(fieldSize), nextRed = new Float32Array(fieldSize);
  const fieldCanvas = document.createElement('canvas');
  fieldCanvas.width = gridW; fieldCanvas.height = gridH;
  const fieldContext = fieldCanvas.getContext('2d', { willReadFrequently: false });
  const fieldImage = fieldContext.createImageData(gridW, gridH);
  const fieldTexture = Texture.from(fieldCanvas);
  const fieldSprite = new Sprite(fieldTexture);
  fieldSprite.width = width;
  fieldSprite.height = 86 * scale;
  fieldSprite.y = strikeY - fieldSprite.height;
  fieldSprite.blendMode = 'add';
  fieldSprite.filters = [new AdvancedBloomFilter({ threshold: .18,
    bloomScale: .47, brightness: 1.04, blur: 3, quality: 2 })];
  layer.addChild(fieldSprite);
  let lastFieldTime = null;
  function sample(array, x, y) {
    const x0 = Math.max(0, Math.min(gridW - 2, Math.floor(x)));
    const y0 = Math.max(0, Math.min(gridH - 2, Math.floor(y)));
    const fx = clamp(x - x0), fy = clamp(y - y0);
    const at = y0 * gridW + x0;
    return (array[at] * (1 - fx) + array[at + 1] * fx) * (1 - fy) +
      (array[at + gridW] * (1 - fx) + array[at + gridW + 1] * fx) * fy;
  }
  function stepField(t, sources) {
    for (let y = 0; y < gridH; y++) {
      const height = 1 - y / gridH;
      for (let x = 0; x < gridW; x++) {
        const i = y * gridW + x;
        const gust = .67 * Math.sin(t * 1.18 + x * .018 + height * 4.2) +
          .48 * Math.sin(t * 2.03 - x * .031 + height * 9.1);
        const eddy = .45 * Math.sin(t * 2.7 + x * .063 + y * .16);
        const vx = gust + eddy;
        const vy = -(1.47 + .46 * Math.sin(t * 1.31 + x * .027 + y * .046));
        const sx = x - vx, sy = y - vy;
        const loss = .966 - .004 * height;
        nextGold[i] = sample(gold, sx, sy) * loss;
        nextRed[i] = sample(red, sx, sy) * loss;
      }
    }
    for (const source of sources) {
      const age = t - source.start, duration = source.duration;
      const release = age > duration ? clamp(1 - (age - duration) / .24) : 1;
      if (release <= 0) continue;
      const centerX = Math.round(source.x / width * gridW);
      const target = source.lead ? nextRed : nextGold;
      const pulse = .9 + .1 * Math.sin(t * 7.9 + source.pitch);
      for (let dy = 0; dy < 5; dy++) {
        const y = gridH - 1 - dy;
        for (let dx = -10; dx <= 10; dx++) {
          const x = centerX + dx;
          if (x < 0 || x >= gridW) continue;
          const spread = Math.exp(-dx * dx / 32 - dy * dy / 11);
          target[y * gridW + x] += .16 * spread * release * pulse;
        }
      }
    }
    [gold, nextGold] = [nextGold, gold];
    [red, nextRed] = [nextRed, red];
  }
  function drawField() {
    const pixels = fieldImage.data;
    for (let i = 0; i < fieldSize; i++) {
      const g = clamp(gold[i]), r = clamp(red[i]);
      const power = Math.max(g, r);
      const warm = clamp(power * 1.8);
      const topFade = clamp(Math.floor(i / gridW) / 20);
      pixels[i * 4] = 255;
      pixels[i * 4 + 1] = Math.round((g >= r ? 57 : 13) + warm * (g >= r ? 115 : 71));
      pixels[i * 4 + 2] = Math.round((g >= r ? 10 : 19) + warm * 39);
      pixels[i * 4 + 3] = Math.round(235 * Math.pow(power, .9) * topFade);
    }
    fieldContext.putImageData(fieldImage, 0, 0);
    fieldTexture.source.update();
  }
  function renderSprites(t, sources) {
    let used = 0;
    for (const source of sources) {
      const age = t - source.start;
      const first = Math.max(0, Math.floor((age - .53) * 27));
      const last = Math.ceil(Math.min(age, source.duration + .20) * 27);
      for (let birth = first; birth <= last; birth++) {
        const born = birth / 27;
        if (born > source.duration + .18) continue;
        for (let j = 0; j < 3; j++) {
          const phase = age - born - j * .012;
          const seed = source.pitch * 37 + birth * 11 + j * 173;
          const life = .33 + .23 * random(seed, 1);
          if (phase < 0 || phase > life) continue;
          if (used >= spritePool.length) break;
          const part = spritePool[used++];
          const progress = phase / life;
          const wind = 15 * Math.sin(t * 1.19 + source.pitch * .41 + progress * 3.1);
          const curl = 12 * Math.sin(t * 2.07 + seed * .17 + progress * 6.3);
          const lateral = (random(seed, 2) - .5) * 37;
          part.visible = true;
          part.x = source.x + (lateral * (.4 + progress) + wind * progress + curl * progress) * scale;
          part.y = strikeY - (4 + 78 * progress * (.68 + .38 * random(seed, 3))) * scale;
          part.width = (28 + 30 * progress + 19 * random(seed, 4)) * scale;
          part.height = (20 + 28 * progress + 15 * random(seed, 5)) * scale;
          part.rotation = .20 * Math.sin(t * 1.8 + seed);
          part.tint = source.lead ? (j === 0 ? 0xff3522 : 0xd81428) :
            (j === 0 ? 0xffe178 : 0xff862d);
          part.alpha = .31 * Math.sin(Math.PI * progress) ** .7;
        }
      }
    }
    for (let i = used; i < spritePool.length; i++) spritePool[i].visible = false;
  }
  function renderBalls(t, sources) {
    for (const ball of balls) ball.sprite.visible = false;
    for (const source of sources) {
      const ball = balls[source.pitch - 21];
      if (!ball) continue;
      const age = t - source.start;
      const release = age > source.duration ? clamp(1 - (age - source.duration) / .26) : 1;
      const growth = clamp(age / .29);
      ball.sprite.visible = true;
      ball.sprite.x = source.x;
      ball.sprite.y = strikeY + 2 * scale;
      ball.sprite.width = 106 * scale;
      ball.sprite.height = 94 * scale;
      const u = ball.filter.resources.fire.uniforms;
      u.uTime = t;
      u.uLead = source.lead ? 1 : 0;
      u.uStrength = release * (source.lead ? .83 : 1);
      u.uGrowth = growth;
    }
  }
  function renderFootage(t, sources, speedScale) {
    for (const pair of footage) for (const sprite of pair) sprite.visible = false;
    for (const source of sources) {
      const pair = footage[source.pitch - 21];
      if (!pair) continue;
      const age = t - source.start;
      const playbackSpeed = (.85 + (source.pitch % 7) * .045) * speedScale;
      const phase = ((age * 96 * playbackSpeed + source.pitch * 52) % 256 + 256) % 256;
      const mix = Math.sin(Math.PI * phase / 256) ** 2;
      const atlas = realFrames[source.pitch % realFrames.length];
      const release = age > source.duration ? clamp(1 - (age - source.duration) / .28) : 1;
      const growth = clamp(age / .24);
      const strength = (.96 + .04 * Math.sin(t * 3.4 + source.pitch)) * release;
      for (let j = 0; j < 2; j++) {
        const sprite = pair[j];
        sprite.texture = atlas[(Math.floor(phase) + j * 128) % 256];
        sprite.visible = true;
        sprite.x = source.x - 9 * scale + (j ? 2 : -2) * scale;
        sprite.y = strikeY + 5 * scale;
        sprite.width = (source.tutti ? 134 : source.lead ? 100 : 106) * scale;
        sprite.height = (source.tutti ? 193 : source.lead ? 148 : 162) *
          scale * growth;
        sprite.tint = source.tutti ? 0xffbd82 :
          source.lead ? 0xff8790 : 0xffffff;
        sprite.alpha = strength * (j ? 1 - mix : mix);
      }
    }
  }
  function render(mode, time, sourceAt, footageSpeed = 1, intensity = 1) {
    layer.visible = mode !== 'procedural' && intensity > 0;
    layer.alpha = intensity;
    if (!layer.visible) return;
    spriteLayer.visible = mode === 'sprite';
    ballLayer.visible = mode === 'metaball';
    footageLayer.visible = mode === 'footage';
    fieldSprite.visible = mode === 'fluid';
    if (mode === 'sprite') renderSprites(time, sourceAt(time));
    else if (mode === 'metaball') renderBalls(time, sourceAt(time));
    else if (mode === 'footage') renderFootage(time, sourceAt(time), footageSpeed);
    else if (mode === 'fluid') {
      if (lastFieldTime === null || time < lastFieldTime || time - lastFieldTime > .30) {
        gold.fill(0); red.fill(0);
        lastFieldTime = time - .80;
      }
      while (lastFieldTime + 1 / 60 <= time + .0001) {
        lastFieldTime += 1 / 60;
        stepField(lastFieldTime, sourceAt(lastFieldTime));
      }
      drawField();
    }
  }
  return { layer, render };
}
