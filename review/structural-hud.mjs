import {activeEvents,indexResearch,dimensionLabels,claimLabels,eventScope} from './research-model.mjs';
import {node,rich,verificationText,appendSources} from './research-ui.mjs';
import {appendEngineEvidence} from './engine-evidence.mjs';

const systems={functional_tonal:'调性功能和声',modal_pentatonic:'调式／五声材料',quartal:'四度结构',layered_pedal:'分层与持续低音'};
const inversions={root:'原位',first:'第一转位',second:'第二转位',third:'第三转位',not_applicable:'不适用',undetermined:'不作单一转位判定'};
function appendHarmony(target,harmony){
  if(!harmony)return;
  const section=node('section',null,'harmonic-evidence');section.append(node('h4','和声与声部依据（实音）'));
  const facts=node('dl',null,'harmonic-summary');
  for(const [label,value] of [['体系',systems[harmony.system]],['调性语境',harmony.key_context],
    ['级数',harmony.roman_numeral||'不强加功能级数'],['根音',harmony.root||'不归为单一三度和弦'],
    [harmony.analysis_layer?'所选层低音':'实际低音',harmony.bass],['转位',inversions[harmony.inversion]],['结构音',harmony.pitch_collection.join('、')],
    ['省略音',(harmony.omitted_tones||[]).join('、')||'无另列省略音']]){
    facts.append(node('dt',label),node('dd',value));
  }
  section.append(facts,node('p',`取样范围：${harmony.temporal_scope}`));
  if(harmony.analysis_layer)section.append(node('p',harmony.analysis_layer,'analysis-note'));
  const scroll=node('div',null,'harmonic-table'),table=node('table'),head=node('thead'),row=node('tr');
  for(const label of ['乐器／声部','实音','职责'])row.append(node('th',label));head.append(row);table.append(head);
  const body=node('tbody');for(const voice of harmony.voices){const row=node('tr');
    for(const text of [voice.instrument,voice.pitches.join('、'),voice.role])row.append(node('td',text));body.append(row);}
  table.append(body);scroll.append(table);section.append(scroll,node('p',`声部进行：${harmony.voice_leading}`),
    node('p',`非和弦音／材料音：${harmony.nonchord_tones}`));target.append(section);
}

export function createStructuralHUD({onEssay,onEvidence}){
  const root=document.getElementById('structural-hud'),cards=new Map(),signatures=new Map();
  const position=document.getElementById('hud-position'),detail=document.getElementById('hud-detail');
  const automatic=document.getElementById('hud-auto-candidates');
  const toggle=document.getElementById('hud-toggle'),narrow=globalThis.matchMedia?.('(max-width:680px)');
  if(toggle&&narrow){toggle.open=!narrow.matches;narrow.addEventListener('change',event=>{toggle.open=!event.matches;});}
  let data={events:[],sources:[]},index=indexResearch(data),lastPosition='',detailVersion=0,lastContext={};
  for(const dimension of ['harmony','form','counterpoint','orchestration']){
    const card=node('section',null,'hud-card');card.append(node('h3',dimensionLabels[dimension]));
    const content=node('div');card.append(content);root.append(card);cards.set(dimension,content);
  }
  function explain(event){
    const version=++detailVersion;
    detail.replaceChildren(node('h3',event.short_label),node('p',`${claimLabels[event.claim_level]} · ${verificationText(event.verification)}`,'analysis-note'));
    const body=node('div',null,'analysis-rich');rich(body,event.html);detail.append(body);
    appendHarmony(detail,event.harmonic_analysis);
    if(event.analysis_origin==='engine_candidate'){
      const evidence=node('section');detail.append(evidence);evidence.append(node('p','正在读取原始音符与结构证据…'));
      Promise.resolve().then(()=>onEvidence?.(event.id)).then(payload=>{
        if(version!==detailVersion)return;
        if(payload)appendEngineEvidence(evidence,payload);else evidence.replaceChildren(node('p','证据读取已取消或当前曲目已改变。'));
      }).catch(error=>{if(version===detailVersion)evidence.replaceChildren(node('p',`证据未载入：${error.message}`));});
    }
    if(event.analysis_framework)detail.append(node('p',`框架：${event.analysis_framework}`));
    if(event.analysis_origin==='musicxml_analysis'&&event.evidence_url){
      const link=node('a','本小节全部音符、记谱与分析证据');link.href=event.evidence_url;link.target='_blank';link.rel='noopener noreferrer';detail.append(link);
    }
    for(const alternative of event.alternatives||[])detail.append(node('p',`其他解释：${alternative}`));
    appendSources(detail,event,data.sources);
    for(const id of event.related_essay_ids||[]){
      const essay=data.essays.find(e=>e.id===id);if(!essay)continue;
      const button=node('button',`阅读：${essay.title}`);button.onclick=()=>onEssay(id);detail.append(button);
    }
    detail.hidden=false;
    if(detail.parentElement)detail.parentElement.open=true;
  }
  function update(context){
    lastContext=context;
    const label=Number.isFinite(context.playingPage)?`播放位置：PDF 第 ${context.playingPage} 页${context.browsedPage!==context.playingPage?` · 浏览页：第 ${context.browsedPage} 页`:''}`:
      '播放位置待核对 · 不沿用上一段分析';
    if(label!==lastPosition){position.textContent=label;lastPosition=label;}
    const active=activeEvents(index,context);
    for(const [dimension,target] of cards){
      const candidates=active.get(dimension).filter(e=>e.analysis_origin!=='engine_candidate'||automatic?.checked),studies=candidates.filter(e=>e.analysis_origin==='score_study'),generated=candidates.filter(e=>e.analysis_origin==='engine_candidate');
      const symbolic=candidates.filter(e=>e.analysis_origin==='musicxml_analysis');
      const events=studies.length||symbolic.length?[...studies,...symbolic,...(symbolic.length&&automatic?.checked?generated:[])]:generated.length?generated:candidates,signature=events.map(e=>e.id+eventScope(e,context)).join('|');
      if(signatures.get(dimension)===signature)continue;signatures.set(dimension,signature);target.replaceChildren();
      if(!events.length){target.append(node('span','待分析','hud-empty'));continue;}
      if(events.length>1)target.append(node('small','多条观点并列 · 参看核查状态'));
      for(const event of events){
        const button=node('button',event.short_label);button.onclick=()=>explain(event);target.append(button,
          node('small',`${claimLabels[event.claim_level]} · ${eventScope(event,context)} · ${event.verification.score==='verified'?'谱面已校核':event.verification.score==='agent_score_checked'?'代理逐谱核对／人工签核待完成':event.verification.score==='disputed'?'存在争议':'待复核'}`));
        if(event.analysis_origin==='engine_candidate'&&event.scope_kind==='background')target.append(node('small','跨段结构背景候选'));
      }
    }
  }
  if(automatic)automatic.onchange=()=>{signatures.clear();update(lastContext);};
  return {update,reset(){detailVersion++;data={events:[],essays:[],sources:[]};index=indexResearch(data);signatures.clear();
    if(automatic)automatic.checked=false;
    detail.hidden=true;detail.replaceChildren();update({});},load(payload){data=payload;index=indexResearch(data);signatures.clear();}};
}
