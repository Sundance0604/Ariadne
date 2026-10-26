// Reuse the exact recording projection and XML frames; no new score analysis.
import fs from 'node:fs';
import {referenceTimeAt} from '../../review/playhead.mjs';
import {projectedQuarter} from '../../review/musicxml-live.mjs';
import {quarter} from '../../review/score-analysis-model.mjs';

const [source,requests,output]=process.argv.slice(2);
const {project,live}=JSON.parse(fs.readFileSync(source,'utf8'));
const rows=JSON.parse(fs.readFileSync(requests,'utf8'));
const qAt=t=>projectedQuarter(live.projection,referenceTimeAt(project.alignment.time_map,t));
const results=[];
for(const row of rows){
  const start=qAt(Number(row.start)),end=qAt(Number(row.end)-1e-7);
  if(!Number.isFinite(start)||!Number.isFinite(end)||end<start)throw Error(`No reliable projection for ${row.id}`);
  // Recording interpolation can land a few ulps before an exact XML boundary.
  // Do not leak a previous attack into the next caption's pitch collection.
  const frames=live.frames.filter(f=>quarter(f.start_q)<=end-1e-8&&quarter(f.end_q)>start+1e-8);
  if(!frames.length)throw Error(`No XML frames for ${row.id}`);
  let text;
  const windows=[...new Set(frames.map(f=>f.harmony_window_id).filter(Boolean))].map(id=>live.windows[id]).filter(Boolean);
  if(row.slot==='harmony'){
    const pitches=[...new Set(windows.flatMap(w=>w.pitches||[]).map(p=>p.replace(/-?\d+$/,'')))];
    const bass=[];
    for(const w of windows){const n=w.bass?.name;if(n&&bass.at(-1)!==n)bass.push(n);}
    text=pitches.length?'片段音集：'+pitches.join('、'):'短暂休止';
    if(bass.length)text+='\n低音：'+bass.join(' → ');
  }else{
    const parts=[...new Set(frames.flatMap(f=>f.active_instruments).map(p=>p.label.replace(/分部\d+$/,'')))];
    text=parts.length?'片段中的乐器：'+parts.join('、'):'短暂休止';
  }
  results.push({index:row.index,id:row.id,text,xml_interval:[start,end],
                frame_ids:frames.map(f=>f.id),window_ids:windows.map(w=>w.id)});
}
fs.writeFileSync(output,JSON.stringify(results,null,2));
