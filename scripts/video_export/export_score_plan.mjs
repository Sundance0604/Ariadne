import fs from 'node:fs';
import {createExportRenderer} from '../../review/video-export.mjs';
const [input,output]=process.argv.slice(2);
if(!input||!output)throw Error('Usage: node scripts/video_export/export_score_plan.mjs input.json output.json');
const data=JSON.parse(fs.readFileSync(input,'utf8')),renderer=createExportRenderer(data);
fs.writeFileSync(output,JSON.stringify(data.sample_times?{states:data.sample_times.map(t=>renderer.renderAt(t))}:renderer.plan()));
