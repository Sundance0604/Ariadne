import assert from 'node:assert/strict';
import {test} from 'node:test';
import {PlaybackController,mapTime,validateAnchors} from '../review/playback.mjs';

class Media extends EventTarget{
  constructor(){super();this.currentTime=0;this.duration=120;this.paused=true;this.ended=false;this.muted=false;this.volume=1;this.playbackRate=1;this.attributes={};}
  set src(value){this.attributes.src=value;}
  getAttribute(key){return this.attributes[key];}
  removeAttribute(key){delete this.attributes[key];}
  load(){}
  async play(){this.paused=false;this.dispatchEvent(new Event('play'));}
  pause(){const was=this.paused;this.paused=true;if(!was)this.dispatchEvent(new Event('pause'));}
}
const anchors=[{masterTime:0,videoTime:5},{masterTime:50,videoTime:55},{masterTime:100,videoTime:110}];
function setup(){const a=new Media(),v=new Media(),messages=[];return {a,v,messages,p:new PlaybackController(a,v,m=>messages.push(m))};}

test('piecewise mapping supports offset, drift, inversion and bounded validity',()=>{
  validateAnchors(anchors,100,110);
  assert.equal(mapTime(anchors,25),30);assert.equal(mapTime(anchors,75),82.5);
  assert.equal(mapTime(anchors,82.5,true),75);assert.equal(mapTime(anchors,-1),null);assert.equal(mapTime(anchors,101),null);
  for(const bad of [[],[{masterTime:0,videoTime:0},{masterTime:0,videoTime:1}],
      [{masterTime:0,videoTime:0},{masterTime:1,videoTime:NaN}]])assert.throws(()=>validateAnchors(bad));
});
test('video-only uses video clock and leaves audio paused and muted',async()=>{
  const {a,v,p}=setup();p.configure({masterClock:'video',video:{}},{video:'/video'},120);
  await p.play();p.currentTime=35;p.playbackRate=.8;
  assert.equal(p.currentTime,35);assert.equal(v.currentTime,35);assert.equal(v.paused,false);
  assert.equal(a.paused,true);assert.equal(a.muted,true);assert.equal(v.muted,false);assert.equal(v.playbackRate,.8);
  p.setLoop(10,20);v.currentTime=21;p.tick();assert.equal(v.currentTime,10);p.pause();assert.equal(v.paused,true);
});
test('audio-only stays compatible; switching project stops the old source',async()=>{
  const {a,v,p}=setup();p.configure(null,{audio:'/audio'},120);await p.play();assert.equal(a.paused,false);
  p.configure({masterClock:'video',video:{}},{video:'/video'},120);assert.equal(a.paused,true);assert.equal(v.paused,true);
  assert.equal(a.getAttribute('src'),undefined);assert.equal(p.loop,null);
});
test('dual playback has exactly one audible source and switches through the mapping',async()=>{
  const {a,v,p}=setup();p.configure({masterClock:'audio',video:{duration_seconds:120},anchors,matchStatus:'manual_reviewed'},{audio:'/audio',video:'/video'},100);
  p.currentTime=25;await p.play();await Promise.resolve();
  assert.equal(a.muted,false);assert.equal(v.muted,true);assert.equal(v.currentTime,30);
  await p.selectSource('video');assert.equal(a.paused,true);assert.equal(a.muted,true);assert.equal(v.muted,false);
  assert.equal(p.currentTime,25);p.currentTime=75;assert.equal(v.currentTime,82.5);
  await p.selectSource('audio');assert.equal(a.currentTime,75);assert.equal(v.muted,true);
});
test('unknown performances cannot start a slave or switch sources',async()=>{
  const {v,p}=setup();p.configure({masterClock:'audio',video:{duration_seconds:120},anchors,matchStatus:'different_performance'},{audio:'/audio',video:'/video'},100);
  await p.play();assert.equal(v.paused,true);assert.equal(await p.selectSource('video'),false);
});
test('large drift pauses the slave instead of repeated seeks; gaps are not extrapolated',async()=>{
  const {v,p,messages}=setup();p.configure({masterClock:'audio',video:{duration_seconds:120},anchors,matchStatus:'manual_reviewed'},{audio:'/audio',video:'/video'},120);
  p.currentTime=25;await p.play();v.currentTime=10;p.tick();assert.equal(v.paused,true);assert.equal(v.currentTime,10);
  assert.ok(messages.at(-1).includes('超过 2 秒'));p.currentTime=110;p.tick();assert.equal(v.paused,true);
});
