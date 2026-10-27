// Immutable interval lookup: deterministic seeks without scanning the full score.
export function intervalIndex(events){
  const rows=[...events].sort((a,b)=>a.start_seconds-b.start_seconds),prefix=[];
  let end=-Infinity;for(const e of rows){end=Math.max(end,e.end_seconds);prefix.push(end);}
  const ends=rows.map(e=>e.end_seconds).sort((a,b)=>a-b);
  function upper(values,time,get=x=>x){let lo=0,hi=values.length;while(lo<hi){const m=(lo+hi)>>1;if(get(values[m])<=time)lo=m+1;else hi=m;}return lo;}
  return {
    between(from,to){const found=[];for(let i=upper(rows,to,e=>e.start_seconds)-1;i>=0&&prefix[i]>from;i--)if(rows[i].end_seconds>from)found.push(rows[i]);return found.reverse();},
    lastStart(time){return rows[upper(rows,time,e=>e.start_seconds)-1]?.start_seconds??-Infinity;},
    lastEnd(time){return ends[upper(ends,time)-1]??-Infinity;}
  };
}
