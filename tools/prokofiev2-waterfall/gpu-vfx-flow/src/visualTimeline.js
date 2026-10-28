// A section starts at its musical cue. Numeric and color controls ease in over
// its transition; shader/material modes change at the midpoint of that cue.
const clamp01 = value => Math.max(0, Math.min(1, value));
const colorPattern = /^#[0-9a-f]{6}$/i;

function blendColor(first, second, amount) {
  const a = Number.parseInt(first.slice(1), 16);
  const b = Number.parseInt(second.slice(1), 16);
  const channel = shift => Math.round(((a >> shift) & 255) * (1 - amount) +
                                     ((b >> shift) & 255) * amount);
  return '#' + [16, 8, 0].map(shift => channel(shift).toString(16).padStart(2, '0')).join('');
}

function blendValue(first, second, amount) {
  if (typeof first === 'number' && typeof second === 'number')
    return first + (second - first) * amount;
  if (typeof first === 'string' && typeof second === 'string' &&
      colorPattern.test(first) && colorPattern.test(second))
    return blendColor(first, second, amount);
  if (first && second && typeof first === 'object' && typeof second === 'object' &&
      !Array.isArray(first) && !Array.isArray(second)) {
    const value = {};
    for (const key of new Set([...Object.keys(first), ...Object.keys(second)])) {
      if (!(key in first)) value[key] = second[key];
      else if (!(key in second)) value[key] = first[key];
      else value[key] = blendValue(first[key], second[key], amount);
    }
    return value;
  }
  return amount < .5 ? first : second;
}

export function sampleVisualPreset(time, sections, fallback) {
  if (!sections?.length) return fallback;
  let index = -1;
  for (let i = 0; i < sections.length; i++) {
    if (time >= sections[i].start_seconds) index = i;
    else break;
  }
  if (index < 0) return fallback;
  const current = sections[index];
  const transition = current.transition_seconds || 0;
  if (index === 0 || transition <= 0 || time >= current.start_seconds + transition)
    return current.preset;
  const previous = sections[index - 1].preset;
  const linear = clamp01((time - current.start_seconds) / transition);
  const eased = linear * linear * (3 - 2 * linear);
  return blendValue(previous, current.preset, eased);
}

export function validateVisualSections(sections, validatePreset) {
  let previous = -Infinity;
  for (const section of sections || []) {
    if (!(section.start_seconds < section.end_seconds) ||
        section.start_seconds <= previous ||
        !Number.isFinite(section.transition_seconds ?? 0) ||
        (section.transition_seconds ?? 0) < 0)
      throw new Error('Visual sections must have increasing starts and valid transitions');
    validatePreset(section.preset);
    previous = section.start_seconds;
  }
}
