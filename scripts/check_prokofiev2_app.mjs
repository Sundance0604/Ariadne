// Actual local HTTP and application modules with simulated DOM/media.
// This is wiring verification, not browser decoding or human listening.
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const base=process.env.ARIADNE_REVIEW_URL||'http://127.0.0.1:8765';
const seen=new Set();
async function graph(url){
  if(seen.has(url))return;seen.add(url);
  const response=await fetch(url);assert.equal(response.status,200,url);
  assert.match(response.headers.get('content-type'),/javascript/,url);
  const code=await response.text();
  for(const m of code.matchAll(/(?:from\s*|import\s*)['"]([^'"]+)['"]/g))
    if(m[1].startsWith('.')||m[1].startsWith('/'))await graph(new URL(m[1],url).href);
}
await graph(new URL('/app.mjs',base).href);
// Reuse only the already-tested DOM fixture initialization, before any Mahler
// assertions or mocked writes. All new checks are local and read-only.
const existing=await fs.readFile('scripts/check_mahler4_app.mjs','utf8');
let setup=existing.slice(0,existing.indexOf("await waitReady('马勒');"));
setup=setup.replace('/?track=mahler-4','/?track=prokofiev-piano-concerto-2')
  .replace("'http://127.0.0.1:8766'",JSON.stringify(base))
  .replace("await fs.readFile('review/app.mjs','utf8')","await (await fetch('/app.mjs')).text()");
const checks=String.raw`
await waitReady('普罗');
async function ready(test){const until=Date.now()+20000;while(Date.now()<until){if(test())return;await new Promise(r=>setTimeout(r,10));}throw Error('Prokofiev research did not load: '+$('research-state').textContent);}
await ready(()=>$('essay-select').children.length===4&&$('guide-section').children.length===38);
const project=await(await fetch('/api/project?track=prokofiev-piano-concerto-2')).json();
$('video').duration=project.alignment.audio.duration_seconds;
assert.equal($('video-panel').hidden,false);assert.match($('video').src,/video\?track=prokofiev-piano-concerto-2/);
assert.equal($('audio').muted,true);assert.equal($('highlight').hidden,true);
assert.equal($('movement-chapters').children.length,4);
const cardText=i=>$('structural-hud').children[i].children[1].children.map(n=>n.textContent).join('\n');
const harmony=()=>cardText(0);
const orchestration=()=>cardText(1);
$('jump').value='13';$('go').onclick();
await ready(()=>orchestration().includes('个活跃分部'));
assert.match(harmony(),/当前：/);assert.match(orchestration(),/Piano/);
$('video').currentTime=131.4;
assert.match(orchestration(),/Flauti/);
$('jump').value='6';$('go').onclick();
assert.match(orchestration(),/钢琴XML时值待核/);
assert.match(harmony(),/已知部分音集/);
const evidence=await(await fetch('/api/musicxml-evidence?track=prokofiev-piano-concerto-2&measure_id=xml-m0023')).json();
assert.ok(evidence.events.some(e=>e.part_id==='P1'&&e.concert_pitch));
const chapters=[];
for(let i=0;i<4;i++){
  $('movement-chapters').children[i].onclick();
  const first=project.alignment.measures.find(m=>m.movement===i+1);
  assert.ok(Math.abs($('video').currentTime-first.start_seconds)<.001);
  assert.equal($('highlight').hidden,false);
  assert.match($('pagelabel').textContent,new RegExp('第 '+[1,38,70,109][i]+' /'));
  chapters.push({movement:i+1,time:$('video').currentTime,page:$('pagelabel').textContent});
}
$('jump').value='739';$('go').onclick();
assert.match($('pagelabel').textContent,/第 140 /);
assert.equal($('highlight').hidden,false);assert.equal($('playhead').hidden,true);
assert.match($('playheadlabel').textContent,/系统区域高亮/);
for(const t of [710,865,1275,2300]){
  $('video').currentTime=t;assert.equal($('highlight').hidden,true);assert.equal($('playhead').hidden,true);
  assert.doesNotMatch(orchestration(),/个活跃分部/);
}
$('jump').value='629';$('go').onclick();assert.match($('guide-title').textContent,/摇篮曲/);
$('tab-research').onclick();$('essay-body').scrollTop=185;const article=$('essay-body').children[0];
const before=$('video').currentTime;
await $('play').onclick();assert.equal($('video').paused,false);assert.equal($('audio').paused,true);
$('video').currentTime=before+.3;assert.equal($('essay-body').children[0],article);assert.equal($('essay-body').scrollTop,185);
await $('play').onclick();assert.equal($('video').paused,true);
$('speed').value='.8';$('speed').onchange();assert.equal($('video').playbackRate,.8);
const time=$('video').currentTime;$('pagenext').onclick();assert.equal($('video').currentTime,time);
$('track').value='ravel-left-hand';await $('track').onchange();await waitReady('拉威尔');
assert.equal($('video-panel').hidden,true);assert.equal($('video').getAttribute('src'),null);
$('track').value='prokofiev-piano-concerto-2';await $('track').onchange();await waitReady('普罗');
await ready(()=>$('essay-select').children.length===4);
console.log(JSON.stringify({prokofiev2_integration:'passed',chapters,guide_sections:38,essays:4,
  shared_cadenza_has_no_moving_line:true,pauses_and_encore_have_no_highlight:true,
  article_scroll_retained:true,video_transport_simulated:true,old_audio_track_switch:true,
  live_notes_and_instruments:true,uncertain_piano_activity_explicit:true,
  method:'actual HTTP and modules with simulated DOM/media; not real browser decoding or listening'}));
`;
try{await import('data:text/javascript;base64,'+Buffer.from(setup+'\n'+checks).toString('base64'));}
catch(error){console.error(JSON.stringify({message:error.message,actual:error.actual,expected:String(error.expected)}));process.exit(1);}
console.log(JSON.stringify({http_module_graph:'passed',modules:seen.size}));
