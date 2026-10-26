import {buildPlaybackRegions,playheadPosition,scoreTimeCovered} from './playhead.mjs';
import {prepareScoreRegions,scoreRegionAt} from './score-follow.mjs';
import {highlightPercent,revealRegionScroll,measureIndexAt} from './score-display.mjs';

export function outputSegments(config){
  let offset=0;
  return config.segments.map(s=>{
    if(!Number.isFinite(s.video_start)||!Number.isFinite(s.video_end)||s.video_end<=s.video_start)throw Error('Invalid video segment');
    const row={...s,output_start:offset,output_end:offset+s.video_end-s.video_start};offset=row.output_end;return row;
  });
}

// No media element, wall clock, DOM animation, or previous call participates in
// this function. Calling times in reverse order produces the same answer.
export function createExportRenderer(input){
  const {project,config}=input,alignment=project.alignment;
  const mapping=new Map((project.symbolic_pdf_regions||project.mapping.measures).map(m=>[m.measure_id,m]));
  const regions=prepareScoreRegions(project.mapping,alignment,project.score_region_anchors,project.score_measures);
  const playback=buildPlaybackRegions(alignment.measures,mapping),segments=outputSegments(config);
  const boxes=regions.length?regions:[...mapping.values()];
  const times=[...new Set([0,...alignment.measures.map(m=>m.start_seconds-.001),...regions.map(r=>r.audioStart)])].sort((a,b)=>a-b);
  const viewport=config.layout.score,zoom=config.score_zoom||1;
  function locate(time){
    const m=alignment.measures[measureIndexAt(alignment.measures,time)];
    const box=regions.length?scoreRegionAt(regions,time):mapping.get(m.measure_id);
    return {box,region:regions.length?box:playback.get(m.measure_id),m};
  }
  function dimensions(box){
    const scale=Math.min(viewport.w/box.page_width_pt,viewport.h/box.page_height_pt)*zoom;
    const width=box.page_width_pt*scale,height=box.page_height_pt*scale;
    return {scale,width,height,x:Math.max(0,(viewport.w-width)/2),y:Math.max(0,(viewport.h-height)/2)};
  }
  const follows=[];let last=null,scroll={top:0,left:0},page=null;
  for(const t of times){
    const {box}=locate(Math.max(0,t));if(!box)continue;
    const id=box.region_id||box.measure_id;
    if(id===last)continue;last=id;
    if(page!==box.page_number){scroll={top:0,left:0};page=box.page_number;}
    const d=dimensions(box),[x,y,w,h]=box.rect_pt;
    const target={top:d.y+y*d.scale-scroll.top,bottom:d.y+(y+h)*d.scale-scroll.top,
      left:d.x+x*d.scale-scroll.left,right:d.x+(x+w)*d.scale-scroll.left};
    const next=revealRegionScroll(scroll,target,{top:0,left:0,right:viewport.w,bottom:viewport.h});
    scroll={top:Math.max(0,Math.min(Math.max(0,d.height-viewport.h),next.top)),
      left:Math.max(0,Math.min(Math.max(0,d.width-viewport.w),next.left))};
    follows.push({time:t,page,box,scroll:{...scroll}});
  }
  function renderAt(outputTime){
    const segment=segments.find(s=>outputTime>=s.output_start&&outputTime<s.output_end);
    if(!segment)return null;
    const videoTime=segment.video_start+outputTime-segment.output_start,musicTime=videoTime-config.music_start_video;
    const {box,region,m}=locate(videoTime);
    const follow=follows.findLast(f=>f.time<=videoTime),page=box?.page_number??follow?.page??1;
    const covered=scoreTimeCovered(alignment.score_time_coverage,videoTime)&&musicTime>=0;
    const interpretation=(input.annotations||[]).some(e=>e.slot==='interpretation'&&e.phase!=='intro'&&videoTime>=e.video_start&&videoTime<e.video_end);
    const visible=covered&&!interpretation;
    const d=box||follow?.box?dimensions(box||follow.box):null,scroll=follow?.scroll||{top:0,left:0};
    const percent=box?highlightPercent(box):null;
    const rect=percent&&d?[viewport.x+d.x+percent.left/100*d.width-scroll.left,
      viewport.y+d.y+percent.top/100*d.height-scroll.top,percent.width/100*d.width,percent.height/100*d.height]:null;
    const flags=m?.flags||[];
    const unreliable=flags.some(f=>['feature_variant_disagreement_over_2s','weak_independent_pitch_evidence','insufficient_pitched_reference'].includes(f));
    const invalid=rect&&(!rect.every(Number.isFinite)||rect[2]<=0||rect[3]<=0||rect[2]*rect[3]>=d.width*d.height*.94);
    const position=box&&covered&&!unreliable&&!invalid?playheadPosition(alignment.time_map,videoTime,box,region):null;
    return {outputTime,videoTime,musicTime,viewport:{...viewport},visible,page,measureId:m?.measure_id,
      pageGeometry:d?{...d,scroll}:null,highlight:visible&&!invalid&&!unreliable?rect:null,
      playhead:visible&&position?{x:viewport.x+d.x+position.leftPercent/100*d.width-scroll.left,
        y:regions.length?rect[1]:viewport.y+d.y-scroll.top,height:regions.length?rect[3]:d.height}:null,
      issue:covered&&!box?'unlocated_score_interval_page_only':invalid?'invalid_or_whole_page_highlight':unreliable?'low_confidence_location_hidden':null};
  }
  function plan(){
    const boundaries=new Set([0,segments.at(-1).output_end]);
    const videoTimes=[...times,...regions.map(r=>r.audioEnd),
      ...alignment.time_map.map(p=>p.audio_seconds),config.music_start_video,
      alignment.score_time_coverage?.end_seconds,
      ...(input.annotations||[]).flatMap(e=>[e.video_start,e.video_end])].filter(Number.isFinite);
    for(const s of segments){boundaries.add(s.output_start);boundaries.add(s.output_end);
      for(const v of videoTimes)if(v>s.video_start&&v<s.video_end)boundaries.add(s.output_start+v-s.video_start);}
    const sorted=[...boundaries].sort((a,b)=>a-b),events=[];
    for(let i=0;i<sorted.length-1;i++){
      const start=sorted[i],end=sorted[i+1];if(end-start<1e-7)continue;
      const state=renderAt(start+1e-7),tail=renderAt(end-1e-7);
      events.push({start,end,...state,playheadEnd:tail?.playhead});
    }
    return {format_version:'1.0',segments,duration:segments.at(-1).output_end,viewport,
      reuse:['playhead.mjs','score-follow.mjs','score-display.mjs'],events};
  }
  return {renderAt,plan,boxes};
}
