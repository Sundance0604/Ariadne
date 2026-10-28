const clamp01 = value => Math.max(0, Math.min(1, value));

// A new plume begins at the strike line, grows upward, then dies back after
// release. Sampling absolute note age keeps seeks and exported frames stable.
export function sampleFlameEnvelope(age, duration, riseSeconds = .36,
                                    releaseSeconds = .26) {
  if (age <= 0 || age >= duration + releaseSeconds) {
    return { growth: 0, intensity: 0 };
  }
  const progress = clamp01(age / riseSeconds);
  const growth = progress * (2 - progress);
  const ignition = clamp01(age / .07);
  const release = clamp01((duration + releaseSeconds - age) / releaseSeconds);
  return {
    growth: growth * Math.sqrt(release),
    intensity: ignition * release,
  };
}
