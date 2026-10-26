// Actual modules + local HTTP, using the existing in-memory DOM harness.
// This is separate from the real-browser checks documented in the pilot report.
import './check_mahler4_app.mjs';
import assert from 'node:assert/strict';
const $=id=>document.getElementById(id);
async function ready(test){const deadline=Date.now()+20000;while(Date.now()<deadline){if(test())return;await new Promise(r=>setTimeout(r,10));}throw Error('Research did not load: '+$('research-state').textContent);}
$('track').value='ravel-left-hand';await $('track').onchange();
await ready(()=>$('essay-select').children.length===5&&$('hud-position').textContent.includes('m.1'));
$('tab-research').onclick();$('essay-body').scrollTop=240;
const first=$('essay-body').children[0];
const xmlReader=$('musicxml-reader');assert.equal(xmlReader.hidden,false);
const xmlSelect=xmlReader.children.find(n=>n.tagName==='SELECT');assert.equal(xmlSelect.children.length,535);
xmlSelect.value='xml-m0034';const xmlTime=$('audio').currentTime;
await xmlReader.children.find(n=>n.tagName==='BUTTON').onclick();
assert.match(xmlReader.children.find(n=>n.tagName==='P').textContent,/第34小节.*PDF第11页/);
const xmlBody=xmlReader.children.at(-1);xmlBody.children.find(n=>n.tagName==='BUTTON').onclick();
assert.equal($('audio').currentTime,xmlTime);assert.equal($('essay-body').children[0],first);
assert.equal($('essay-body').scrollTop,240);assert.match($('pagelabel').textContent,/第 11 /);
assert.equal($('follow').checked,false);$('follow').checked=true;$('follow').onchange();
$('jump').value='32';$('go').onclick();
assert.equal($('essay-body').children[0],first);assert.equal($('essay-body').scrollTop,240);
assert.match($('structural-hud').children[3].children[1].children[0].textContent,/引子|华彩/);
$('jump').value='126';$('go').onclick();$('pagenext').onclick();
assert.match($('hud-position').textContent,/当前.*33.*浏览页.*34/);
$('essay-follow').checked=true;$('essay-follow').onchange();
$('jump').value='480';$('go').onclick();
// The form essay legitimately spans both the Allegro and the later cadenza.
assert.match($('essay-body').children[0].textContent,/曲式功能/);
$('essay-follow').checked=false;$('jump').value='1';$('go').onclick();
assert.match($('essay-body').children[0].textContent,/曲式功能/);
$('structural-hud').children[0].children[1].onclick();
$('hud-detail').children.find(n=>n.tagName==='BUTTON'&&n.textContent.includes('持续低音上的四度骨架')).onclick();
const scoreDetail=node=>node.textContent+' '+(node.innerHTML||'')+' '+node.children.map(scoreDetail).join(' ');
assert.match(scoreDetail($('hud-detail')),/符号底稿/);assert.match(scoreDetail($('hud-detail')),/1\/6/);
assert.match(scoreDetail($('hud-detail')),/人工签核/);
$('essay-select').value='ravel-tonal-emergence';$('essay-select').onchange();
const time=$('audio').currentTime;
const anchors=$('essay-body').children.filter(n=>n.tagName==='BUTTON');
anchors[1].onclick();assert.equal($('audio').currentTime,time);assert.match($('pagelabel').textContent,/第 10 /);
anchors[2].onclick();assert.equal($('audio').currentTime,time);assert.match($('pagelabel').textContent,/第 15 /);
$('hud-auto-candidates').checked=true;$('hud-auto-candidates').onchange();
$('jump').value='61';$('go').onclick();
const harmony=$('structural-hud').children[0].children[1];
harmony.onclick();
$('hud-detail').children.find(n=>n.tagName==='BUTTON'&&n.textContent.startsWith('PDF/MIDI候选')).onclick();
const descendants=node=>node.textContent+' '+node.children.map(descendants).join(' ');
await ready(()=>descendants($('hud-detail')).includes('谱面观测与符号证据'));
assert.match(descendants($('hud-detail')),/PDF位置/);assert.match(descendants($('hud-detail')),/理论推导与关系/);
$('jump').value='55';$('go').onclick();$('audio').currentTime+=.25;
harmony.onclick();
$('hud-detail').children.find(n=>n.tagName==='BUTTON'&&n.textContent.startsWith('PDF/MIDI候选')).onclick();
await ready(()=>descendants($('hud-detail')).includes('Fm7'));
assert.match(descendants($('hud-detail')),/代理读谱抽查/);
assert.match(descendants($('hud-detail')),/上谱表.*休止/);
for(const track of ['lark-ascending','mahler-4']){
  $('track').value=track;await $('track').onchange();await ready(()=>$('research-state').textContent.includes('暂无'));
  assert.equal($('essay-body').children.length,0);
  assert.equal(xmlReader.hidden,true);
}
console.log(JSON.stringify({research_module_integration:'passed',persistent_article:'passed',independent_hud:'passed',
  optional_follow:'passed',page_only_navigation_without_audio_seek:'passed',legacy_tracks:'passed',musicxml_reader_all_measures:'passed',
  method:'in-memory DOM with actual modules and local HTTP; not browser playback QA'}));
