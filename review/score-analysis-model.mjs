import {activeEvents,indexResearch,eventScope,spanMatches} from './research-model.mjs';

export const quarter=value=>typeof value==='string'&&value.includes('/')?value.split('/').map(Number).reduce((a,b)=>a/b):Number(value);
const within=(row,q)=>Number.isFinite(q)&&quarter(row.start_q)<=q&&q<quarter(row.end_q);
const qualities={'major triad':'大三和弦','minor triad':'小三和弦','diminished triad':'减三和弦','augmented triad':'增三和弦',
  'dominant seventh chord':'属七型和弦','major seventh chord':'大七和弦','minor seventh chord':'小七和弦',
  'half-diminished seventh chord':'半减七和弦','diminished seventh chord':'减七和弦'};
export function surfaceLabel(w){
  if(!w)return '无定音音符';
  if(w.chord)return `${w.chord.root}${qualities[w.chord.quality]||w.chord.quality} · ${['原位','第一转位','第二转位','第三转位'][w.chord.inversion]||'转位待核'} · 全体最低音${w.bass?.name}`;
  const pcs=w.pitch_classes||[],names=[...new Set((w.pitches||[]).map(p=>p.replace(/-?\d+$/,'')))];
  if(pcs.length===2&&[5,7].includes(Math.abs(pcs[1]-pcs[0]))){
    const low=w.bass?.name?.replace(/-?\d+$/,'');
    return `开放五度 · ${[...new Set([low,...names].filter(Boolean))].join('／')}（无三音，功能未定）`;
  }
  if(w.structures?.includes('quartal'))return `四度结构 · ${names.join('／')}`;
  if(w.structures?.includes('anhemitonic_pentatonic'))return `无半音五声音集 · ${names.join('／')}`;
  return `实音集合 · ${(w.pitches||[]).join('、')}`;
}
export function conditionalFigure(f){
  return f.pitch_classes_agree?`在${f.context}候选下：${f.figure}（不等同功能认定）`:
    `在${f.context}候选下：条件性级数待审查（原输出${f.figure}）`;
}
export function partFamily(id){
  const n=Number(id?.replace(/^P/,''));
  return n>=1&&n<=9?'木管':n>=10&&n<=15?'铜管':n>=16&&n<=21?'打击乐':n>=22&&n<=23?'键盘／拨弦':n>=24&&n<=37?'弦乐':'其他分部';
}
const distinct=items=>[...new Map(items.map(e=>[e.id,e])).values()];

export function createScoreAnalysisModel(){
  let data={events:[],essays:[],sources:[]},curated=indexResearch(data),aux=indexResearch(data),xml=new Map();
  return {
    load(next){
      data=next;curated=indexResearch({events:(data.events||[]).filter(e=>!['musicxml_analysis','engine_candidate'].includes(e.analysis_origin))});
      aux=indexResearch({events:(data.events||[]).filter(e=>e.analysis_origin==='engine_candidate')});xml=new Map();
      for(const event of data.events||[])if(event.analysis_origin==='musicxml_analysis'){
        if(!xml.has(event.xml_measure_id))xml.set(event.xml_measure_id,[]);xml.get(event.xml_measure_id).push(event);
      }
    },
    view(context,snapshot={},automatic=false){
      const {data:live,quarter:q,frame,previousFrame}=snapshot;
      const active=activeEvents(curated,context),old=automatic?activeEvents(aux,context):new Map();
      const cases=(live?.hud_cases?.cases||[]).filter(c=>frame&&within(c,q));
      const contexts=(live?.hud_cases?.contexts||[]).filter(c=>frame&&within(c,q));
      const sections=(live?.form?.sections||[]).filter(s=>frame&&within(s,q));
      const w=frame?live.windows?.[frame.harmony_window_id]:null;
      const parts=frame?.active_instruments||[],previous=previousFrame?.active_instruments||[];
      const transitions={entered:parts.filter(p=>!previous.some(old=>old.part_id===p.part_id)),
        exited:previous.filter(p=>!parts.some(now=>now.part_id===p.part_id))};
      const events=dimension=>distinct([...(active.get(dimension)||[]),...(old.get(dimension)||[])]);
      const profile=data.module_profile;
      const moduleEntries=dimension=>(profile?.readings||[]).filter(e=>e.dimension===dimension&&
        (frame&&e.start_q!==undefined?within(e,q):e.score_spans.some(s=>spanMatches(s,context))))
        .sort((a,b)=>b.priority-a.priority);
      const common={position:{source:'estimated_playback',measureId:frame?.measure_id||null,windowId:frame?.harmony_window_id||null,
        xmlQuarter:q,pdfPage:frame?.page??context.playingPage??null,number:frame?.number,onset:frame?.onset_q,
        timePrecision:'candidate_projection',error:snapshot.error},
        cases,sources:data.sources||[],essays:data.essays||[],xmlEvidence:xml.get(frame?.measure_id)||[],automatic};
      const noPitched=frame&&!frame.harmony_window_id;
      const harmony={surface:w?{...w,label:surfaceLabel(w),noteIds:w.event_ids}:noPitched?
        {id:'no-pitched',label:'无有效定音音符；非定音活动另列配器',noteIds:[],pitches:[],bass:null,chord:null}:null,
        contextual:contexts,alternatives:frame?live.readings[frame.harmony_window_id]||[]:[],contextualEvents:events('harmony')};
      const orchestration={activeParts:parts,transitions,observedRoles:cases.filter(c=>c.dimensions?.includes('orchestration')),
        contextualEvents:events('orchestration')};
      const counterpoint={localRelations:cases.flatMap(c=>c.interval_ids||[]),contextualEvents:events('counterpoint'),
        moduleProfileEnabled:Boolean(profile),moduleEntries:moduleEntries('counterpoint')};
      const form={activeHierarchy:sections,models:live?.form?.models||[],contextualEvents:events('form'),
        moduleProfileEnabled:Boolean(profile),moduleEntries:moduleEntries('form')};
      const ids=es=>es.map(e=>e.id+eventScope(e,context)).join('|');
      return {...common,harmony,orchestration,counterpoint,form,moduleRelations:profile?.relations||[],signatures:{
        harmony:JSON.stringify([w?.id||(noPitched?'no-pitched':'unlocated'),contexts.map(c=>c.id),ids(harmony.contextualEvents)]),
        orchestration:JSON.stringify([parts.map(p=>[p.part_id,p.pitches,p.roles]),orchestration.observedRoles.map(c=>c.id),
          transitions.entered.map(p=>p.part_id),transitions.exited.map(p=>p.part_id),ids(orchestration.contextualEvents)]),
        counterpoint:JSON.stringify([counterpoint.localRelations,ids(counterpoint.contextualEvents),counterpoint.moduleEntries.map(e=>e.id)]),
        form:JSON.stringify([sections.map(s=>s.id),ids(form.contextualEvents),form.moduleEntries.map(e=>e.id)])}};
    }
  };
}
