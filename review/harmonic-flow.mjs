// One deterministic drawing plan for Canvas 2D and offline transparent frames.
// Positions use projected video seconds; bars represent notation, not loudness.
import {intervalIndex} from './interval-index.mjs';
export const pitchClassNames=['C','Db','D','Eb','E','F','Gb','G','Ab','A','Bb','B'];
export const visualPalette={primary:'#FFDF42',secondary:'#d8c575',background:'#18160e'};
const yellow=visualPalette.primary;
const covered=(d,t)=>!d.coverage||d.coverage.segments.some(s=>s.start_seconds<=t&&t<s.end_seconds);
export function createHarmonicFlow(data){
  const notes=[...data.notes].sort((a,b)=>a.start_seconds-b.start_seconds);
  const parts=data.parts||[...new Map(notes.map(n=>[n.part_id,{id:n.part_id,label:n.label||n.part_id,
    family:n.family||'其他',color:yellow,flow_group:n.part_id}])).values()];
  const byPart=new Map(parts.map(p=>[p.id,p])),groups=data.flow_groups||parts.map(p=>
    ({id:p.id,label:p.label,color:p.color||yellow,part_ids:[p.id]})),
    groupIndex=new Map(groups.map((g,i)=>[g.id,i]));
  const groupForPart=new Map(groups.flatMap(g=>g.part_ids.map(pid=>[pid,g.id])));
  const lane=n=>groupIndex.get(groupForPart.get(n.part_id))??0;
  const percussion=data.percussion||[],hasPercussion=percussion.length>0||parts.some(p=>p.family==='打击乐');
  const noteIndex=intervalIndex(notes),percussionIndex=intervalIndex(percussion);
  const logicalHeight=groups.length<=5?240:252+16*Math.ceil(groups.length/5);
  return {frame(time,{width=400,height=logicalHeight,future=4,past=1.5,partIds=null}={}){
    if(!Number.isFinite(time)||future<=0||past<0)throw Error('Invalid flow clock');
    const commands=[],rect=(x,y,w,h,color,alpha=1)=>{if(w>0&&h>0)commands.push({op:'rect',x,y,w,h,color,alpha});},
      text=(x,y,value,size,color,alpha=1)=>commands.push({op:'text',x,y,text:value,size,color,alpha}),
      line=(x,y,x2,y2,color,alpha=1)=>commands.push({op:'line',x,y,x2,y2,color,alpha});
    const sx=width/400,sy=height/logicalHeight;
    // Work in 400×240 logical coordinates; export and Canvas scale identically.
    rect(0,0,400,logicalHeight,visualPalette.background,.76);
    text(12,9,'和声音流 · 实音12音级',17,yellow);
    if(groups.length<=5)groups.forEach((g,i)=>{
      const step=376/Math.max(1,groups.length),x=12+i*step;
      rect(x,36,6,6,g.color,.95);text(x+10,31,g.label,Math.min(11,(step-12)/Math.max(1,g.label.length)),g.color);
    });
    else text(12,32,`${groups.length}个乐器模块`,11,yellow);
    const left=12,right=hasPercussion?348:388,top=56,bottom=208,column=(right-left)/12,
      scale=(bottom-top)/(future+past),now=top+future*scale;
    const isCovered=covered(data,time),visible=[];
    for(let pc=0;pc<12;pc++){
      if([1,3,6,8,10].includes(pc))rect(left+pc*column,top,column,bottom-top,yellow,.065);
      line(left+pc*column,top,left+pc*column,bottom,yellow,.13);
      text(left+pc*column+3,215,pitchClassNames[pc],12,yellow);
    }
    for(const dt of [1,2,3,4])if(dt<=future){const y=now-dt*scale;line(left,y,right,y,yellow,.09);}
    const spansByLane=new Map();
    if(isCovered)for(const n of noteIndex.between(time-past,time+future)){
      if(!groupForPart.has(n.part_id))continue;
      if(n.end_seconds<=time-past||partIds&&!partIds.includes(n.part_id))continue;
      if(!Number.isFinite(n.start_seconds)||!Number.isFinite(n.end_seconds)||n.end_seconds<=n.start_seconds)continue;
      visible.push(n);const key=`${n.pc}:${lane(n)}`;
      if(!spansByLane.has(key))spansByLane.set(key,[]);spansByLane.get(key).push(n);
    }
    // Union overlapping same-class/family bars: doubling never raises opacity.
    const activePcs=new Set();
    for(const [key,rows] of spansByLane){
      const [pc,li]=key.split(':').map(Number),spans=[];
      for(const n of rows){
        const previous=spans.at(-1);
        if(previous&&n.start_seconds<previous[1])previous[1]=Math.max(previous[1],n.end_seconds);
        else spans.push([n.start_seconds,n.end_seconds]);
        if(n.start_seconds<=time&&time<n.end_seconds)activePcs.add(pc);
      }
      for(const [a,b] of spans){
        const laneWidth=(column-6)/Math.max(1,groups.length),x=left+pc*column+3+li*laneWidth,w=Math.max(1,laneWidth*.79),
          y=Math.max(top,now-(b-time)*scale),end=Math.min(bottom,now-(a-time)*scale);
        const color=groups[li]?.color||yellow;
        if(a<time)rect(x,Math.max(y,now),w,end-Math.max(y,now),color,.29);
        if(b>time)rect(x,y,w,Math.min(end,now)-y,color,.56);
        if(a<=time&&time<b)rect(x,now-1.5,w,3,color,1);
      }
    }
    const percussionIds=[];
    if(hasPercussion){
      line(355,top,355,bottom,yellow,.17);text(363,215,'打击',11,yellow);
      const byDrum=new Map(),drums=parts.filter(p=>p.family==='打击乐').map(p=>p.id);
      if(isCovered)for(const e of percussionIndex.between(time-past,time+future)){
        if(!byPart.has(e.part_id))continue;
        if(e.start_seconds>time+future||e.end_seconds<=time-past)continue;
        if(partIds&&!partIds.includes(e.part_id))continue;
        if(!byDrum.has(e.part_id))byDrum.set(e.part_id,[]);byDrum.get(e.part_id).push(e);
        percussionIds.push(e.id);
      }
      for(const [pid,rows] of byDrum){
        const spans=[],attacks=new Set();
        for(const e of rows.sort((a,b)=>a.start_seconds-b.start_seconds)){
          const last=spans.at(-1);if(last&&e.start_seconds<last[1])last[1]=Math.max(last[1],e.end_seconds);
          else spans.push([e.start_seconds,e.end_seconds]);attacks.add(e.start_seconds);
        }
        const step=24/Math.max(1,drums.length),x=363+Math.max(0,drums.indexOf(pid))*step,
          color=groups[groupIndex.get(groupForPart.get(pid))]?.color||byPart.get(pid)?.color||yellow;
        for(const [a,b] of spans){
          const y=Math.max(top,now-(b-time)*scale),end=Math.min(bottom,now-(a-time)*scale);
          rect(x,y,Math.max(1,step-1),end-y,color,a<=time&&time<b?.65:.27);
        }
        for(const a of attacks){const y=now-(a-time)*scale;if(y>=top&&y<=bottom)rect(x,y,Math.max(1,step-1),1,color,.7);}
      }
    }
    line(left,now,388,now,yellow,.87);
    for(const pc of activePcs)rect(left+pc*column+3,234,column-6,2,yellow,.8);
    if(groups.length>5)groups.forEach((g,i)=>{
      const x=12+(i%5)*76,y=248+Math.floor(i/5)*16;
      rect(x,y+3,5,7,g.color,.9);text(x+8,y,g.label,Math.min(10,65/Math.max(1,g.label.length)),g.color,.95);
    });
    // Apply scaling to the command list once; text stays in the same coordinate system.
    for(const c of commands){c.x*=sx;c.y*=sy;if(c.w!==undefined)c.w*=sx;if(c.h!==undefined)c.h*=sy;
      if(c.x2!==undefined)c.x2*=sx;if(c.y2!==undefined)c.y2*=sy;if(c.size)c.size*=Math.min(sx,sy);}
    return {time,width,height,commands,active_pitch_classes:[...activePcs].sort((a,b)=>a-b),
      visible_note_ids:visible.map(n=>n.id),visible_percussion_ids:percussionIds,instrument_ids:parts.map(p=>p.id),
      group_ids:groups.map(g=>g.id),covered:isCovered};
  }};
}

export function drawHarmonicFlow(ctx,frame){
  ctx.clearRect(0,0,frame.width,frame.height);ctx.save();ctx.textBaseline='top';
  for(const c of frame.commands){ctx.globalAlpha=c.alpha;ctx.fillStyle=c.color;ctx.strokeStyle=c.color;
    if(c.op==='rect')ctx.fillRect(c.x,c.y,c.w,c.h);
    else if(c.op==='text'){ctx.font=`${c.size}px "Microsoft YaHei",sans-serif`;ctx.fillText(c.text,c.x,c.y);}
    else if(c.op==='line'){ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(c.x,c.y);ctx.lineTo(c.x2,c.y2);ctx.stroke();}
  }ctx.restore();
}
