import assert from 'node:assert/strict';
import fs from 'node:fs';
import {test} from 'node:test';
import {createScoreAnalysisModel} from '../review/score-analysis-model.mjs';
import {hudTextFor} from '../review/hud-text.mjs';
import {createStructuralHUD} from '../review/structural-hud.mjs';
import {makeDOM,fixture} from './research-dom.mjs';

const profile=JSON.parse(fs.readFileSync(new URL('../analysis/ravel-module-development.json',import.meta.url),'utf8'));
const snapshot=q=>({quarter:q,frame:{measure_id:'xml-m0067',page:16,active_instruments:[]},
  data:{hud_cases:{cases:[],contexts:[]},form:{sections:[],models:[]},windows:{},readings:{}}});

test('Ravel revisions preserve harmony/orchestration and distinguish structural from simultaneous relations',()=>{
  const model=createScoreAnalysisModel(),context={playingPage:16,browsedPage:16};
  model.load(fixture());const before=model.view(context,snapshot(199));
  model.load({...fixture(),module_profile:profile});const after=model.view(context,snapshot(199));
  for(const id of ['harmony','orchestration']){
    assert.deepEqual(after[id],before[id]);assert.equal(after.signatures[id],before.signatures[id]);
  }
  assert.equal(after.form.moduleEntries[0].id,'development-five-return');
  assert.equal(after.counterpoint.moduleEntries[0].id,'voices-five-doubling');
  assert.match(hudTextFor('form',after.form,context).background,/两个八度/);
  assert.match(hudTextFor('counterpoint',after.counterpoint,context).background,/一条线/);
  assert.equal(after.form.moduleEntries[0].relation_ids[0],after.counterpoint.moduleEntries[0].relation_ids[0]);
  assert.equal(after.moduleRelations[0].theme_identity,'unassigned');
});

test('seek across the literal fragment does not retain its identity claim or old scope',()=>{
  const model=createScoreAnalysisModel();model.load({...fixture(),module_profile:profile});
  const origin=model.view({playingPage:11},snapshot(118));
  assert.equal(origin.form.moduleEntries[0].id,'development-five-origin');
  const later=model.view({playingPage:16},snapshot(203));
  assert.notEqual(later.form.moduleEntries[0]?.id,'development-five-return');
  model.load(fixture());
  assert.equal(model.view({playingPage:16},snapshot(199)).form.moduleProfileEnabled,false);
});

test('only two Ravel headings change; four cards and labels on other works remain intact',()=>{
  const $=makeDOM(),hud=createStructuralHUD({onEssay(){}});
  hud.load({...fixture(),module_profile:profile});
  assert.equal($('structural-hud').children.length,4);
  assert.equal($('structural-hud').children[0].children[0].textContent,'和声');
  assert.equal($('structural-hud').children[1].children[0].textContent,'配器与织体');
  assert.equal($('structural-hud').children[2].children[0].textContent,'声部关系与复调');
  assert.equal($('structural-hud').children[3].children[0].textContent,'曲式与主题发展');
  hud.reset();hud.load(fixture());
  assert.equal($('structural-hud').children[2].children[0].textContent,'对位');
  assert.equal($('structural-hud').children[3].children[0].textContent,'曲式');
});
