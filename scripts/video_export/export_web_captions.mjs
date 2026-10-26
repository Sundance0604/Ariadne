// Read the actual webpage payload and shared HUD formatter. No simulated player.
import fs from 'node:fs';
import {createScoreAnalysisModel} from '../../review/score-analysis-model.mjs';
import {hudTextFor} from '../../review/hud-text.mjs';
import {frameAt,projectedQuarter} from '../../review/musicxml-live.mjs';
import {referenceTimeAt} from '../../review/playhead.mjs';
import {recordingTimeAt} from '../../review/score-follow.mjs';
import {createExportRenderer} from '../../review/video-export.mjs';
const [input,output]=process.argv.slice(2),data=JSON.parse(fs.readFileSync(input,'utf8'));
const {live,research,guide,project,config}=data,model=createScoreAnalysisModel();model.load(research);
const renderer=createExportRenderer({project,config,annotations:[]}),events=[],omitted=[];
const end=config.segments[0].video_end,begin=config.music_start_video;
const coverage=project.alignment.score_time_coverage;
function atQuarter(q){
  const tick=Number(q)*live.projection.ppq,clock=live.projection.reference_clock;
  const row=clock.findLast(r=>r.tick<=tick);return row?recordingTimeAt(project.alignment.time_map,row.midi_seconds+(tick-row.tick)*row.seconds_per_tick):null;
}
const times=[...new Set([begin,end,...live.frames.flatMap(f=>[atQuarter(f.start_q),atQuarter(f.end_q)]),
  ...project.alignment.measures.map(m=>m.start_seconds),coverage?.end_seconds,59,69,95])].filter(t=>Number.isFinite(t)&&t>=begin&&t<=end).sort((a,b)=>a-b);
const last=new Map();
function emit(slot,start,finish,text,source){
  if(!text.trim()||finish<=start)return;
  const old=last.get(slot);
  if(old&&old.text===text&&Math.abs(old.video_end-start)<.002){old.video_end=finish;return;}
  const row={id:`web-${slot}-${events.length+1}`,slot,video_start:start,video_end:finish,text,phase:'performance',source};
  events.push(row);last.set(slot,row);
}
const forbidden=/待分析|待核查|待核对|待审|待复核|尚未.{0,8}复核|未验证|估计位置|待补充|待定位|置信度|TODO|FIXME|DEBUG|未定位|证据另查/iu;
for(let i=0;i<times.length-1;i++){
  const start=times[i],finish=times[i+1],t=(start+finish)/2,state=renderer.renderAt(t),reference=referenceTimeAt(project.alignment.time_map,t);
  if(coverage&&(t<coverage.start_seconds||t>=coverage.end_seconds))continue;
  const quarter=projectedQuarter(live.projection,reference),frame=frameAt(live.frames,quarter),index=frame?live.frames.indexOf(frame):-1;
  const context={time:t,playingPage:state.page,browsedPage:state.page,systemIndex:frame?.system_index??0,x:state.highlight?.[0]??0,referenceSeconds:reference,referenceId:state.measureId};
  const view=model.view(context,{data:live,quarter,frame,previousFrame:index>0?live.frames[index-1]:null});
  for(const slot of data.dimensions||['harmony','orchestration','counterpoint','form']){
    const strings=hudTextFor(slot,view[slot],context),lines=[];
    for(const line of [strings.surface,strings.background].flatMap(s=>s.split('\n'))){
      if(forbidden.test(line)||line.includes('织体职责：候选')||/^\d+项研究 · /.test(line)){if(!omitted.some(e=>e.text===line))omitted.push({slot,text:line,reason:'web research-status line omitted from video'});continue;}
      lines.push(line.replace(/^模型候选 · /,'并列曲式读法 · ').replace('（精确及重叠边界见证据）',''));
    }
    emit(slot,start,finish,lines.join('\n'),view[slot].moduleEntries?.[0]?.id||'web HUD shared formatter');
  }
  const note=guide.annotations.find(n=>state.page>=n.start_pdf_page&&state.page<=n.end_pdf_page);
  if(note&&!data.dimensions)emit('guide',start,finish,`${note.title}\n${note.markdown}`,note.annotation_id);
}
fs.writeFileSync(output,JSON.stringify({events,omitted},null,2));
