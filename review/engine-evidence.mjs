import {node} from './research-ui.mjs';

const parts={'flute':'长笛','piccolo':'短笛','oboe':'双簧管','english-horn':'英国管',
  'clarinet-eb':'降E调单簧管','clarinet-a':'A调单簧管','bass-clarinet-a':'A调低音单簧管',
  'bassoon':'巴松','contrabassoon':'低音巴松','horn':'圆号','trumpet':'小号','trombone':'长号',
  'tuba':'大号','timpani':'定音鼓','piano':'钢琴','harp':'竖琴','violin-1':'第一小提琴',
  'violin-2':'第二小提琴','viola':'中提琴','cello':'大提琴','double-bass':'低音提琴'};
const roleNames={Melody:'主旋律候选',Countermelody:'副旋律候选',Bass:'低音支撑',
  'Harmonic Support':'和声填充',Ostinato:'固定音型候选','Rhythmic Drive':'节奏推动',Pedal:'持续支点候选',Doubling:'加倍',Undetermined:'职责待判'};
const names=['C','C♯','D','E♭','E','F','F♯','G','A♭','A','B♭','B'];
const pitch=p=>p==null?'无':names[((p%12)+12)%12]+(Math.floor(p/12)-1);
const inversion=['原位','第一转位','第二转位','第三转位'];
const qualities={major:'大三和弦',minor:'小三和弦',diminished:'减三和弦',augmented:'增三和弦',dominant7:'属七形态',major7:'大七形态',minor7:'小七形态',half_diminished7:'半减七形态',diminished7:'减七形态'};
const relations={unison_or_octave_doubling:'同音／八度加倍候选',parallel_interval_support:'平行音程支撑候选',rhythmically_differentiated_layers:'节奏分层候选',register_projection_relationship:'音域投影关系候选'};
function describeSonority(target,label,s){
  if(!s)return;
  target.append(node('p',`${label}：${s.pitch_classes.map(p=>names[p]).join('、')}；低音 ${pitch(s.bass)}。`));
  for(const candidate of s.candidates||[])target.append(node('p',
    `形态候选：根音${names[candidate.root_pc]} · ${qualities[candidate.quality]||candidate.quality} · ${inversion[candidate.inversion_index]}；功能仍须语境判定。`));
  for(const candidate of s.candidates||[])for(const context of candidate.roman_candidates||[])target.append(node('p',
    `竞争语境：${context.context} → ${context.roman}（尚未确立局部调性或终止功能）。`));
}
export function appendEngineEvidence(target,payload){
  target.replaceChildren(node('h4','谱面观测与符号证据'));
  target.append(node('p','位置来自100页重排谱，分歧处须与杜兰扫描谱对照。音高解码、MIDI对应和时值分别保留为候选；震音展开可共享一个记谱音头，不代表每次攻击都写有独立音头。下列不是录音中已逐音确认的声响。','analysis-note'));
  for(const review of payload.case_reviews||[]){
    const section=node('section');section.append(node('h4',review.title),
      node('p','代理读谱抽查记录 · 未升级为人工或专家验收','analysis-note'));
    for(const observation of review.observations||[])section.append(node('p',`谱面观察：${observation}`));
    for(const finding of review.findings)section.append(node('p',finding));
    for(const uncertainty of review.unresolved)section.append(node('p',`仍待核查：${uncertainty}`,'analysis-note'));
    target.append(section);
  }
  if(payload.review_warning)target.append(node('p',`补充读谱记录未采用：${payload.review_warning}`,'analysis-note'));
  const facts=payload.facts,notes=facts.notes,ppq=payload.ppq||480;
  const scroll=node('div',null,'harmonic-table'),table=node('table'),header=node('tr');
  for(const title of ['乐器','实音／记谱候选','PDF位置','键时值／延音','核查状态'])header.append(node('th',title));
  table.append(header);let shown=0;
  function more(){
    for(const n of notes.slice(shown,shown+24)){
      const row=node('tr'),where=n.score_locations.map(l=>`${l.page}页·系统${l.physical_system_index+1}·x${l.x_pt}`).join('；');
      row.setAttribute('title',n.id||'');
      const written=[...new Set(n.score_locations.map(l=>l.written_spelling_candidate).filter(Boolean))].join('、');
      for(const value of [parts[n.part_id]||n.part_id,pitch(n.pitch)+(written?'／'+written:''),where||'未定位',
        `${((n.key_end_tick-n.start_tick)/ppq).toFixed(3)}／${((n.sounding_end_tick-n.start_tick)/ppq).toFixed(3)} ♩`,
        !n.score_locations.length?'待对应':!n.correspondence.octave_agrees?'八度存在分歧':
          n.correspondence.status==='tremolo_realization_candidate'?'震音展开候选（共享记谱音）':
          n.correspondence.onset_not_located?'延续音候选（起音未定位）':'音高对应候选'])row.append(node('td',value));
      table.append(row);
    }
    shown=Math.min(notes.length,shown+24);button.textContent=`继续查看音符（已显示${shown}/${notes.length}）`;button.hidden=shown===notes.length;
  }
  const button=node('button');button.onclick=more;more();scroll.append(table);target.append(scroll,button);
  const derivation=node('section');derivation.append(node('h4','理论推导与关系'));
  for(const record of payload.derivations){
    if(record.sonority){
      describeSonority(derivation,'CC64延音模型层',record.sonority);
      describeSonority(derivation,'按键层（MIDI note-on/off模型）',record.key_held_sonority);
      derivation.append(node('p',`踏板余音候选：${record.pedal_residue_note_ids?.length||0}条。两层的最低音不能混称。`));
    }
    if(record.entered)derivation.append(node('p',`进入：${record.entered.map(id=>parts[id]||id).join('、')||'无'}；退出：${record.exited.map(id=>parts[id]||id).join('、')||'无'}。`));
    if(record.instruments)for(const instrument of record.instruments)derivation.append(node('p',
      `${parts[instrument.part_id]||instrument.part_id}：${instrument.roles.map(r=>roleNames[r.role]||r.role).join('、')}；均为职责假设。`));
    if(record.stream_ids)derivation.append(node('p',`${record.stream_ids.join(' ↔ ')}：${relations[record.kind]||record.kind}；同时音程（半音）${record.simultaneous_intervals_semitones.join('、')}。`));
    if(record.motions?.length)derivation.append(node('p',`运动证据：${record.motions.map(m=>`${m.a_semitones}/${m.b_semitones} (${m.type})`).join('；')}`));
    if(record.signals)derivation.append(node('p',`边界证据：${Object.keys(record.signals).join('、')}；${record.status}。`));
    if(record.level)derivation.append(node('p',`结构层级：${record.level}；功能：${record.function}；${record.status||''}。`));
  }
  target.append(derivation,node('h4','相关原谱标记（位置及归属仍可复核）'));
  if(payload.hierarchy?.length){
    const levels={work:'作品',movement:'乐章',section:'结构区间候选',phrase:'含动机片段',motif:'动机轮廓'};
    target.append(node('h4','结构层级与材料对应'));
    for(const unit of payload.hierarchy.slice(0,12))target.append(node('p',`${levels[unit.level]||unit.level}：${unit.id}；${unit.function||'主题身份待判'}`));
    target.append(node('p',`该区间保存${payload.hierarchy.length}个层级节点；片段节点不代表完整乐句已经确定。`));
    for(const motif of (payload.motif_patterns||[]).slice(0,3)){
      target.append(node('p',`轮廓${motif.id}：音程（半音）${motif.intervals_semitones.join('、')}；相邻起音间隔比例${motif.ioi_ratios.join(' : ')}。`));
      const w=motif.witnesses[0];if(w)target.append(node('p',`${parts[w.prototype.part_id]||w.prototype.part_id} ${w.prototype.pitches.map(pitch).join('–')} → ${parts[w.answer.part_id]||w.answer.part_id} ${w.answer.pitches.map(pitch).join('–')}；移调${w.transposition_semitones}半音，入口相差${w.entrance_delay_ticks/ppq}个参考四分音符。不能仅据此认定同一主题或严格模仿。`));
    }
  }
  const marks=facts.written_marks||[];
  target.append(node('p',marks.slice(0,18).map(m=>`${m.page}页 ${parts[m.part_id]||m.part_id}：${m.value}`).join('；')||'此证据集中没有可读取的相关标记。'));
  target.append(node('h4','不确定项与竞争解释'));
  for(const text of payload.uncertainties)target.append(node('p',text,'analysis-note'));
}
