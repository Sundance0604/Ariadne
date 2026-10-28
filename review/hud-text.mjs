// Shared text formatter: the webpage and video exporter render the same state.
import {eventScope} from './research-model.mjs';
export function hudTextFor(dimension,v,context){
if(['counterpoint','form'].includes(dimension)&&v.moduleProfileEnabled){
  const entry=v.moduleEntries[0];
  return {surface:entry?.title||'',background:entry?.summary||''};
}
const es=v.contextualEvents,labels=es.map(e=>(e.analysis_origin==='engine_candidate'?'PDF/MIDI候选 · ':'')+e.short_label);
let surface='待分析',background='点击查看事实、分析与来源';
if(dimension==='harmony'){
  surface=v.surface?`当前：${v.surface.label}`:labels.length?`谱面研究（非实时时点）：${labels.join('；')}`:'当前记谱音响未定位';
  const layers=v.alternatives.filter(r=>r.kind!=='complete_vertical');
  if(layers.length)surface+='\n'+layers.map(r=>`并列层读法：${r.label}${r.chord&&!r.label.includes('转位')?`（层内${['原位','第一转位','第二转位','第三转位'][r.chord.inversion]}，最低${r.layer_bass?.name||'待核'}）`:''}`).join('\n');
  background=v.contextual.length?`背景：${v.contextual.map(c=>c.label).join('；')}`:v.surface&&labels.length?`本段谱面研究：${labels.join('；')}`:'背景和声：待分析';
}else if(dimension==='orchestration'){
  surface=v.activeParts.length?`${v.activeParts.length}个活跃分部 · ${v.activeParts.map(p=>p.label).join('、')}`:v.activityLocated?'当前无已知有效记谱活动':labels.length?`谱面研究（非实时时点）：${labels.join('；')}`:'当前分部活动未定位';
  background=v.observedRoles.length?v.observedRoles.map(c=>c.label).join('；'):v.activityLocated&&labels.length?`本段配器研究：${labels.join('；')}`:'织体职责：候选／待核查';
  if(v.transitions.entered.length)background+='\n此时进入：'+v.transitions.entered.map(p=>p.label).join('、');
  if(v.transitions.exited.length)background+='\n此时退出：'+v.transitions.exited.map(p=>p.label).join('、');
  if(v.uncertainty?.length)background+='\n'+v.uncertainty.join('；');
}else if(dimension==='counterpoint'){
  surface=v.localRelations.length?`${v.localRelations.length}条音程见证 · 非严格对位认定`:labels.join('；')||'当前重要声部关系：待分析';
  background=es.length?`${es.length}项研究 · ${eventScope(es[0],context)}`:'声部独立性与模仿：待核查';
  if(v.localRelations.length&&labels.length)background+='\n相关声部研究：'+labels.join('；');
}else{
  surface=v.activeHierarchy.length?v.activeHierarchy.map(s=>s.title).join('／'):labels.join('；')||'当前结构功能：待分析';
  background=v.activeHierarchy.length?['段落范围：'+v.activeHierarchy.map(s=>`m.${s.xml_range[0]}–${s.xml_range[1]-1}`).join('；')+'（精确及重叠边界见证据）',
    ...v.models.map(m=>`模型候选 · ${m.name}：${m.reading}`)].join('\n'):es.length?eventScope(es[0],context):'主题／乐句／全曲：证据另查';
}
return {surface,background};
}
