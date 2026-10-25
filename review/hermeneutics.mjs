import {relatedEssay,claimLabels} from './research-model.mjs';
import {node,rich,verificationText,appendSources} from './research-ui.mjs';

export function createHermeneutics({onNavigate}){
  const $=id=>document.getElementById(id),select=$('essay-select'),body=$('essay-body'),follow=$('essay-follow');
  let data={essays:[],sources:[]},selected=null,scrolls=new Map(),context={};
  function show(id){
    const essay=data.essays.find(e=>e.id===id);if(!essay||selected===id)return;
    if(selected)scrolls.set(selected,body.scrollTop);
    selected=id;select.value=id;body.replaceChildren(node('h3',essay.title),
      node('p',`${claimLabels[essay.claim_level]} · ${verificationText(essay.verification)}`,'analysis-note'));
    const prose=node('div',null,'analysis-rich');rich(prose,essay.html);body.append(prose);
    body.append(node('h4','相关乐段（按谱面定位）'));
    for(const span of essay.score_spans){
      if(span.precision==='unlocated'){body.append(node('p','这段证据尚未定位，不用于播放跳转。'));continue;}
      const button=node('button',span.label||`PDF 第 ${span.pdf_page_start}–${span.pdf_page_end} 页`);
      button.onclick=()=>onNavigate(span,essay.verification);body.append(button);
    }
    if(essay.interpretive_note)body.append(node('p',essay.interpretive_note,'analysis-note'));
    appendSources(body,essay,data.sources);body.scrollTop=scrolls.get(id)||0;
  }
  select.onchange=()=>{follow.checked=false;show(select.value);};
  function update(next){context=next;if(!follow.checked)return;const essay=relatedEssay(data.essays,context,selected);if(essay)show(essay.id);}
  follow.onchange=()=>update(context);
  return {show(id){follow.checked=false;show(id);},update,reset(){data={essays:[],sources:[]};selected=null;scrolls.clear();context={};follow.checked=false;
      select.replaceChildren();body.replaceChildren();$('research-state').textContent='正在读取研究资料…';},
    load(payload){data=payload;for(const essay of data.essays){const option=node('option',essay.title);option.value=essay.id;select.append(option);}
      $('research-state').textContent=data.essays.length?'默认独立阅读 · 翻页和播放不会重置本文':'此曲暂无诠释研究资料，原导聆仍可使用。';
      if(data.essays.length)show(data.essays[0].id);},error(message){$('research-state').textContent=`研究未载入：${message}；原播放器不受影响。`;}};
}
