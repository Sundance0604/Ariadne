import {hudTextFor} from './hud-text.mjs';
import {dimensionLabels,claimLabels,eventScope} from './research-model.mjs';
import {node,rich,verificationText,appendSources} from './research-ui.mjs';
import {appendEngineEvidence} from './engine-evidence.mjs';
import {createScoreAnalysisModel,conditionalFigure,partFamily} from './score-analysis-model.mjs';

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

export function createStructuralHUD({onEssay,onEvidence,onOpen=()=>{},onMeasure=()=>{},onNote=()=>{},onRefresh=()=>{}}){
  const root=document.getElementById('structural-hud'),position=document.getElementById('hud-position');
  const detail=document.getElementById('hud-detail'),automatic=document.getElementById('hud-auto-candidates');
  const model=createScoreAnalysisModel(),cards=new Map(),signatures=new Map();
  const toggle=document.getElementById('hud-toggle'),narrow=globalThis.matchMedia?.('(max-width:680px)');
  if(toggle&&narrow){toggle.open=!narrow.matches;narrow.addEventListener('change',e=>{toggle.open=!e.matches;});}
  let data={events:[],essays:[],sources:[]},latest=null,lastContext={},lastSnapshot={},detailVersion=0;
  const labels={harmony:'和声',orchestration:'配器与织体',counterpoint:'对位',form:'曲式'};
  for(const dimension of ['harmony','orchestration','counterpoint','form']){
    const card=node('section',null,'hud-card');card.setAttribute('data-dimension',dimension);
    const heading=node('h3',labels[dimension]);card.append(heading);
    const content=node('button',null,'hud-summary'),surface=node('span'),context=node('small');
    content.setAttribute('aria-label',`查看${labels[dimension]}证据`);content.append(surface,context);
    content.onclick=()=>explainDimension(dimension);card.append(content);root.append(card);
    cards.set(dimension,{card,surface,context,heading,content});
  }
  function moduleLabels(profile){
    for(const [id,fallback] of [['counterpoint','对位'],['form','曲式']]){
      labels[id]=profile?.labels?.[id]||fallback;
      cards.get(id).heading.textContent=labels[id];
      cards.get(id).content.setAttribute('aria-label',`查看${labels[id]}证据`);
    }
  }
  const setText=(n,t)=>{if(n.textContent!==t){n.textContent=t;n.title=t;}};
  function noteIds(target,title,ids,measureId){
    if(!Array.isArray(ids)){
      const selection={windowId:latest?.position.windowId,quarter:latest?.position.xmlQuarter};
      const b=node('button',`${title} · 按需查询`);b.onclick=()=>onMeasure(measureId,selection);
      target.append(b);return;
    }
    const d=node('details');d.append(node('summary',`${title}（${ids?.length||0}）`));
    for(const id of ids||[]){const b=node('button',id,'note-id-link');b.onclick=()=>onNote(id,measureId);d.append(b);}
    if(!ids?.length)d.append(node('p','无'));target.append(d);
  }
  function essays(target,ids){
    for(const id of new Set(ids||[])){
      const essay=data.essays.find(e=>e.id===id);if(!essay)continue;
      const b=node('button',`阅读：${essay.title}`);b.onclick=()=>onEssay?.(id);target.append(b);
    }
  }
  function explain(event){
    const version=++detailVersion;
    detail.replaceChildren(node('h3',event.short_label),node('p',`${claimLabels[event.claim_level]} · ${verificationText(event.verification)}`,'analysis-note'));
    const body=node('div',null,'analysis-rich');rich(body,event.html);detail.append(body);appendHarmony(detail,event.harmonic_analysis);
    if(event.analysis_origin==='engine_candidate'){
      const evidence=node('section');detail.append(evidence);evidence.append(node('p','正在读取PDF/MIDI候选证据…'));
      Promise.resolve().then(()=>onEvidence?.(event.id)).then(payload=>{
        if(version!==detailVersion)return;if(payload)appendEngineEvidence(evidence,payload);
      }).catch(error=>{if(version===detailVersion)evidence.replaceChildren(node('p',`证据未载入：${error.message}`));});
    }
    if(event.analysis_framework)detail.append(node('p',`框架：${event.analysis_framework}`));
    for(const a of event.alternatives||[])detail.append(node('p',`其他解释：${a}`));
    appendSources(detail,event,data.sources);essays(detail,event.related_essay_ids);
    detail.hidden=false;onOpen();
  }
  function explainDimension(dimension){
    if(!latest)return;detailVersion++;const v=latest,p=v.position;
    detail.replaceChildren(node('h3',`${labels[dimension]} · ${p.measureId?`m.${p.number}，小节内${p.onset}`:'播放位置待核对'}`),
      node('p','打开时的证据快照；不跳转录音。记谱事实、理论分析和跨段解释分别列示。','analysis-note'));
    if(p.measureId){
      const b=node('button','查看本时点音符与完整小节数据');b.onclick=()=>onMeasure(p.measureId,{windowId:p.windowId,quarter:p.xmlQuarter,dimension});detail.append(b);
    }
    if(dimension==='harmony'){
      const h=v.harmony;detail.append(node('h4','谱面事实 · 当前记谱音响'),node('p',h.surface?.label||'当前无可定位的定音音符'),
        node('p',`全体实际记谱最低音：${h.surface?.bass?.name||'无'}。不包含未经建模的踏板或录音余响。`));
      noteIds(detail,'当前全体音符ID',h.surface?.noteIds,p.measureId);
      detail.append(node('h4','局部理论分析 · 并列读法'));
      for(const r of h.alternatives){
        const d=node('section',null,'layer-reading');d.append(node('h4',r.label),node('p',`分析对象：${r.kind}。${r.basis}`),
          node('p',`全体最低音：${h.surface?.bass?.name||'无'}；所选层最低音：${r.layer_bass?.name||'无'}；层内根音：${r.chord?.root||'未定'}；层内转位：${r.chord?['原位','第一转位','第二转位','第三转位'][r.chord.inversion]:'不作单一判定'}。`));
        for(const f of r.functions||[])d.append(node('p',conditionalFigure(f),'analysis-note'));
        noteIds(d,'纳入归约的音符ID',r.event_ids,p.measureId);noteIds(d,'另外列出的音符ID',r.omitted_event_ids,p.measureId);detail.append(d);
      }
      detail.append(node('h4','跨时背景 · 独立有效区间'),node('p',h.contextual.length?h.contextual.map(c=>`${c.label} · XML四分音符[${c.start_q}, ${c.end_q})`).join('；'):'背景和声待结合前后文归约；不继承上一瞬时和弦。'));
    }else if(dimension==='orchestration'){
      detail.append(node('h4','谱面事实 · 当前活跃分部'),node('p',`${v.orchestration.activeParts.length}个XML分部；不是乐器种类、演奏员或独立旋律条数。`));
      for(const warning of v.orchestration.uncertainty)detail.append(node('p',warning));
      for(const family of ['木管','铜管','打击乐','键盘／拨弦','弦乐','其他分部']){
        const parts=v.orchestration.activeParts.filter(p=>(p.family||partFamily(p.part_id))===family);if(!parts.length)continue;
        detail.append(node('h4',family));
        for(const part of parts)detail.append(node('p',`${part.label}（${part.part_id}）· ${part.pitches.join('、')||'非定音'} · ${part.roles.length?'规则职责候选：'+part.roles.join('／'):'织体职责见本段分析'}。实际instrument_ref、奏法和起止见音符底稿。`));
      }
      detail.append(node('p',`与前一记谱帧比较，进入：${v.orchestration.transitions.entered.map(p=>p.label).join('、')||'无'}；退出：${v.orchestration.transitions.exited.map(p=>p.label).join('、')||'无'}。`),
        node('h4','理论分析 · 织体与交接'),node('p','最高音不自动等于主旋律；同一钢琴分部可含多个谱表与声部，不按左／右手虚构分工。未核验的职责保留候选。'));
    }else if(dimension==='counterpoint'){
      detail.append(node('h4','谱面事实与声部关系'),node('p',v.counterpoint.localRelations.length?`${v.counterpoint.localRelations.length}条当前窗口音程见证。它们不是严格模仿或种类对位的认定。`:'当前重要声部关系待分析；完整小节数据保留音程、运动与节奏依据。'));
      for(const id of v.counterpoint.localRelations)detail.append(node('p',`音程证据：${id}`));
    }else{
      detail.append(node('h4','跨段结构 · 层级与竞争模型'));
      for(const s of v.form.activeHierarchy)detail.append(node('p',`${s.title} · XML四分音符[${s.start_q}, ${s.end_q}) · 代理结构综合，人工签核待完成。`));
      for(const m of v.form.models)detail.append(node('p',`${m.name}：${m.reading}`));
      detail.append(node('p','更细的主题／动机、乐句、终止见完整小节数据和既有研究；小节边界不自动等于乐句边界。'));
    }
    if(['counterpoint','form'].includes(dimension)&&v[dimension].moduleProfileEnabled){
      detail.append(node('h4',labels[dimension]+' · 当前研究'));
      for(const e of v[dimension].moduleEntries){
        detail.append(node('h4',e.title),node('p',e.summary),node('p',e.detail));
        detail.append(node('small','沿用已有谱面研究及代理XML核查；未代填人类或专家签核。'));
        for(const ref of e.source_events)detail.append(node('p',`已有依据：${ref.id} · ${ref.path}`));
        for(const id of e.relation_ids){
          const r=v.moduleRelations.find(r=>r.id===id);if(!r)continue;
          detail.append(node('h4','跨时间的局部材料对应'),node('p',r.scope),
            node('p',`音程：${r.intervals.join('、')}半音；时值比例：${r.duration_ratios.join(' : ')}；移位${r.transposition_semitones}半音。`),
            node('p',`原有Motif记录：${r.motif_comparison_id}；主题身份未认定。`));
          for(const [title,occurrence] of [['较早片段',r.from],['较后片段',r.to]])
            noteIds(detail,title,occurrence.event_ids,occurrence.measure_id);
          for(const text of r.counterevidence)detail.append(node('p',text));
        }
      }
    }
    if(v.cases.length){detail.append(node('h4','谱例核查与范围'));
      for(const c of v.cases)detail.append(node('p',`${c.label}：${c.explanation} · XML四分音符[${c.start_q}, ${c.end_q}) · 代理核查，人工签核待完成。`));
      essays(detail,v.cases.flatMap(c=>c.related_essay_ids||[]));
    }
    const events=v[dimension].contextualEvents;
    if(events.length)detail.append(node('h4','已有研究与来源 · 不与瞬时事实合并'));
    for(const e of events){const b=node('button',`${e.analysis_origin==='engine_candidate'?'PDF/MIDI候选 · ':''}${e.short_label}`);b.onclick=()=>explain(e);
      detail.append(b,node('small',`${eventScope(e,lastContext)} · ${verificationText(e.verification)}`));}
    detail.hidden=false;onOpen();
  }
  function update(context,snapshot={}){
    lastContext=context;lastSnapshot=snapshot;latest=model.view(context,snapshot,Boolean(automatic?.checked));
    const state=snapshot.data?'ready':snapshot.error?'error':'unavailable';
    if(position.getAttribute('data-xml-state')!==state)position.setAttribute('data-xml-state',state);
    const p=latest.position;
    setText(position,p.error?`谱面数据未载入：${p.error}`:p.measureId?`当前：m.${p.number} · PDF 第${p.pdfPage}页 · 录音投影估计${context.browsedPage!==p.pdfPage?` · 浏览页：${context.browsedPage}`:''}`:
      Number.isFinite(context.playingPage)?`播放位置：PDF 第 ${context.playingPage} 页 · 浏览页：第 ${context.browsedPage} 页`:'位置未覆盖 · 不沿用上一时点');
    for(const [dimension,card] of cards){
      const signature=latest.signatures[dimension];if(signatures.get(dimension)===signature)continue;signatures.set(dimension,signature);
      const {surface,background}=hudTextFor(dimension,latest[dimension],context);
      setText(card.surface,surface);setText(card.context,background);
    }
  }
  if(automatic)automatic.onchange=()=>{signatures.clear();update(lastContext,lastSnapshot);onRefresh();};
  return {update,showEvent:explain,showDimension:explainDimension,view:()=>latest,
    reset(){detailVersion++;data={events:[],essays:[],sources:[]};model.load(data);moduleLabels(null);signatures.clear();latest=null;
      if(automatic)automatic.checked=false;detail.hidden=true;detail.replaceChildren();update({});},
    load(payload){data=payload;model.load(data);moduleLabels(payload.module_profile);signatures.clear();}};
}
