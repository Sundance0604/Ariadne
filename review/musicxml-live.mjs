import {node} from './research-ui.mjs';
import {referenceTickAt} from './research-model.mjs';

export function frameAt(frames,quarter){
  if(!Number.isFinite(quarter))return null;
  // Tempo integration can land a few ulps below an exact XML boundary.
  // This is numerical tolerance, not a musical look-ahead window.
  let lo=0,hi=frames.length;while(lo<hi){const mid=(lo+hi)>>1;if(frames[mid].start_q<=quarter+1e-8)lo=mid+1;else hi=mid;}
  const f=frames[lo-1];return f&&quarter<f.end_q?f:null;
}

export function projectedQuarter(projection,seconds){
  if(!Number.isFinite(seconds)||seconds<0||seconds>=projection.reference_end_seconds)return null;
  const tick=referenceTickAt(projection.reference_clock,seconds);
  const q=Number.isFinite(tick)?tick/projection.ppq:null;
  return Number.isFinite(q)&&q<projection.reference_end_quarter?q:null;
}

export function createMusicXMLLive(){
  const root=document.getElementById('musicxml-live');if(!root)return {reset(){},load(){},update(){}};
  const position=node('p',null,'xml-live-position'),columns=node('div',null,'xml-live-columns'),harmony=node('div'),orchestra=node('div');
  columns.append(harmony,orchestra);root.append(position,columns);
  let data=null,version=0,last='',context={};
  function update(next){
    context=next;if(!data)return;
    const q=projectedQuarter(data.projection,next.referenceSeconds),frame=frameAt(data.frames,q);
    const signature=frame?.id||'unlocated';if(signature===last)return;last=signature;
    harmony.replaceChildren();orchestra.replaceChildren();
    if(!frame){position.textContent='当前和声与乐器：位置未覆盖，不沿用上一时点';return;}
    position.textContent=`当前谱面（估计）· m.${frame.number} · PDF ${frame.page}页 · 小节内 ${frame.onset_q} 四分音符处`;
    harmony.append(node('h3','和声 · 并列读法'));
    const readings=data.readings[frame.harmony_window_id]||[];
    if(!readings.length)harmony.append(node('p','此处无定音和弦，仍显示活动乐器。'));
    for(const [i,r] of readings.entries()){
      const line=node('div',null,'xml-live-reading');line.append(node('strong',(readings.length>1?`${i+1}. `:'')+r.label));
      for(const f of r.functions||[])line.append(node('small',`${f.context}：${f.figure}（条件性）`));
      if(r.kind!=='complete_vertical')line.append(node('small',r.basis));harmony.append(line);
    }
    orchestra.append(node('h3',`活跃乐器 · ${frame.active_instruments.length}个分部`));
    const chips=node('div',null,'xml-instrument-chips');
    for(const p of frame.active_instruments){
      const chip=node('span',p.label,'xml-instrument-chip');chip.title=[p.pitches.join('、'),p.roles.join('／'),...p.instrument_names].filter(Boolean).join(' · ');
      chip.append(node('small',p.roles.join('／')));chips.append(chip);
    }
    orchestra.append(chips);
  }
  return {update,reset(){version++;data=null;last='';context={};root.hidden=true;position.textContent='';harmony.replaceChildren();orchestra.replaceChildren();},
    async load(track){const expected=++version;try{
      const response=await fetch(`/api/musicxml-live?track=${encodeURIComponent(track)}`,{cache:'no-store'});const payload=await response.json();
      if(expected!==version)return;if(!response.ok)throw Error(payload.error||'读取失败');if(!payload.available)return;
      data=payload;root.hidden=false;last='';update(context);
    }catch(error){if(expected===version){root.hidden=false;position.textContent=`当前谱面数据未载入：${error.message}`;}}}};
}
