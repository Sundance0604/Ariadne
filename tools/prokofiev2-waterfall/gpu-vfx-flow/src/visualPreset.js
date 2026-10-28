const ranges = {
  motion: {
    flight_speed_scale: [.1, 2],
    launch_speed_scale: [.1, 2],
    launch_speed_pulse: [0, .5],
    launch_speed_pulse_rate: [.1, 20],
    airborne_speed_pulse_scale: [0, 2],
    launch_angle_sweep_radians: [0, .22],
    launch_angle_sweep_rate: [0, 20],
    launch_angle_jitter_radians: [0, .15],
    horizontal_wind_scale: [0, 3],
    vertical_wind_scale: [0, 3],
    plume_spread_pixels: [0, 180],
    plume_breath_rate: [.1, 5],
    plume_early_spread_fraction: [0, 1],
    plume_gather_spread_fraction: [0, 1],
  },
  density: {
    ember_attack_count: [0, 500],
    streak_attack_count: [0, 100],
    filament_attack_count: [0, 100],
    ember_per_second: [0, 500],
    streak_per_second: [0, 50],
    smoke_per_second: [0, 50],
    flame_per_second: [0, 50],
    light_per_second: [0, 50],
    glint_per_second: [0, 50],
    filament_per_second: [0, 50],
  },
  brightness: {
    ember: [0, 2], filament: [0, 2],
    note_glow: [0, 2], note_material: [0, 2], strike_flash: [0, 2],
  },
  size: { ember: [.1, 3], filament: [.1, 3] },
};

const colorKeys = ['piano_low', 'piano_high', 'strings', 'woodwind',
                   'brass', 'strike'];

function checkKeys(object, expected, name, optional = []) {
  if (!object || Array.isArray(object) || typeof object !== 'object')
    throw new Error(`${name} must be an object`);
  const missing = expected.filter(key => !(key in object));
  const extra = Object.keys(object).filter(key => !expected.includes(key) && !optional.includes(key));
  if (missing.length || extra.length)
    throw new Error(`${name}: missing [${missing}], unknown [${extra}]`);
}

