import {activeEvents,indexResearch,dimensionLabels,claimLabels,eventScope} from './research-model.mjs';
import {node,rich,verificationText,appendSources} from './research-ui.mjs';

export function createStructuralHUD({onEssay}){
  const root=document.getElementById('structural-hud'),cards=new Map(),signatures=new Map();
  const position=document.getElementById('hud-position'),detail=document.getElementById('hud-detail');
  const toggle=document.getElementById('hud-toggle'),narrow=globalThis.matchMedia?.('(max-width:680px)');
  if(toggle&&narrow){toggle.open=!narrow.matches;narrow.addEventListener('change',event=>{toggle.open=!event.matches;});}
  let data={events:[],sources:[]},index=indexResearch(data),lastPosition='';
  for(const dimension of ['harmony','form','counterpoint','orchestration']){
    const card=node('section',null,'hud-card');card.append(node('h3',dimensionLabels[dimension]));
    const content=node('div');card.append(content);root.append(card);cards.set(dimension,content);
  }
  function explain(event){
    detail.replaceChildren(node('h3',event.short_label),node('p',`${claimLabels[event.claim_level]} · ${verificationText(event.verification)}`,'analysis-note'));
    const body=node('div',null,'analysis-rich');rich(body,event.html);detail.append(body);
    if(event.analysis_framework)detail.append(node('p',`框架：${event.analysis_framework}`));
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
    const label=Number.isFinite(context.playingPage)?`播放位置：PDF 第 ${context.playingPage} 页${context.browsedPage!==context.playingPage?` · 浏览页：第 ${context.browsedPage} 页`:''}`:
      '播放位置待核对 · 不沿用上一段分析';
    if(label!==lastPosition){position.textContent=label;lastPosition=label;}
    const active=activeEvents(index,context);
    for(const [dimension,target] of cards){
      const events=active.get(dimension),signature=events.map(e=>e.id+eventScope(e,context)).join('|');
      if(signatures.get(dimension)===signature)continue;signatures.set(dimension,signature);target.replaceChildren();
      if(!events.length){target.append(node('span','暂无可靠分析','hud-empty'));continue;}
      if(events.length>1)target.append(node('small','多条观点并列 · 参看核查状态'));
      for(const event of events){
        const button=node('button',event.short_label);button.onclick=()=>explain(event);target.append(button,
          node('small',`${claimLabels[event.claim_level]} · ${eventScope(event,context)} · ${event.verification.score==='verified'?'谱面已校核':event.verification.score==='disputed'?'存在争议':'待复核'}`));
      }
    }
  }
  return {update,reset(){data={events:[],essays:[],sources:[]};index=indexResearch(data);signatures.clear();
    detail.hidden=true;detail.replaceChildren();update({});},load(payload){data=payload;index=indexResearch(data);signatures.clear();}};
}
