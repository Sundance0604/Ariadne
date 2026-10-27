// Display-only module: one source part per tile; deterministic media-time animation.
import {visualPalette} from './harmonic-flow.mjs';
import {intervalIndex} from './interval-index.mjs';
const order=['独奏','木管','铜管','打击乐','弦乐','键盘／拨弦','其他'];
export function createOrchestrationActivity(data){
  const parts=data.parts||[],events=new Map(parts.map(p=>[p.id,[]]));
  for(const e of data.events||[])if(events.has(e.part_id))events.get(e.part_id).push(e);
  const indices=new Map([...events].map(([id,rows])=>[id,intervalIndex(rows)]));
  const grouped=new Map();
  for(const p of parts){const key=p.role==='solo'?'独奏':p.family||'其他';if(!grouped.has(key))grouped.set(key,[]);grouped.get(key).push(p);}
  const groups=[...grouped].sort((a,b)=>order.indexOf(a[0])-order.indexOf(b[0]));
  const totalRows=groups.reduce((n,[,ps])=>n+Math.ceil(ps.length/5),0),logicalHeight=65+43*totalRows;
  return {frame(time,{width=520,height=logicalHeight}={}){
    const commands=[],rect=(x,y,w,h,color,alpha=1)=>commands.push({op:'rect',x,y,w,h,color,alpha}),
      text=(x,y,value,size,color,alpha=1)=>commands.push({op:'text',x,y,text:value,size,color,alpha});
    rect(0,0,520,logicalHeight,visualPalette.background,.76);
    text(12,9,'配器激活',17,visualPalette.primary);text(320,15,'起音 · 持续 · 休止',11,visualPalette.secondary);
    const columns=Math.min(5,Math.max(1,...groups.map(([,ps])=>ps.length))),rowH=43,tileW=(448-(columns-1)*6)/columns;
    const covered=!data.coverage||data.coverage.segments.some(s=>s.start_seconds<=time&&time<s.end_seconds);
    const states=[];
    let rowIndex=0;
    groups.forEach(([family,ps])=>{
      const groupY=48+rowIndex*rowH; text(12,groupY+8,family,12,visualPalette.secondary);
      ps.forEach((part,i)=>{
        const y=groupY+Math.floor(i/columns)*rowH;
        const index=indices.get(part.id),active=covered?index.between(time,time):[],
          lastAttack=covered?index.lastStart(time):-Infinity,lastEnd=covered?index.lastEnd(time):-Infinity;
        const unknown=covered&&(data.unknown_intervals||[]).some(e=>e.part_id===part.id&&e.start_seconds<=time&&time<e.end_seconds);
        const attack=covered?Math.max(0,1-(time-lastAttack)/.16):0,
          release=covered?Math.max(0,1-(time-lastEnd)/.18):0,
          level=unknown?0:Math.max(active.length? .42:0,attack,release*.3),
          x=60+(i%columns)*(tileW+6),h=31,color=part.color||visualPalette.primary;
        rect(x,y,tileW,h,color,.035+level*.18);
        const border=.10+level*.60;
        rect(x,y,tileW,1,color,border);rect(x,y+h-1,tileW,1,color,border);
        rect(x,y,1,h,color,border);rect(x+tileW-1,y,1,h,color,border);
        if(level>0)rect(x+1,y+1,2,h-2,color,.25+level*.65);
        const label=part.label+(unknown?' ?':'');
        text(x+7,y+7,label,Math.min(12,(tileW-12)/Math.max(1,label.length)),color,unknown?.5:.32+level*.68);
        states.push({part_id:part.id,active:active.length>0,attack:attack>0,unknown,level,
          event_ids:active.flatMap(e=>e.event_ids||[e.id])});
      });
      rowIndex+=Math.ceil(ps.length/columns);
    });
    text(12,logicalHeight-17,'按声部 · 记谱时值',10,visualPalette.secondary,.65);
    const sx=width/520,sy=height/logicalHeight;
    for(const c of commands){c.x*=sx;c.y*=sy;if(c.w!==undefined)c.w*=sx;if(c.h!==undefined)c.h*=sy;if(c.size)c.size*=Math.min(sx,sy);}
    return {time,width,height,commands,states,covered};
  }};
}
