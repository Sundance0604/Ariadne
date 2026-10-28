// Actual HTTP/modules, simulated media and DOM. Browser checks are separate.
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const base=process.env.ARIADNE_REVIEW_URL||'http://127.0.0.1:8765';
const seen=new Set();
async function graph(url){
  if(seen.has(url))return;seen.add(url);
  const r=await fetch(url);assert.equal(r.status,200,url);
  assert.match(r.headers.get('content-type'),/javascript/,url);
  for(const m of (await r.text()).matchAll(/(?:from\s*|import\s*)['"]([^'"]+)['"]/g))
    if(m[1].startsWith('.')||m[1].startsWith('/'))await graph(new URL(m[1],url).href);
}
await graph(new URL('/app.mjs',base).href);
const fixture=await fs.readFile('scripts/check_mahler4_app.mjs','utf8');
const setup=fixture.slice(0,fixture.indexOf("await waitReady('马勒');"))
 .replace('/?track=mahler-4','/?track=dvorak-american')
 .replace("'http://127.0.0.1:8766'",JSON.stringify(base))
 .replace("await fs.readFile('review/app.mjs','utf8')","await (await fetch('/app.mjs')).text()");
const checks=String.raw`
await waitReady('德沃夏克');
async function ready(test){const until=Date.now()+20000;while(Date.now()<until){if(test())return;await new Promise(r=>setTimeout(r,10));}throw Error('American data did not load');}
await ready(()=>$('essay-select').children.length===4&&$('guide-section').children.length===49);
const project=await(await fetch('/api/project?track=dvorak-american')).json();
$('video').duration=project.alignment.audio.duration_seconds;
assert.equal(project.alignment.measures.length,962);
const cardText=i=>$('structural-hud').children[i].children[1].children.map(n=>n.textContent).join('\n');
$('jump').value='3';$('go').onclick();
await ready(()=>cardText(1).includes('4个活跃分部'));
assert.match(cardText(0),/震音交替音集/);assert.match(cardText(0),/本段谱面研究/);
assert.match(cardText(1),/第一小提琴.*第二小提琴.*中提琴.*大提琴/);
assert.doesNotMatch(cardText(1),/钢琴/);
const chapters=[];
for(let i=0;i<4;i++){
 $('movement-chapters').children[i].onclick();
 const m=project.alignment.measures.find(m=>m.movement===i+1);
 assert.ok(Math.abs($('video').currentTime-m.start_seconds)<.001);
 assert.equal($('highlight').hidden,false);
 assert.match($('pagelabel').textContent,new RegExp('第 '+[1,12,18,24][i]+' /'));
 chapters.push({movement:i+1,time:$('video').currentTime,page:$('pagelabel').textContent});
}
for(const [visit,page] of [[64,1],[533,18]]){
 $('jump').value=String(visit);$('go').onclick();
 assert.match($('guide-title').textContent,/再次经过/);
 assert.match($('pagelabel').textContent,new RegExp('第 '+page+' /'));
 const evidence=await(await fetch('/api/musicxml-evidence?track=dvorak-american&measure_id=visit-'+String(visit).padStart(4,'0'))).json();
 assert.equal(evidence.measure.visit,2);assert.ok(evidence.events.length>0);
}
for(const t of [600,1080,1360,1695]){
 $('video').currentTime=t;assert.equal($('highlight').hidden,true);assert.equal($('playhead').hidden,true);
 assert.doesNotMatch(cardText(1),/个活跃分部/);
}
$('jump').value='250';$('go').onclick();$('tab-research').onclick();
$('essay-body').scrollTop=185;const article=$('essay-body').children[0],time=$('video').currentTime;
await $('play').onclick();assert.equal($('video').paused,false);
$('video').currentTime=time+.3;assert.equal($('essay-body').children[0],article);assert.equal($('essay-body').scrollTop,185);
await $('play').onclick();assert.equal($('video').paused,true);
$('track').value='ravel-left-hand';await $('track').onchange();await waitReady('拉威尔');
assert.equal($('video-panel').hidden,true);assert.equal($('video').getAttribute('src'),null);
console.log(JSON.stringify({american_integration:'passed',chapters,visits:962,guides:49,essays:4,
 repeats:true,pauses_clear:true,scroll_retained:true,cross_track_clear:true,transport:'simulated'}));
`;
try{await import('data:text/javascript;base64,'+Buffer.from(setup+'\n'+checks).toString('base64'));}
catch(e){console.error({message:e.message,actual:e.actual,expected:String(e.expected)});process.exit(1);}
console.log(JSON.stringify({http_module_graph:'passed',modules:seen.size}));
