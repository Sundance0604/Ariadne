import {node} from './research-ui.mjs';
const roles={'lowest-register support':'最低音区支撑','highest-register layer; melody not inferred from height alone':'最高音区层（旋律身份另核）',
  'sustained layer':'持续层','active figuration or repeated attacks':'活动音型／重复攻击','unpitched rhythmic or colour layer':'非定音节奏／音色层'};

function table(parent,head,rows){
  const scroll=node('div',null,'harmonic-table'),table=node('table'),thead=node('thead'),tr=node('tr');
  for(const title of head)tr.append(node('th',title));thead.append(tr);table.append(thead);
  const body=node('tbody');for(const row of rows){const tr=node('tr');for(const text of row)tr.append(node('td',String(text??'')));body.append(tr);}
  table.append(body);scroll.append(table);parent.append(scroll);
}

export function createMusicXMLReader({onNavigate}={}){
  let root=document.getElementById('musicxml-reader'),version=0,track=null;
  // Keep older DOM fixtures and tracks without XML compatible.
  if(!root)return {reset(){},load(){}};
  const select=node('select'),button=node('button','查看该小节'),state=node('p'),body=node('div');
  select.setAttribute('aria-label','MusicXML小节');root.append(node('h3','完整管弦乐谱面数据'),select,button,state,body);
  function section(title){const d=node('details');d.append(node('summary',title));body.append(d);return d;}
  button.onclick=async()=>{
    const current=++version;state.textContent='正在读取谱面证据…';
    try{
      const response=await fetch(`/api/musicxml-evidence?track=${encodeURIComponent(track)}&measure_id=${encodeURIComponent(select.value)}`,{cache:'no-store'}),d=await response.json();
      if(current!==version)return;if(!response.ok)throw Error(d.error||'读取失败');
      body.replaceChildren();state.textContent=`第${d.measure.number}小节 · PDF第${d.measure.page}页 · XML谱面时值；人工签核待完成。此选择不改变播放位置。`;
      if(onNavigate){const page=node('button','查看对应谱页（不跳转录音）');page.onclick=()=>onNavigate({page:d.measure.page,canSeek:false,time:null});body.append(page);}
      const names=new Map(d.part_registry.map(p=>[p.id,p.name]));
      const instruments=new Map(d.part_registry.flatMap(p=>(p.score_instruments||[]).map(i=>[i.id,i.name])));
      const h=section('和声、低音与转位');h.open=true;
      h.append(node('p','显示小节内各记谱时值窗口。转位0/1/2/3表示原位/第一/第二/第三转位。级数以局部调性假设为条件；踏板余响不由音符时值代替。'));
      table(h,['起点（四分音符）','音名／结构','低音','转位','条件性级数'],d.harmony.map(w=>[
        w.onset_q,(d.harmonic_readings?.[w.id]||[]).map(r=>r.label).join('；另一读法：')||w.sonority.label,w.sonority.bass?.name,w.sonority.chord?.inversion??'不作单一判定',
        d.harmonic_readings?.[w.id]?.flatMap(r=>r.functions.map(k=>`${k.context}: ${k.figure}`)).join('；')||w.roman_hypotheses.map(k=>`${k.context}: ${k.roman}`).join('；')||'不强加级数']));
      const o=section('乐器活动、音域与职责依据');
      table(o,['分部','实音音域','活动／职责依据','记谱奏法'],(d.orchestration[0]?.parts||[]).map(p=>[
        p.name+((p.instrument_refs||[]).length?' / '+p.instrument_refs.map(id=>instruments.get(id)||id).join('、'):''),
        p.range?.join('–')||'非定音',p.role_observations.map(r=>roles[r]||r).join('；'),p.written_techniques.join('；')]));
      const cp=section('声部关系与音程见证');
      cp.append(node('p',`${d.intervals.length}条独立单音声部对见证；${d.chordal_intervals.length}组和弦／分部攻击另存。平行五八度不自动判作错误。`));
      table(cp,['声部','实音','音程','谱面起止'],d.intervals.slice(0,100).map(r=>[
        r.voices.map(v=>`${names.get(v.split(':')[0])} ${v.split(':')[1]}`).join(' / '),r.pitches.join(' / '),r.interval,`${r.start_q}–${r.end_q}`]));
      if(d.intervals.length>100)cp.append(node('p','上表列前100条；全部记录可通过下方完整证据链接查看。'));
      const form=section('曲式层级、动机与终止证据');
      for(const u of d.hierarchy)form.append(node('p',`${u.level} · ${u.title}：${u.argument}`));
      form.append(node('p',`本小节相关动机比较${d.motif_comparisons.length}组，终止候选${d.cadences.length}项；候选不等于已确认的主题或终止。`));
      const ns=section('逐音符号底稿（含被隔离的源事件）');
      table(ns,['分部／声部','记谱音','实音','起点／时值','连音／审核'],d.events.map(e=>[
        `${names.get(e.part_id)}${e.instrument_ref?' / '+(instruments.get(e.instrument_ref)||e.instrument_ref):''} v${e.voice} / 谱表${e.staff}`,e.written_pitch?.name||e.kind,e.concert_pitch?.name||'',
        `${e.onset_q} / ${e.duration_q}`,e.exclusion_reason||e.tie.join('+')]));
      const link=node('a','本小节完整证据（含源音符ID与全部中间判断）');link.href=`/api/musicxml-evidence?track=${encodeURIComponent(track)}&measure_id=${encodeURIComponent(select.value)}`;link.target='_blank';link.rel='noopener noreferrer';body.append(link);
    }catch(error){if(current===version)state.textContent=`谱面证据未载入：${error.message}`;}
  };
  return {reset(){version++;track=null;root.hidden=true;select.replaceChildren();body.replaceChildren();state.textContent='';},
    load(data,trackId){version++;track=trackId;root.hidden=!data.musicxml;if(!data.musicxml)return;
      select.replaceChildren();for(const m of data.musicxml.measures){const option=node('option',`m.${m.number} · PDF ${m.page}页`);option.value=m.measure_id;select.append(option);}select.value=data.musicxml.measures[0]?.measure_id;
      state.textContent=`${data.musicxml.summary.measures}小节已解析。可独立查阅，不要求录音或MIDI逐音匹配。`;}};
}
