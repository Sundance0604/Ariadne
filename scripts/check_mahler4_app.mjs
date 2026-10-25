// Optional local module integration check. Start Python on port 8766 first.
// Uses an in-memory DOM; numbering writes use a mock response and never edit the real work.
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
let documentModel;
class Element extends EventTarget{
  constructor(tag='div',id=''){super();this.tagName=tag.toUpperCase();this.children=[];this.attributes={};this.style={setProperty(k,v){this[k]=v;}};this.dataset={};this.hidden=false;this.checked=false;this.disabled=false;this.value='';this._text='';this.scrollTop=0;this.scrollLeft=0;this.parentElement=null;this.classList={add(){},remove(){},toggle(){}};this.id=id;}
  set id(v){this._id=v;if(v&&documentModel)documentModel.nodes.set(v,this);}
  get id(){return this._id;}
  get textContent(){return this._text;}
  set textContent(v){this._text=String(v);}
  append(...items){for(const item of items){this.children.push(item);if(item&&typeof item==='object')item.parentElement=this;if(this.tagName==='SELECT'&&!this.value)this.value=item.value;}}
  replaceChildren(...items){this.children=[];this.value=this.tagName==='SELECT'?'':this.value;this.append(...items);}
  setAttribute(k,v){this.attributes[k]=String(v);}
  getAttribute(k){return this.attributes[k]??null;}
  removeAttribute(k){delete this.attributes[k];}
  getBoundingClientRect(){return {top:0,left:0,right:800,bottom:600,width:800,height:600};}
  querySelectorAll(){return [];}
  closest(selector){if(selector==='label')return {firstChild:{textContent:''}};if(selector==='.analysis-content')return documentModel.classes.get('.analysis-content');return this.parentElement;}
  click(){return this.onclick?.();}
  focus(){}
}
class Media extends Element{
  constructor(tag,id){super(tag,id);this._time=0;this.paused=true;this.ended=false;this.muted=false;this.volume=1;this.playbackRate=1;this.duration=3785.27;}
  set currentTime(t){this._time=t;for(const name of ['seeking','timeupdate','seeked'])this.dispatchEvent(new Event(name));}
  get currentTime(){return this._time;}
  set src(s){this.attributes.src=s;}
  get src(){return this.attributes.src;}
  load(){if(this.src)queueMicrotask(()=>this.dispatchEvent(new Event('loadedmetadata')));}
  async play(){this.paused=false;this.dispatchEvent(new Event('play'));}
  pause(){if(!this.paused){this.paused=true;this.dispatchEvent(new Event('pause'));}}
}
documentModel={nodes:new Map(),classes:new Map(),createElement:t=>new Element(t),createElementNS:(_ns,t)=>new Element(t),createTextNode:t=>({textContent:t}),createDocumentFragment:()=>new Element('fragment'),
  getElementById:id=>documentModel.nodes.get(id),querySelector:s=>documentModel.classes.get(s),querySelectorAll:s=>s==='[data-mode]'?modes:s==='[data-mobile-tab]'?mobile:[],documentElement:new Element(),body:new Element()};
