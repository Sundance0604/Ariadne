// The DTW map locates reference time, not individual noteheads on the PDF.
// The final horizontal projection is an estimate inside an observed score region.
export function scoreTimeCovered(coverage,seconds){
  if(!coverage)return true;
  if(!Number.isFinite(seconds)||seconds<coverage.start_seconds||seconds>=coverage.end_seconds)return false;
  return !Array.isArray(coverage.segments)||coverage.segments.some(s=>seconds>=s.start_seconds&&seconds<s.end_seconds);
}

export function referenceTimeAt(timeMap, audioSeconds) {
  if (!timeMap.length) return null;
  let low = 0, high = timeMap.length;
  while (low < high) {
    const mid = (low + high) >> 1;
    if (timeMap[mid].audio_seconds <= audioSeconds) low = mid + 1;
    else high = mid;
  }
  if (!low) return timeMap[0].midi_seconds;
  if (low === timeMap.length) return timeMap.at(-1).midi_seconds;
  const a = timeMap[low - 1], b = timeMap[low];
  const fraction = (audioSeconds - a.audio_seconds) / (b.audio_seconds - a.audio_seconds);
  return a.midi_seconds + fraction * (b.midi_seconds - a.midi_seconds);
}

export function buildPlaybackRegions(measures, mapping) {
  const groups = new Map(), regions = new Map();
  for (const measure of measures) {
    const box = mapping.get(measure.measure_id);
    if (!box) continue;
    const key = box.resolution === 'bar' ? measure.measure_id
      : JSON.stringify([box.page_number, box.system_index, box.resolution, box.rect_pt]);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(measure);
  }
  for (const group of groups.values()) {
    const region = {
      start: Math.min(...group.map(m => m.midi_start_seconds)),
      end: Math.max(...group.map(m => m.midi_end_seconds)),
      audioStart: Math.min(...group.map(m => m.start_seconds)),
      audioEnd: Math.max(...group.map(m => m.end_seconds)),
      grouped: group.length > 1,
    };
    for (const measure of group) regions.set(measure.measure_id, region);
  }
  return regions;
}

export function playheadPosition(timeMap, audioSeconds, box, region) {
  const referenceTime = region?.manual_timing
    ? region.start+Math.max(0,Math.min(1,(audioSeconds-region.audioStart)/(region.audioEnd-region.audioStart)))*(region.end-region.start)
    : region && audioSeconds <= region.audioStart + .001 ? region.start
    : region && audioSeconds >= region.audioEnd - .001 ? region.end
    : referenceTimeAt(timeMap, audioSeconds);
  if (referenceTime === null || !box || !region || !Number.isFinite(region.start)
      || !Number.isFinite(region.end) || region.end <= region.start) return null;
  const fraction = Math.max(0, Math.min(1, (referenceTime - region.start) / (region.end - region.start)));
  const [left, , width] = box.rect_pt;
  return { fraction, leftPercent: (left + width * fraction) / box.page_width_pt * 100, referenceSeconds:referenceTime };
}
