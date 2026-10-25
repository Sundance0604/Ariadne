import assert from 'node:assert/strict';
import {test} from 'node:test';
import {createHermeneutics} from '../review/hermeneutics.mjs';
import {createResearchPanel} from '../review/research.mjs';
import {makeDOM,fixture} from './research-dom.mjs';

test('long reading and scroll stay fixed across pages, seek and pause/rate context',()=>{
  const $=makeDOM(),navigations=[];
  const essays=createHermeneutics({onNavigate:(...args)=>navigations.push(args)});
  essays.reset();essays.load(fixture());$('essay-body').scrollTop=123;
  const original=$('essay-body').replacements;
  for(const ctx of [{playingPage:5,time:50},{playingPage:8,time:15,rate:1.2},{playingPage:3,paused:true}])essays.update(ctx);
  assert.equal($('essay-select').value,'essay-a');assert.equal($('essay-body').scrollTop,123);
  assert.equal($('essay-body').replacements,original);
  const anchors=$('essay-body').children.filter(n=>n.tagName==='button');
  anchors[0].onclick();anchors[2].onclick();assert.equal(navigations[0][0].pdf_page_start,1);assert.equal(navigations[1][0].pdf_page_start,8);
  $('essay-follow').checked=true;essays.update({playingPage:5});assert.equal($('essay-select').value,'essay-b');
  essays.update({playingPage:3});assert.equal($('essay-select').value,'essay-a');assert.equal($('essay-body').scrollTop,123);
  essays.reset();assert.equal($('essay-body').textContent,'');assert.equal($('essay-follow').checked,false);
});
test('late old-track research cannot replace new-track empty state; errors stay local',async()=>{
  const $=makeDOM();const oldFetch=globalThis.fetch;let resolveOld;
  globalThis.fetch=url=>String(url).includes('old')?new Promise(resolve=>resolveOld=resolve):Promise.resolve(new Response(JSON.stringify({available:false,events:[],essays:[],sources:[]})));
  try{
    const panel=createResearchPanel({onNavigate(){},onSelectTab(){},getRegions:()=>[]});
    const old=panel.load('old','hash');await panel.load('new','hash');
    resolveOld(new Response(JSON.stringify({...fixture(),edition:{pdf_sha256:'hash'}})));await old;
    assert.match($('research-state').textContent,/暂无/);assert.doesNotMatch($('essay-body').textContent,/long prose A/);
    globalThis.fetch=()=>Promise.resolve(new Response(JSON.stringify({error:'PDF mismatch'}),{status:422}));
    await panel.load('broken','hash');assert.match($('research-state').textContent,/PDF mismatch/);
  }finally{globalThis.fetch=oldFetch;}
});