const html=await fs.readFile('review/index.html','utf8');
for(const match of html.matchAll(/<([a-z0-9]+)[^>]*\bid="([^"]+)"[^>]*>/g)){
  const [,tag,id]=match;const element=['audio','video'].includes(tag)?new Media(tag,id):new Element(tag,id);
  element.hidden=/\bhidden\b/.test(match[0]);element.value=/\bvalue="([^"]+)"/.exec(match[0])?.[1]||'';
}
for(const cls of ['.toolbar','header','.transport','.score-scroll','.pagebuttons','.analysis-content'])documentModel.classes.set(cls,new Element());
const modes=['study','watch','focus'].map(mode=>{const e=new Element('button');e.dataset.mode=mode;return e;});
const mobile=['score','analysis','video'].map(mode=>{const e=new Element('button');e.dataset.mobileTab=mode;return e;});
globalThis.document=documentModel;globalThis.ResizeObserver=class{constructor(fn){this.fn=fn;}observe(){this.fn();}};
globalThis.window=new EventTarget();globalThis.location={href:'http://127.0.0.1:8766/?track=mahler-4'};
globalThis.history={replaceState(_a,_b,u){location.href=String(u);}};
const frames=new Map();let frame=0;globalThis.requestAnimationFrame=fn=>{frames.set(++frame,fn);return frame;};globalThis.cancelAnimationFrame=id=>frames.delete(id);
const realFetch=globalThis.fetch;globalThis.fetch=(url,options)=>realFetch(new URL(url,location.href),options);
const $=id=>documentModel.nodes.get(id);
$('speed').value='1';$('volume').value='.8';$('follow').checked=true;$('showplayhead').checked=true;$('show-measure-numbers').checked=true;
let source=await fs.readFile('review/app.mjs','utf8');
source=source.replace(/from '\/([^']+)'/g,(_,name)=>`from '${pathToFileURL(path.resolve('review',name)).href}'`);
await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
async function waitReady(expected){for(let n=0;n<200;n++){if($('work-title').textContent.includes(expected)&&!$('play').disabled&&$('guide-title').textContent!=='正在载入导聆')return;await new Promise(r=>setTimeout(r,10));}throw Error('App not ready: '+$('pagelabel').textContent+' '+$('toast').textContent);}
await waitReady('马勒');
assert.equal($('reference-count').textContent.startsWith('9 项'),true);
assert.equal($('measure-number-controls').hidden,false);
assert.equal($('measure-number-layer').children.length,4);
assert.ok($('measure-number-layer').children[0].getAttribute('aria-label').includes('候选小节 1'));
const realProject=await (await fetch('/api/project?track=mahler-4')).json();
assert.equal(realProject.score_measures.measures.length,1253);
$('measure-jump-movement').value='2';$('measure-jump-number').value='25';$('measure-jump-go').onclick();
const target=realProject.score_measures.measures.find(m=>m.movement===2&&m.score_measure_number===25);
assert.ok($('pagelabel').textContent.includes(`第 ${target.page_number} /`));
assert.ok(!$('measure-selection').hidden);
assert.equal(Number($('measure-number-value').value),25);
$('show-measure-numbers').checked=false;$('show-measure-numbers').onchange();assert.equal($('measure-number-layer').hidden,true);
$('show-measure-numbers').checked=true;$('show-measure-numbers').onchange();assert.equal($('measure-number-layer').hidden,false);
const lament=realProject.score_measures.measures.find(m=>m.page_number===80&&m.rect_pt[0]>=423);
$('measure-jump-movement').value='3';$('measure-jump-number').value=String(lament.score_measure_number);$('measure-jump-go').onclick();
assert.match($('guide-title').textContent,/哀诉/,'numbered jump selects the paragraph within the same page');
$('movement-chapters').children[0].onclick();
const label=$('measure-number-layer').children[2];label.onclick();
assert.equal(Number($('measure-number-value').value),3);
assert.ok($('location').textContent.includes('小节 ≈3'));
const fetchBeforeSave=globalThis.fetch;let saveRequest;
globalThis.fetch=async(url,options)=>{
  if(String(url).startsWith('/api/score-measure-number')){
    saveRequest=JSON.parse(options.body);const updated=structuredClone(realProject.score_measures);
    let after=false;
    for(const measure of updated.measures){
      if(measure.region_id===saveRequest.region_id){after=true;measure.numbering_status='corrected';}
      if(after&&measure.movement===1)measure.score_measure_number+=27;
    }
    return new Response(JSON.stringify({saved:true,score_measures:updated}),{status:200});
  }
  return fetchBeforeSave(url,options);
};
$('measure-number-value').value='30';$('measure-count-span').value='1';
$('measure-number-reason').value='UI fixture only';$('measure-number-confirm').checked=true;
await $('measure-number-save').onclick();
assert.equal(saveRequest.start_number,30);assert.equal(saveRequest.geometry_sha256,realProject.score_measures.geometry_sha256);
assert.ok($('measure-number-state').textContent.includes('已保存'));
assert.ok($('measure-number-layer').children[2].getAttribute('aria-label').includes('已校正小节 30'));
assert.ok($('measure-number-layer').children[3].getAttribute('aria-label').includes('候选小节 31'));
globalThis.fetch=fetchBeforeSave;
$('track').value='ravel-left-hand';await $('track').onchange();
assert.equal($('measure-number-controls').hidden,true);assert.equal($('measure-number-layer').children.length,0);
$('track').value='mahler-4';await $('track').onchange();await waitReady('马勒');
assert.equal($('movement-chapters').hidden,false);
assert.equal($('movement-chapters').children.length,4);
for(let i=0;i<4;i++){
  $('movement-chapters').children[i].onclick();
  assert.ok($('pagelabel').textContent.includes(`第 ${[5,49,78,102][i]} /`));
  assert.equal($('movement-chapters').children[i].getAttribute('aria-current'),'true');
}
const payload=await (await fetch('/api/analysis?track=mahler-4')).json();
for(const note of payload.annotations){
  $('video').currentTime=note.start_seconds+.3;
  assert.equal($('guide-section').value,note.annotation_id,`segment start: ${note.title}`);
}
const paragraphChecks=[];
for(const page of [5,80,112,115]){
  const notes=payload.annotations.filter(n=>n.start_pdf_page===page);
  for(const note of notes){
    $('video').currentTime=note.start_seconds+.3;
    assert.equal($('guide-section').value,note.annotation_id,`automatic paragraph on ${page}: ${note.title}`);
    paragraphChecks.push(note.title);
  }
}
$('movement-chapters').children[0].onclick();
for(let n=0;n<4;n++)$('pagenext').onclick();
assert.ok($('pagelabel').textContent.includes('第 9 /'));
assert.match($('guide-title').textContent,/宽广/);
$('video').currentTime+=.1;
assert.match($('guide-title').textContent,/宽广/,'manual page reading survives a time update');
const mainTheme=payload.annotations[1];$('guide-section').value=mainTheme.annotation_id;$('guide-section').onchange();
assert.equal($('guide-title').textContent,mainTheme.title);
assert.ok(Math.abs($('video').currentTime-mainTheme.start_seconds)<.01);
assert.ok($('pagelabel').textContent.includes('第 5 /'));
const interlude=payload.annotations.find(n=>n.start_pdf_page===115&&n.score_start[2]===0);
$('guide-section').value=interlude.annotation_id;$('guide-section').onchange();
$('video').currentTime=interlude.end_seconds+.3;
assert.match($('guide-title').textContent,/花园/,'selected paragraph releases when playback reaches the next paragraph');
const checks=[];
for(const index of [1,20,356,740,1065,1244]){
  $('jump').value=String(index);$('go').onclick();
  for(const fn of [...frames.values()]){frames.clear();fn();}
  assert.equal($('highlight').hidden,false);assert.equal($('playhead').hidden,false);
  assert.ok(!String($('playhead').style.left).includes('NaN'));
  checks.push({index,page:$('pagelabel').textContent,region:$('current').textContent,left:$('playhead').style.left,guide:$('guide-title').textContent});
}
$('stable-regions').checked=true;$('stable-regions').onchange();
$('jump').value='1';$('go').onclick();assert.equal($('highlight').hidden,true);
$('stable-regions').checked=false;$('stable-regions').onchange();assert.equal($('highlight').hidden,false);
for(const track of ['ravel-left-hand','lark-ascending']){$('track').value=track;await $('track').onchange();assert.equal($('video-panel').hidden,true);assert.equal($('video').getAttribute('src'),null);assert.equal($('movement-chapters').hidden,true);}
$('track').value='mahler-4';await $('track').onchange();assert.equal($('video-panel').hidden,false);
await waitReady('马勒');
console.log(JSON.stringify({kind:'in-memory DOM module integration, not a browser playback test',checks,paragraphChecks,segment_start_checks:'38 passed',movement_jumps:'4 passed',manual_page_reading:'passed',old_tracks:'passed',stable_only_filter:'passed',number_overlay:'passed',number_jump:'passed',number_save_ui:'mock response passed; real writes tested in isolated Python fixture',reference_count:$('reference-count').textContent},null,2));
