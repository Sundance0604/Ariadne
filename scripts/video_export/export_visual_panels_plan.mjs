// Shared drawing commands, sampled on the original performance clock.
import fs from 'node:fs';
import {createHarmonicFlow} from '../../review/harmonic-flow.mjs';
import {createOrchestrationActivity} from '../../review/orchestration-activity.mjs';
const [source,activityPath,configPath,output]=process.argv.slice(2),
  data=JSON.parse(fs.readFileSync(source,'utf8')),activity=JSON.parse(fs.readFileSync(activityPath,'utf8')),
  config=JSON.parse(fs.readFileSync(configPath,'utf8'));
const {start,duration,fps,width,height,panels,overlay_x,overlay_y}=config;
data.parts=activity.parts;data.flow_groups=activity.flow_groups;data.percussion=activity.events.filter(e=>e.kind==='unpitched');
data.notes=data.notes.filter(n=>n.end_seconds>start-2&&n.start_seconds<start+duration+4);
const renderers={flow:createHarmonicFlow(data),orchestration:createOrchestrationActivity(activity)},handle=fs.openSync(output,'wx');
try{for(let index=0;index<Math.round(duration*fps);index++){
  const time=start+index/fps,commands=[],state={};
  for(const [name,box] of Object.entries(panels)){
    const frame=renderers[name].frame(time,box);state[name]=Object.fromEntries(Object.entries(frame).filter(([k])=>!['commands','width','height','time'].includes(k)));
    const dx=box.x-overlay_x,dy=box.y-overlay_y;
    for(const c of frame.commands)commands.push({...c,x:c.x+dx,y:c.y+dy,...(c.x2===undefined?{}:{x2:c.x2+dx,y2:c.y2+dy})});
  }
  fs.writeSync(handle,JSON.stringify({time,width,height,commands,state})+'\n');
}}finally{fs.closeSync(handle);}
console.log(JSON.stringify({frames:Math.round(duration*fps),parts:activity.parts.length,events:activity.events.length,start,duration}));
