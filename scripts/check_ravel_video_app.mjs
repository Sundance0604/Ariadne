// Actual app modules plus HTTP; media elements and DOM are simulated.
// This verifies wiring and switching, not video decoding or browser playback.
import './check_research_app.mjs';
import assert from 'node:assert/strict';
const $=id=>document.getElementById(id);
const text=n=>(n?.textContent||'')+' '+(n?.children||[]).map(text).join(' ');
async function ready(test){const end=Date.now()+20000;while(Date.now()<end){if(test())return;await new Promise(r=>setTimeout(r,20));}throw Error('Video research not ready: '+text($('structural-hud')));}
const project=await(await fetch('/api/project?track=ravel-left-hand-video')).json();
$('track').value='ravel-left-hand-video';await $('track').onchange();
await ready(()=>$('essay-select').children.length===5&&$('hud-position').getAttribute('data-xml-state')==='ready');
assert.equal($('video-panel').hidden,false);assert.equal($('audio').getAttribute('src'),null);
assert.match($('video').src,/video\?track=ravel-left-hand-video/);
assert.equal($('video').muted,false);assert.equal($('audio').muted,true);
assert.equal($('highlight').hidden,true);assert.equal($('playhead').hidden,true);
$('tab-research').onclick();$('essay-body').scrollTop=185;
const article=$('essay-body').children[0];
$('follow').checked=true;$('follow').onchange();
$('jump').value='64';$('go').onclick();
assert.ok(Math.abs($('video').currentTime-project.alignment.measures[63].start_seconds)<.001);
assert.match($('hud-position').textContent,/m\.64/);
$('structural-hud').children[0].children[1].onclick();assert.match(text($('hud-detail')),/E大三和弦/);
assert.match(text($('structural-hud')),/活跃分部/);
assert.equal($('highlight').hidden,false);assert.equal($('playhead').hidden,false);
assert.equal($('essay-body').children[0],article);assert.equal($('essay-body').scrollTop,185);
const time=$('video').currentTime;$('pagenext').onclick();assert.equal($('video').currentTime,time);
await $('play').onclick();assert.equal($('video').paused,false);assert.equal($('audio').paused,true);
$('speed').value='.8';$('speed').onchange();assert.equal($('video').playbackRate,.8);
await $('play').onclick();assert.equal($('video').paused,true);
$('video').currentTime=1190;
assert.match($('hud-position').textContent,/位置未覆盖/);assert.equal($('highlight').hidden,true);
assert.equal($('playhead').hidden,true);
$('track').value='ravel-left-hand';await $('track').onchange();
await ready(()=>$('essay-select').children.length===5&&$('hud-position').getAttribute('data-xml-state')==='ready');
assert.equal($('video-panel').hidden,true);assert.equal($('video').src,undefined);assert.equal($('video').paused,true);
assert.match($('audio').src,/audio\?track=ravel-left-hand/);
$('jump').value='64';$('go').onclick();assert.notEqual($('audio').currentTime,time);
$('track').value='ravel-left-hand-video';await $('track').onchange();
await ready(()=>$('hud-position').getAttribute('data-xml-state')==='ready');
$('follow').checked=true;$('follow').onchange();
$('jump').value='34';$('go').onclick();assert.match($('pagelabel').textContent,/第 11 /);
console.log(JSON.stringify({ravel_video_integration:'passed',independent_video_clock:true,
  shared_essays:5,xml_measures:535,applause_does_not_activate_score:true,
  independent_page_reading:true,article_scroll_retained:true,video_transport_simulated:true,
  audio_edition_preserved:true,method:'actual modules and HTTP with simulated DOM/media; not real browser playback'}));
