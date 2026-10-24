import {buildPlaybackRegions,playheadPosition} from '/playhead.mjs';
import {createAnalysisPanel} from '/analysis.mjs';

const $=id=>document.getElementById(id),audio=$('audio');
let project=null,mapping=new Map(),playbackRegions=new Map(),current=0,page=1,pageCount=0;
let draft=[],undoStack=[],activeButton=null,animationFrame=null,track=null,loadVersion=0;
const unsaved=new Map();
const format=t=>`${Math.floor(t/60)}:${(t%60).toFixed(2).padStart(5,'0')}`;
const endpoint=path=>`${path}?track=${encodeURIComponent(track)}`;
const analysisPanel=createAnalysisPanel(id=>{if(!project)return;const i=project.measures.findIndex(m=>m.measure_id===id);if(i>=0)choose(i,true);});
new ResizeObserver(()=>document.documentElement.style.setProperty('--toolbar-height',document.querySelector('.toolbar').getBoundingClientRect().height+'px')).observe(document.querySelector('.toolbar'));
const messages={feature_variant_disagreement_over_2s:'两组特征的起点估计相差超过 2 秒',partial_final_bar:'MIDI 在末小节时值结束前终止',recording_edge_requires_listening:'录音首尾需要人工试听确认',cadenza_pdf_region_has_no_separate_barlines:'华彩：几个 MIDI 小节共用无独立小节线的谱面区域',pdf_coordinate_missing:'尚缺对应谱面坐标',pdf_geometry_extends_past_page:'谱线略超出页面底边，需要检查裁切',weak_independent_pitch_evidence:'音高支持较弱，需要试听核对',insufficient_pitched_reference:'此段有音高音符不足，不能用音高相似度判断同步'};
messages.meter_change_inside_bar='参考文件在候选小节内部换拍，分节位置需要核对';
messages.shared_pdf_region_requires_review='多个候选小节共用谱面区域，位置需要人工核对';
messages.pdf_region_boundary_candidate='谱面与参考文件的分段不同，区域边界仍需核对';
function controls(enabled){
  for(const id of ['previous','next','go','jump','pageprev','pagenext','anchor','undo','save','export','speed'])$(id).disabled=!enabled;
}
function showPage(n){
  if(!project)return;
  page=Math.max(1,Math.min(pageCount,n));$('score').src=endpoint(`/page/${page}.png`);
  $('pagelabel').textContent=`原始 PDF · 第 ${page} / ${pageCount} 页`;highlight();updatePlayhead();
}
function highlight(){
  if(!project)return;
  const box=mapping.get(project.measures[current].measure_id),node=$('highlight');
  node.hidden=!box||box.page_number!==page;if(node.hidden)return;
  const [x,y,w,h]=box.rect_pt;
  Object.assign(node.style,{left:`${x/box.page_width_pt*100}%`,top:`${y/box.page_height_pt*100}%`,width:`${w/box.page_width_pt*100}%`,height:`${h/box.page_height_pt*100}%`});
}
function choose(index,seek=false){
  if(!project||!Number.isFinite(index))return;
  current=Math.max(0,Math.min(project.measures.length-1,Math.floor(index)));
  const m=project.measures[current],box=mapping.get(m.measure_id);
  $('jump').value=current+1;$('current').textContent=`候选第 ${current+1} 小节`;
  $('interval').textContent=`${format(m.start_seconds)} – ${format(m.end_seconds)}`;
  const scope=box?.resolution==='bar'?'':box?.resolution?.includes('cadenza')?' · 华彩共用区域':' · 系统／乐句候选区域';
  $('location').textContent=box?`PDF 第 ${box.page_number} 页${scope}`:'尚无坐标 · 谱页位置待核对';
  $('status').textContent=m.flags.length?'需要重点复核':'尚未人工复核';
  $('notice').textContent=[...new Set(m.flags.map(f=>messages[f]||'该区域需要人工核对，详见本曲处理报告'))].join('\n');
  activeButton?.classList.remove('active');activeButton=$('list').children[current];activeButton?.classList.add('active');
  if(box&&$('follow').checked&&box.page_number!==page)showPage(box.page_number);else highlight();
  if(seek)audio.currentTime=m.start_seconds;
  updatePlayhead();analysisPanel.update(box?.page_number);
}
function updatePlayhead(){
  if(!project)return;
  const m=project.measures[current],box=mapping.get(m.measure_id),region=playbackRegions.get(m.measure_id);
  const position=playheadPosition(project.time_map,audio.currentTime,box,region),line=$('playhead');
  line.hidden=!position||box.page_number!==page||!$('showplayhead').checked;
  if(!position){$('playheadlabel').textContent='暂无位置估计';return;}
  if(!line.hidden)line.style.left=`${position.leftPercent}%`;
  const scope=box.resolution==='bar'?'小节内':box.resolution?.includes('cadenza')?'华彩区域':'候选区域';
  $('playheadlabel').textContent=box.page_number!==page?'当前页不是播放页':`${scope}估计位置 · ${Math.round(position.fraction*100)}%`;
}
function syncPlaybackPosition(){
  if(!project)return;
  let lo=0,hi=project.measures.length;
  while(lo<hi){const mid=(lo+hi)>>1;if(project.measures[mid].start_seconds<=audio.currentTime+.001)lo=mid+1;else hi=mid;}
  const index=Math.max(0,lo-1);if(index!==current)choose(index);updatePlayhead();
}
function animatePlayhead(){syncPlaybackPosition();animationFrame=!audio.paused&&!audio.ended?requestAnimationFrame(animatePlayhead):null;}
function stopAnimation(){if(animationFrame!==null)cancelAnimationFrame(animationFrame);animationFrame=null;syncPlaybackPosition();}
async function loadTrack(id){
  if(project&&track)unsaved.set(track,{draft:structuredClone(draft),undoStack:structuredClone(undoStack),reason:$('reason').value,
    audioHash:project.audio.sha256,scoreHash:project.symbolic_reference.sha256});
  const version=++loadVersion;audio.pause();stopAnimation();project=null;track=id;current=0;page=1;pageCount=0;
  audio.removeAttribute('src');audio.load();controls(false);analysisPanel.reset(null);
  $('score').removeAttribute('src');$('highlight').hidden=true;$('playhead').hidden=true;
  $('list').replaceChildren();activeButton=null;$('current').textContent='正在载入';$('status').textContent='算法候选';
  $('pagelabel').textContent='正在载入曲目…';$('toast').textContent='';$('notice').textContent='';$('reason').value='';
  try{
    const response=await fetch(endpoint('/api/project'),{cache:'no-store'}),data=await response.json();
    if(version!==loadVersion)return;
    if(!response.ok)throw Error(data.error||'项目读取失败');
    project=data.alignment;mapping=new Map(data.mapping.measures.map(m=>[m.measure_id,m]));
    pageCount=data.page_count;playbackRegions=buildPlaybackRegions(project.measures,mapping);
    let retained=unsaved.get(track);
    if(retained&&(retained.audioHash!==project.audio.sha256||retained.scoreHash!==project.symbolic_reference.sha256)){
      unsaved.delete(track);retained=null;
    }
    draft=retained?.draft||data.anchors?.anchors||[];undoStack=retained?.undoStack||[];
    $('reason').value=retained?.reason||'';$('jump').max=project.measures.length;$('jump').value=1;
    $('work-title').textContent=data.track.title;document.title=`${data.track.title} · 曲谱同步`;
    $('review-summary').textContent=`${project.measures.length} 个候选小节尚未完成人工试听验收。原谱定位、播放线位置与分析内容分别保留复核状态。`;
    const list=document.createDocumentFragment();
    project.measures.forEach((m,i)=>{const b=document.createElement('button');b.textContent=`${i+1} · ${format(m.start_seconds)}`;b.className=m.flags.length?'flag':'';b.onclick=()=>choose(i,true);list.append(b);});
    $('list').append(list);audio.src=endpoint('/audio');audio.load();audio.playbackRate=Number($('speed').value);
    analysisPanel.load(track);showPage(1);choose(0);controls(true);
    $('toast').textContent=retained?`已恢复本页暂存的 ${draft.length} 个锚点`:`已载入 ${draft.length} 个人工锚点`;
    const url=new URL(location.href);url.searchParams.set('track',track);history.replaceState(null,'',url);
  }catch(error){if(version===loadVersion){$('pagelabel').textContent=`无法载入：${error.message}`;$('toast').textContent='可选择其他曲目后重试';}}
}
$('previous').onclick=()=>choose(current-1,true);$('next').onclick=()=>choose(current+1,true);
$('go').onclick=()=>choose(Number($('jump').value)-1,true);$('jump').onkeydown=e=>{if(e.key==='Enter')$('go').click();};
$('pageprev').onclick=()=>showPage(page-1);$('pagenext').onclick=()=>showPage(page+1);
$('follow').onchange=()=>choose(current);$('speed').onchange=()=>audio.playbackRate=Number($('speed').value);
audio.ontimeupdate=()=>{$('clock').textContent=format(audio.currentTime);syncPlaybackPosition();};
audio.onplay=()=>{if(animationFrame===null)animationFrame=requestAnimationFrame(animatePlayhead);};
audio.onpause=stopAnimation;audio.onended=stopAnimation;audio.onseeking=syncPlaybackPosition;audio.onseeked=syncPlaybackPosition;
$('showplayhead').onchange=updatePlayhead;$('score').onload=updatePlayhead;
$('anchor').onclick=()=>{
  if(!project)return;const m=project.measures[current],reason=$('reason').value.trim();
  if(!current){$('toast').textContent='全曲端点请在局部试听后专项处理';return;}
  if(!reason){$('toast').textContent='请填写校正依据';return;}
  undoStack.push(structuredClone(draft));draft=draft.filter(a=>a.measure_id!==m.measure_id);
  draft.push({measure_id:m.measure_id,midi_seconds:m.midi_start_seconds,audio_seconds:audio.currentTime,original_audio_seconds:m.start_seconds,reason,source:'human',review_status:'corrected',modified_at:new Date().toISOString()});
  draft.sort((a,b)=>a.midi_seconds-b.midi_seconds);$('toast').textContent=`起点 ${format(audio.currentTime)} 已暂存；共 ${draft.length} 个锚点，等待保存与重新计算`;
};
$('undo').onclick=()=>{if(undoStack.length){draft=undoStack.pop();$('toast').textContent=`已撤销；当前 ${draft.length} 个锚点`;}};
$('save').onclick=async()=>{
  if(!project)return;const version=loadVersion;
  try{
    const response=await fetch(endpoint('/api/anchors'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({track_id:track,audio_sha256:project.audio.sha256,score_sha256:project.symbolic_reference.sha256,anchors:draft})});
    const data=await response.json();if(!response.ok)throw Error(data.error);
    if(version===loadVersion)$('toast').textContent='已保存当前曲目的人工锚点；重新计算后生效';
  }catch(error){if(version===loadVersion)$('toast').textContent=error.message;}
};
$('export').onclick=()=>{
  if(!project)return;
  const url=URL.createObjectURL(new Blob([JSON.stringify({track_id:track,alignment:project,measure_map:[...mapping.values()],draft_anchors:draft,analysis:analysisPanel.exportData()},null,2)],{type:'application/json'}));
  const a=document.createElement('a');a.href=url;a.download=`${track}-sync-review.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),5000);
};
$('track').onchange=()=>loadTrack($('track').value);
controls(false);
async function initialize(){
  const response=await fetch('/api/library',{cache:'no-store'});if(!response.ok)throw Error('曲库读取失败');
  const catalog=await response.json();
  for(const item of catalog.tracks){const option=document.createElement('option');option.value=item.id;option.textContent=item.title;$('track').append(option);}
  const requested=new URL(location.href).searchParams.get('track');
  $('track').value=catalog.tracks.some(t=>t.id===requested)?requested:catalog.default_track;
  await loadTrack($('track').value);
}
initialize().catch(error=>{$('pagelabel').textContent=error.message;});
