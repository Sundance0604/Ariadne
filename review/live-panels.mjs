import {createHarmonicFlow,drawHarmonicFlow} from './harmonic-flow.mjs';
import {createOrchestrationActivity} from './orchestration-activity.mjs';

export function createLivePanels(){
  const root=document.getElementById('live-visual-panels'),flow=document.getElementById('live-flow'),
    activity=document.getElementById('live-activity'),state=document.getElementById('live-visual-state');
  let version=0,models=null,time=0;
  const usable=root&&typeof flow?.getContext==='function'&&typeof activity?.getContext==='function';
  function reset(){version++;models=null;if(root)root.hidden=true;}
  function update(seconds){
    time=seconds;if(!usable||!models)return;
    const f=models.flow.frame(seconds),a=models.activity.frame(seconds);
    for(const [canvas,frame] of [[flow,f],[activity,a]]){
      canvas.width=frame.width;canvas.height=frame.height;
      drawHarmonicFlow(canvas.getContext('2d'),frame);
    }
    if(state)state.textContent=f.covered?'四个弦乐分部 · 记谱区间的候选时间投影；震音显示交替音范围':'乐章停顿或未覆盖区间';
  }
  return {reset,update,async load(track){
    reset();if(!usable)return;
    const expected=version;
    try{
      const response=await fetch(`/api/visual-panels?track=${encodeURIComponent(track)}`,{cache:'no-store'});
      const data=await response.json();if(expected!==version)return;
      if(!response.ok)throw Error(data.error||'面板读取失败');
      if(!data.available)return;
      models={flow:createHarmonicFlow({...data.flow,parts:data.activity.parts,flow_groups:data.flow_groups}),
              activity:createOrchestrationActivity(data.activity)};
      root.hidden=false;update(time);
    }catch(error){if(expected===version&&state){root.hidden=false;state.textContent=error.message;}}
  }};
}
