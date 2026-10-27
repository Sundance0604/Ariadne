// Export exact per-frame drawing commands; no browser timing or screen capture.
import fs from 'node:fs';
import {createHarmonicFlow} from '../../review/harmonic-flow.mjs';
const [source,configPath,output]=process.argv.slice(2);
const data=JSON.parse(fs.readFileSync(source,'utf8')),config=JSON.parse(fs.readFileSync(configPath,'utf8'));
const {start,duration,fps,width,height}=config;
data.notes=data.notes.filter(n=>n.end_seconds>start-2&&n.start_seconds<start+duration+4);
const flow=createHarmonicFlow(data),handle=fs.openSync(output,'wx');
try{for(let index=0;index<Math.round(duration*fps);index++){
  fs.writeSync(handle,JSON.stringify(flow.frame(start+index/fps,{width,height}))+'\n');
}}finally{fs.closeSync(handle);}
console.log(JSON.stringify({frames:Math.round(duration*fps),source_notes:data.notes.length,start,duration}));
