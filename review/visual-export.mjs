import {createHarmonicFlow} from './harmonic-flow.mjs';
import {createOrchestrationActivity} from './orchestration-activity.mjs';
export function createVisualExport(flow,activity,config){
  const data={...flow,parts:activity.parts,flow_groups:activity.flow_groups,
    percussion:activity.events.filter(e=>e.kind==='unpitched')};
  const models={flow:createHarmonicFlow(data),orchestration:createOrchestrationActivity(activity)};
  return {at(time){
    const frame={time,width:config.width,height:config.height,commands:[],state:{}};
    if(activity.coverage&&!activity.coverage.segments.some(s=>s.start_seconds<=time&&time<s.end_seconds))return frame;
    for(const [name,box] of Object.entries(config.panels)){
      const value=models[name].frame(time,box),dx=box.x-config.overlay_x,dy=box.y-config.overlay_y;
      frame.state[name]=Object.fromEntries(Object.entries(value).filter(([k])=>!['commands','width','height','time'].includes(k)));
      for(const c of value.commands)frame.commands.push({...c,x:c.x+dx,y:c.y+dy,...(c.x2===undefined?{}:{x2:c.x2+dx,y2:c.y2+dy})});
    }return frame;
  }};
}
