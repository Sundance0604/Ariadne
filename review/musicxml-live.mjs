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

export function createMusicXMLLive({onChange=()=>{}}={}){
  // Data provider only: a single owner for the activation table, no duplicate UI.
  let data=null,error=null,version=0,index=new Map();
  return {
    at(referenceSeconds){
      const quarter=data?projectedQuarter(data.projection,referenceSeconds):null;
      const frame=data?frameAt(data.frames,quarter):null,i=frame?index.get(frame.id):null;
      return {data,error,quarter:frame?Math.max(quarter,frame.start_q):quarter,frame,
        previousFrame:i>0?data.frames[i-1]:null};
    },
    reset(){version++;data=null;error=null;index=new Map();},
    async load(track){
      const expected=++version;data=null;error=null;
      try{
        const response=await fetch(`/api/musicxml-live?track=${encodeURIComponent(track)}`,{cache:'no-store'}),payload=await response.json();
        if(expected!==version)return;if(!response.ok)throw Error(payload.error||'读取失败');
        if(payload.available){data=payload;index=new Map(data.frames.map((f,i)=>[f.id,i]));}
      }catch(e){if(expected===version)error=e.message;}
      if(expected===version)onChange();
    }
  };
}
