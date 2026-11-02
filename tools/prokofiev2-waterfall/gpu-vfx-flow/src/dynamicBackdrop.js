import { Filter, GlProgram, Rectangle, Sprite, Texture } from 'pixi.js';

// A deliberately low-frequency, time-addressable backdrop. Every frame is a
// function of score time, so isolated excerpts and later full exports agree at
// their joins. Rendering the filter at half resolution keeps the 4K notes and
// keyboard crisp while limiting the cost of the atmospheric layer.
const vertex = `
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
`;

const fragment = `
  in vec2 vTextureCoord;
  out vec4 finalColor;
  uniform float uTime;
  uniform float uMode;
  uniform float uStrength;
  uniform float uAspect;

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
  float fbm(vec2 p) {
    return .55 * noise(p) + .29 * noise(p * 2.03 + 11.7) +
           .16 * noise(p * 4.11 - 7.2);
  }
  float gaussian(float x, float sigma) {
    return exp(-.5 * x * x / (sigma * sigma));
  }
  void main(void) {
    vec2 uv = vTextureCoord;
    // With this correction, one shape has the same proportions in 16:9 and
    // other export sizes. All movement is intentionally slower than the notes.
    vec2 p = vec2((uv.x - .5) * uAspect, uv.y - .5);
    float t = uTime;
    vec3 color = vec3(0.0);
    float energy = 0.0;
    if (uMode < 1.5) {
      // Smoke: a broad, self-warping density field rather than an animated
      // photograph. Coherent eddies move and reshape throughout the excerpt.
      vec2 drift = vec2(.045 * t, -.033 * t);
      vec2 q = p * vec2(2.65, 3.25) + drift;
      float w1 = fbm(q * .72 + vec2(1.7, 3.2));
      float w2 = fbm(q * .81 - vec2(3.4, 1.1) - drift * .67);
      vec2 warped = q + vec2(w1 - .5, w2 - .5) * 1.85;
      float body = fbm(warped);
      float filament = fbm(warped * 1.38 + vec2(7.8, -2.6));
      float folds = smoothstep(.47, .73, body * .72 + filament * .28);
      float vapor = smoothstep(.31, .61, body);
      float placement = gaussian(p.x + .36 + .09 * sin(t * .10), .47) *
                        gaussian(p.y - .04, .32);
      energy = placement * (.62 * vapor + .38 * folds);
      color = mix(vec3(.025, .095, .15), vec3(.19, .31, .39), folds);
      color += vec3(.12, .10, .12) * smoothstep(.63, .79, filament) * .32;
    } else if (uMode < 2.5) {
      // Soft bloom: independent, wandering pools with a textured core. The
      // dark centre stays clear enough for dense piano and orchestra notes.
      float cloud = fbm(p * 2.6 + vec2(t * .024, -t * .018));
      vec2 a = vec2(-.61 + .13 * sin(t * .12), -.24 + .09 * cos(t * .075));
      vec2 b = vec2(.59 + .11 * cos(t * .085), .10 + .08 * sin(t * .095));
      vec2 c = vec2(-.07 + .15 * sin(t * .065 + 1.8), .34);
      float blue = gaussian((p.x - a.x) / .75, 1.0) *
                   gaussian((p.y - a.y) / .36, 1.0);
      float violet = gaussian((p.x - b.x) / .63, 1.0) *
                     gaussian((p.y - b.y) / .40, 1.0);
      float silver = gaussian((p.x - c.x) / .88, 1.0) *
                     gaussian((p.y - c.y) / .24, 1.0);
      float texture = .66 + .34 * cloud;
      color = (vec3(.075, .18, .31) * blue +
               vec3(.17, .105, .24) * violet +
               vec3(.16, .20, .22) * silver * .47) * texture;
      energy = min(1.0, blue * .58 + violet * .47 + silver * .24);
    } else {
      // Light rays: several softly separated shafts whose angle, width and
      // intensity wander independently. They are a light source, not a still
      // image of a lamp or a conspicuous geometric fan.
      float y = uv.y;
      float sourceX = -.52 + .07 * sin(t * .07);
      float ray1 = gaussian(p.x - (sourceX + .68 * y + .06 * sin(t * .11)), .11);
      float ray2 = gaussian(p.x - (sourceX + 1.10 * y - .10 * sin(t * .075)), .075);
      float ray3 = gaussian(p.x - (sourceX + 1.48 * y + .08 * cos(t * .09)), .16);
      float broken = .58 + .42 * fbm(vec2(p.x * 4.2 + t * .018,
                                          y * 2.7 - t * .027));
      float vertical = smoothstep(.02, .18, y) * (1.0 - smoothstep(.66, 1.0, y));
      float rays = (ray1 * .56 + ray2 * .34 + ray3 * .29) * broken * vertical;
      float source = gaussian(p.x - sourceX, .21) * gaussian(y - .12, .11);
      energy = rays + source * .30;
      color = vec3(.29, .34, .37) * rays + vec3(.25, .28, .27) * source * .19;
    }
    // Suppress both side edges and the keyboard boundary. This keeps the new
    // layer in the black field without a visible rectangle or hard seam.
    float edge = smoothstep(0.0, .10, uv.x) *
                 smoothstep(0.0, .10, 1.0 - uv.x) *
                 smoothstep(0.0, .12, uv.y) *
                 smoothstep(0.0, .16, 1.0 - uv.y);
    float alpha = clamp(energy * uStrength * edge, 0.0, .72);
    finalColor = vec4(color, alpha);
  }
`;

const modeIds = { smoke: 1, bloom: 2, rays: 3 };

export function createDynamicBackdrop(app, width, strikeY, options) {
  if (!options) return () => {};
  const mode = modeIds[options.mode];
  if (!mode) throw new Error(`Unknown dynamic backdrop: ${options.mode}`);
  const strength = Number(options.strength ?? 1);
  const speed = Number(options.speed ?? 1);
  if (!Number.isFinite(strength) || strength < 0 || strength > 2 ||
      !Number.isFinite(speed) || speed <= 0 || speed > 3)
    throw new Error('Invalid dynamic backdrop strength or speed');
  const backdrop = new Sprite(Texture.WHITE);
  backdrop.x = 0; backdrop.y = 0;
  backdrop.width = width; backdrop.height = strikeY;
  backdrop.filterArea = new Rectangle(0, 0, width, strikeY);
  const filter = new Filter({
    glProgram: GlProgram.from({ vertex, fragment }),
    resolution: .5,
    resources: { backdropUniforms: {
      uTime: { value: 0, type: 'f32' },
      uMode: { value: mode, type: 'f32' },
      uStrength: { value: strength, type: 'f32' },
      uAspect: { value: width / strikeY, type: 'f32' },
    } },
  });
  backdrop.filters = [filter];
  app.stage.addChild(backdrop);
  return time => { filter.resources.backdropUniforms.uniforms.uTime = time * speed; };
}
