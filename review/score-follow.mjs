// Score regions carry observed PDF geometry and independently matched reference
// times. MIDI-inferred bar numbers need not be the printed score's bar numbers.
export function recordingTimeAt(timeMap,referenceTime){
  if(!Array.isArray(timeMap)||!timeMap.length||!Number.isFinite(referenceTime))return null;
  let low=0,high=timeMap.length;
  while(low<high){const mid=(low+high)>>1;if(timeMap[mid].midi_seconds<=referenceTime)low=mid+1;else high=mid;}
  if(!low)return timeMap[0].audio_seconds;
  if(low===timeMap.length)return timeMap.at(-1).audio_seconds;
  const a=timeMap[low-1],b=timeMap[low];
  return a.audio_seconds+(referenceTime-a.midi_seconds)/(b.midi_seconds-a.midi_seconds)*(b.audio_seconds-a.audio_seconds);
}

export function prepareScoreRegions(document,alignment,corrections=null,numbered=null){
  const overrides=new Map((corrections?.anchors||[]).map(anchor=>[anchor.region_id,anchor]));
  const suppressed=new Set((numbered?.suppressed_duplicate_systems||[]).map(s=>`pdf-${String(s.page).padStart(3,'0')}-system-${s.system}`));
  const parents=(document.score_regions||[]).filter(r=>!suppressed.has(r.region_id)||overrides.has(r.region_id));
  const children=numbered?numbered.measures:[...(document.bar_regions||[])];
  // Keep any previously saved fine-region time corrections addressable.
  const legacy=numbered?(document.bar_regions||[]).filter(r=>overrides.has(r.region_id)):[];
  return [...parents,...children,...legacy].filter(region=>
    !region.parent_region_id||!overrides.has(region.parent_region_id)||overrides.has(region.region_id)).map((original,index)=>{
    const start=original.midi_start_seconds??original.reference_start_seconds;
    const end=original.midi_end_seconds??original.reference_end_seconds;
    const audioStart=Number.isFinite(start)?recordingTimeAt(alignment.time_map,start):original.audio_start_seconds;
    const audioEnd=Number.isFinite(end)?recordingTimeAt(alignment.time_map,end):original.audio_end_seconds;
    const manual=overrides.get(original.region_id);
    return {...original,region_id:original.region_id||`score-region-${index}`,start,end,
      audioStart:manual?.start_seconds??audioStart,audioEnd:manual?.end_seconds??audioEnd,
      manual_timing:Boolean(manual),stable_candidate:manual?true:original.stable_candidate,
      review_status:manual?'corrected':original.review_status};
  }).filter(region=>Number.isFinite(region.audioStart)&&Number.isFinite(region.audioEnd)
    &&region.audioEnd>region.audioStart&&Array.isArray(region.rect_pt)&&region.rect_pt.length===4)
    .sort((a,b)=>a.audioStart-b.audioStart);
}

export function scoreRegionAt(regions,time,stableOnly=false){
  if(!Number.isFinite(time)||!regions.length)return null;
  let low=0,high=regions.length;
  while(low<high){const mid=(low+high)>>1;if(regions[mid].audioStart<=time)low=mid+1;else high=mid;}
  let selected=null;
  for(let i=low-1;i>=0;i--){
    const region=regions[i];
    if(time>=region.audioEnd||(stableOnly&&!region.stable_candidate))continue;
    if(!selected||region.manual_timing&&!selected.manual_timing
      ||Boolean(region.manual_timing)===Boolean(selected.manual_timing)
        &&region.rect_pt[2]*region.rect_pt[3]<selected.rect_pt[2]*selected.rect_pt[3])selected=region;
  }
  return selected;
}

export function scoreRegionAtPoint(regions,page,xFraction,yFraction){
  return regions.filter(region=>{
    if(region.page_number!==page)return false;
    const [x,y,w,h]=region.rect_pt;
    return xFraction>=x/region.page_width_pt&&xFraction<=(x+w)/region.page_width_pt
      &&yFraction>=y/region.page_height_pt&&yFraction<=(y+h)/region.page_height_pt;
  }).sort((a,b)=>a.rect_pt[2]*a.rect_pt[3]-b.rect_pt[2]*b.rect_pt[3])[0]||null;
}
