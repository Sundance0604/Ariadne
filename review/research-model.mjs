// Score coordinates are primary; recording seconds are a runtime projection.
export const dimensions=['harmony','counterpoint','form','orchestration','motif'];
export const dimensionLabels={harmony:'和声',counterpoint:'对位',form:'曲式',orchestration:'配器',motif:'动机'};
export const claimLabels={score_observation:'谱面观察',theoretical_analysis:'理论解释',hermeneutic_interpretation:'诠释观点'};
export function spanMatches(span,context){
  if(span.precision==='reference_interval_candidate')return Number.isFinite(context.referenceTick)&&
    context.referenceSha256===span.reference_sha256&&context.referenceTick>=span.reference_start_tick&&context.referenceTick<span.reference_end_tick;
  if(span.precision==='unlocated'||!Number.isFinite(context.playingPage))return false;
  if(context.playingPage<span.pdf_page_start||context.playingPage>span.pdf_page_end)return false;
  if(span.precision==='page_range')return true;
  if(span.precision==='score_segment_candidate')return (span.region_ids||[]).some(id=>id===context.regionId||id===context.referenceId);
  const point=[context.playingPage,context.systemIndex,context.x];
  if(!point.every(Number.isFinite))return false;
  const compare=(a,b)=>a[0]-b[0]||a[1]-b[1]||a[2]-b[2];
  return compare(point,span.score_start)>=0&&compare(point,span.score_end)<0;
}
export function indexResearch(data){
  return new Map(dimensions.map(d=>[d,(data.events||[]).filter(e=>e.dimension===d)]));
}
export function activeEvents(index,context){
  return new Map(dimensions.map(d=>[d,(index.get(d)||[]).filter(event=>event.score_spans.some(span=>spanMatches(span,context)))]));
}
export function eventScope(event,context){
  const spans=event.score_spans.filter(span=>spanMatches(span,context));
  const reference=spans.find(s=>s.precision==='reference_interval_candidate');
  return reference?`参考音符窗口候选 · 证据PDF ${reference.pdf_page_start}–${reference.pdf_page_end}页 · 非逐音实播校准`:
    spans.some(s=>s.precision==='score_segment')?'谱面段落 · 时间待复核':
    spans.some(s=>s.precision==='score_segment_candidate')?'候选区域 · 待复核':'本页／本段背景 · 仅页级定位';
}

export function referenceTickAt(clock,seconds){
  if(!Array.isArray(clock)||!clock.length||!Number.isFinite(seconds)||seconds<clock[0].midi_seconds)return null;
  let lo=0,hi=clock.length;while(lo<hi){const mid=(lo+hi)>>1;if(clock[mid].midi_seconds<=seconds)lo=mid+1;else hi=mid;}
  const row=clock[lo-1];if(!(row.seconds_per_tick>0))return null;
  return row.tick+(seconds-row.midi_seconds)/row.seconds_per_tick;
}
export function relatedEssay(essays,context,currentId){
  const matches=essays.filter(essay=>essay.score_spans.some(span=>spanMatches(span,context)));
  return matches.find(e=>e.id===currentId)||matches[0]||null;
}
export function spanNavigation(span,verification,regions=[]){
  if(span.precision==='unlocated')return {page:null,canSeek:false,time:null};
  const matching=regions.filter(r=>(span.region_ids||[]).includes(r.region_id||r.measure_id));
  const region=matching.find(r=>r.manual_timing&&Number.isFinite(r.audioStart));
  const canSeek=span.precision!=='page_range'&&verification.location==='verified'&&
    ['verified','manual_reviewed'].includes(verification.timing)&&Boolean(region);
  return {page:span.pdf_page_start,canSeek,time:canSeek?region.audioStart:null};
}