export function validateVisualPreset(preset) {
  const baseKeys = ['schema_version', 'motion', 'density', 'colors',
                    'brightness', 'size'];
  if (preset.schema_version !== 1 && preset.schema_version !== 2)
    throw new Error('Unsupported visual preset version');
  checkKeys(preset, preset.schema_version === 2 ? [...baseKeys, 'appearance'] : baseKeys,
            'preset');
  for (const [group, keys] of Object.entries(ranges)) {
    checkKeys(preset[group], Object.keys(keys), group);
    for (const [key, [lower, upper]] of Object.entries(keys)) {
      const value = preset[group][key];
      if (typeof value !== 'number' || !Number.isFinite(value) ||
          value < lower || value > upper)
        throw new Error(`${group}.${key} must be between ${lower} and ${upper}`);
    }
  }
  for (const key of ['ember_attack_count', 'streak_attack_count',
                     'filament_attack_count']) {
    if (!Number.isInteger(preset.density[key]))
      throw new Error(`density.${key} must be an integer`);
  }
  if (preset.motion.plume_gather_spread_fraction >=
      preset.motion.plume_early_spread_fraction)
    throw new Error('plume gather must be narrower than early spread');
  checkKeys(preset.colors, colorKeys, 'colors');
  for (const key of colorKeys) {
    if (!/^#[0-9a-f]{6}$/i.test(preset.colors[key]))
      throw new Error(`colors.${key} must be #RRGGBB`);
  }
  if (preset.schema_version === 2) {
    const appearance = preset.appearance;
    checkKeys(appearance, ['material', 'material_amount', 'material_speed',
      'keyboard_tint', 'horizon_tint', 'color_variation', 'orchestra_base_alpha',
      'orchestra_lead_alpha', 'orchestra_lead_start', 'orchestra_lead_end',
      'orchestra_emitter_scale', 'impact_scale', 'particle_white_mix'], 'appearance',
      ['orchestra_neutral_color', 'orchestra_lead_color', 'particle_style',
       'particle_life_scale', 'edge_strength', 'glow_strength',
       'horizon_strength', 'fire_render_mode', 'fire_playback_speed', 'fire_mix',
       'background_tint', 'background_atmosphere',
       'keyboard_crystal_amount', 'keyboard_metal_amount',
       'keyboard_ember_amount', 'piano_material', 'piano_material_amount',
       'piano_material_opacity', 'piano_material_speed',
       'background_motif_opacity', 'corona_opacity', 'corona_tint',
       'eclipse_image', 'eclipse_gold_mix']);
    if (!['glass', 'crystal', 'metal', 'gilded', 'fracture', 'fire'].includes(appearance.material))
      throw new Error('Unknown material');
    if (appearance.piano_material !== undefined &&
        !['glass', 'crystal', 'metal', 'gilded', 'fracture', 'fire'].includes(appearance.piano_material))
      throw new Error('Unknown piano material');
    for (const key of ['keyboard_tint', 'horizon_tint', 'background_tint',
                       'orchestra_neutral_color', 'orchestra_lead_color'])
      if (appearance[key] !== undefined && !/^#[0-9a-f]{6}$/i.test(appearance[key]))
        throw new Error(`appearance.${key} must be #RRGGBB`);
    if (appearance.corona_tint !== undefined &&
        !/^#[0-9a-f]{6}$/i.test(appearance.corona_tint))
      throw new Error('appearance.corona_tint must be #RRGGBB');
    if (appearance.eclipse_image !== undefined &&
        !['photo', 'procedural'].includes(appearance.eclipse_image))
      throw new Error('appearance.eclipse_image must be photo or procedural');
    if (appearance.particle_style !== undefined &&
        !['spark', 'crystal', 'fire'].includes(appearance.particle_style))
      throw new Error('Unknown particle style');
    if (appearance.fire_render_mode !== undefined &&
        !['procedural', 'sprite', 'fluid', 'metaball', 'footage'].includes(appearance.fire_render_mode))
      throw new Error('Unknown fire render mode');
    for (const [key, [low, high]] of Object.entries({
      material_amount: [0, 2], material_speed: [.1, 3], color_variation: [0, .5],
      piano_material_amount: [0, 3], piano_material_opacity: [0, 2],
      piano_material_speed: [.1, 3],
      orchestra_base_alpha: [0, 1], orchestra_lead_alpha: [0, 1],
      orchestra_emitter_scale: [0, 1], impact_scale: [.1, 4],
      particle_white_mix: [0, 1],
      orchestra_lead_start: [0, 36000], orchestra_lead_end: [0, 36000],
      particle_life_scale: [.1, 2], edge_strength: [0, 2], glow_strength: [0, 2],
      horizon_strength: [0, 2],
      background_atmosphere: [0, 1],
      background_motif_opacity: [0, .4],
      corona_opacity: [0, .8],
      eclipse_gold_mix: [0, 1],
      keyboard_crystal_amount: [0, 1], keyboard_metal_amount: [0, 1],
      keyboard_ember_amount: [0, 1],
      fire_playback_speed: [.3, 2], fire_mix: [0, 1],
    })) {
      const value = appearance[key];
      if (value === undefined && ['particle_life_scale', 'edge_strength', 'glow_strength',
          'horizon_strength',
          'fire_playback_speed', 'fire_mix', 'background_atmosphere',
          'background_motif_opacity', 'corona_opacity', 'eclipse_gold_mix',
          'keyboard_crystal_amount', 'keyboard_metal_amount',
          'keyboard_ember_amount', 'piano_material_amount',
          'piano_material_opacity', 'piano_material_speed'].includes(key)) continue;
      if (typeof value !== 'number' || !Number.isFinite(value) || value < low || value > high)
        throw new Error(`appearance.${key} must be between ${low} and ${high}`);
    }
    if (appearance.orchestra_lead_end < appearance.orchestra_lead_start)
      throw new Error('The orchestra lead window must have nondecreasing times');
  }
  return preset;
}

export function colorNumber(hex) { return Number.parseInt(hex.slice(1), 16); }
