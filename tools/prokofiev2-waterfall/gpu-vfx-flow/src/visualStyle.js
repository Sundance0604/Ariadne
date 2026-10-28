const bounds = {
  geometry: {
    piano_white_width: [.2, 1], piano_black_width: [.2, 1],
    piano_corner_radius: [4, 22], orchestra_support_width: [.1, 1],
    orchestra_lead_width: [.1, 1], orchestra_fire_lead_width: [.1, 1],
  },
  surface: {
    piano_face_opacity: [0, 1], piano_face_white_mix: [0, 1],
    piano_inset_white_mix: [0, 1], piano_inset_strength: [0, 1],
    piano_material_short: [0, 1], piano_material_long: [0, 1],
    piano_material_speed: [.1, 3], piano_material_amount: [0, 2],
    piano_bevel_light: [0, 1], piano_bevel_shadow: [0, 1],
  },
  light: {
    piano_rim_base: [0, 1], piano_rim_pulse: [0, 1],
    piano_glow: [0, 2], piano_halo_base: [0, 2],
    piano_halo_pulse: [0, 1], horizon_strength: [0, 2],
    note_bloom_threshold: [0, 1], note_bloom_scale: [0, 3],
    note_bloom_brightness: [0, 3], note_bloom_blur: [0, 12],
  },
};

export function validateVisualStyle(style) {
  if (!style || typeof style !== 'object' || Array.isArray(style) ||
      style.schema_version !== 1 ||
      Object.keys(style).sort().join() !== 'geometry,light,schema_version,surface')
    throw new Error('Visual style must contain schema_version, geometry, surface and light');
  for (const [group, fields] of Object.entries(bounds)) {
    const values = style[group];
    if (!values || typeof values !== 'object' || Array.isArray(values) ||
        Object.keys(values).sort().join() !== Object.keys(fields).sort().join())
      throw new Error(`Visual style ${group} has missing or unknown fields`);
    for (const [name, [low, high]] of Object.entries(fields)) {
      const value = values[name];
      if (typeof value !== 'number' || !Number.isFinite(value) ||
          value < low || value > high)
        throw new Error(`Visual style ${group}.${name} must be ${low}–${high}`);
    }
  }
  return style;
}
