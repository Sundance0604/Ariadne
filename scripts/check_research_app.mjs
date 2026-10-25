// Actual modules + local HTTP, using the existing in-memory DOM harness.
// This is separate from the real-browser checks documented in the pilot report.
import './check_mahler4_app.mjs';
import assert from 'node:assert/strict';
const $=id=>document.getElementById(id);
async function ready(test){for(let i=0;i<200;i++){if(test())return;await new Promise(r=>setTimeout(r,10));}throw Error('Research did not load');}
$('track').value='ravel-left-hand';await $('track').onchange();
await ready(()=>$('essay-select').children.length===2);
$('tab-research').onclick();$('essay-body').scrollTop=240;
const first=$('essay-body').children[0];
$('jump').value='32';$('go').onclick();
assert.equal($('essay-body').children[0],first);assert.equal($('essay-body').scrollTop,240);
assert.ok($('structural-hud').children[1].children[1].children[0].textContent.includes('华彩'));
$('jump').value='126';$('go').onclick();$('pagenext').onclick();
assert.match($('hud-position').textContent,/播放位置.*33.*浏览页.*34/);
$('essay-follow').checked=true;$('essay-follow').onchange();
$('jump').value='480';$('go').onclick();
assert.match($('essay-body').children[0].textContent,/同一架钢琴/);
$('essay-follow').checked=false;$('jump').value='1';$('go').onclick();
assert.match($('essay-body').children[0].textContent,/同一架钢琴/);
$('essay-select').value='ravel-tonal-emergence';$('essay-select').onchange();
const time=$('audio').currentTime;
const anchors=$('essay-body').children.filter(n=>n.tagName==='BUTTON');
anchors[1].onclick();assert.equal($('audio').currentTime,time);assert.match($('pagelabel').textContent,/第 10 /);
anchors[2].onclick();assert.equal($('audio').currentTime,time);assert.match($('pagelabel').textContent,/第 15 /);
for(const track of ['lark-ascending','mahler-4']){
  $('track').value=track;await $('track').onchange();await ready(()=>$('research-state').textContent.includes('暂无'));
  assert.equal($('essay-body').children.length,0);
}
console.log(JSON.stringify({research_module_integration:'passed',persistent_article:'passed',independent_hud:'passed',
  optional_follow:'passed',page_only_navigation_without_audio_seek:'passed',legacy_tracks:'passed',
  method:'in-memory DOM with actual modules and local HTTP; not browser playback QA'}));
