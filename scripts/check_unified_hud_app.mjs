// Actual application modules and HTTP. DOM, media clock, and layout are simulated.
import './check_ravel_video_app.mjs';
import assert from 'node:assert/strict';
const $=id=>document.getElementById(id);
const text=n=>(n?.textContent||'')+' '+(n?.children||[]).map(text).join(' ');
const find=(root,predicate)=>predicate(root)?root:(root?.children||[]).map(n=>find(n,predicate)).find(Boolean);
const cards=$('structural-hud').children;
assert.equal(cards.length,4);assert.equal(document.getElementById('musicxml-live'),undefined);
const project=await(await fetch('/api/project?track=ravel-left-hand-video')).json();
const live=await(await fetch('/api/musicxml-live?track=ravel-left-hand-video')).json();
function videoTime(q){
  const tick=q*live.projection.ppq;
  const clock=live.projection.reference_clock.filter(c=>c.tick<=tick).at(-1);
  const seconds=clock.midi_seconds+(tick-clock.tick)*clock.seconds_per_tick;
  const map=project.alignment.time_map,i=map.findIndex(p=>p.midi_seconds>=seconds);
  if(i===0)return map[0].audio_seconds;
  const a=map[i-1],b=map[i];return a.audio_seconds+(seconds-a.midi_seconds)/(b.midi_seconds-a.midi_seconds)*(b.audio_seconds-a.audio_seconds);
}
$('tab-research').onclick();const article=$('essay-body').children[0];$('essay-body').scrollTop=213;
const selected=$('essay-select').value,title=article.textContent;
const checks=[];
for(const [id,q,pattern] of [['m11',31.01,/E1/],['m58',1321/8+.01,/开放五度/],['m63',751/4+.01,/D大三和弦/],
  ['m64-A3',188.01,/A3/],['m64-A1',188.76,/A1/],['m64-D1',189.01,/D1/],
  ['m520-before',1517.01,/4个活跃分部/],['m520-after',1517.76,/5个活跃分部/]]){
  $('video').currentTime=videoTime(q);
  assert.match(text(cards[id.startsWith('m520')?1:0]),pattern);
  assert.equal($('essay-body').children[0],article);assert.equal($('essay-body').scrollTop,213);
  checks.push({id,video_seconds:$('video').currentTime,position:$('hud-position').textContent});
}
$('video').currentTime=videoTime(31.01);cards[0].children[1].onclick();
assert.equal($('tab-evidence').getAttribute('aria-selected'),'true');
assert.match(text($('hud-detail')),/全体最低音：E1.*所选层最低音：D2/);
assert.match(text($('hud-detail')),/G小七和弦/);
const oldTime=$('video').currentTime;
await $('hud-detail').children.find(n=>n.tagName==='BUTTON'&&n.textContent.startsWith('查看本时点')).onclick();
const reader=$('musicxml-reader');assert.equal(reader.open,true);
assert.match(text(reader),/xml-h-000197/);
const note=find(reader,n=>n.tagName==='BUTTON'&&n.textContent==='P9-xml-m0011-n0001');assert.ok(note);note.onclick();
assert.match(text(reader),/源音符 P9-xml-m0011-n0001/);assert.equal($('video').currentTime,oldTime);
// The note reader is independent: m34 opens PDF11 without seeking or replacing essays.
reader.children.find(n=>n.tagName==='SELECT').value='xml-m0034';
await reader.children.find(n=>n.tagName==='BUTTON').onclick();
reader.children.at(-1).children.find(n=>n.tagName==='BUTTON').onclick();
assert.match($('pagelabel').textContent,/第 11 /);assert.equal($('video').currentTime,oldTime);
assert.match($('hud-position').textContent,/m\.11/,'browsing m34 must not become the playing harmony');
$('evidence-return-score').onclick();assert.equal($('video').currentTime,oldTime);assert.equal($('follow').checked,true);
assert.match($('pagelabel').textContent,/第 3 /);
$('tab-research').onclick();assert.equal($('essay-select').value,selected);assert.equal(article.textContent,title);
assert.equal($('essay-body').children[0],article);assert.equal($('essay-body').scrollTop,213);
$('hud-toggle').open=false;assert.equal($('hud-toggle').open,false);$('hud-toggle').open=true;
for(const track of ['lark-ascending','mahler-4']){
  $('track').value=track;await $('track').onchange();
  assert.equal($('musicxml-reader').hidden,true);assert.doesNotMatch(text($('structural-hud')),/G小七|开放五度|5个活跃分部/);
}
console.log(JSON.stringify({unified_hud_integration:'passed',primary_cards:4,duplicate_live_panel:false,
  cases:checks,source_note_navigation:'passed',xml34_pdf11_without_seek:'passed',return_to_current_score:'passed',
  nonzero_article_scroll:213,track_reset:'passed',kind:'actual modules and HTTP; DOM/media simulated, not real browser layout or playback'}));
