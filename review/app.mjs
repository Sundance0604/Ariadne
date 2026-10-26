import {buildPlaybackRegions,playheadPosition} from '/playhead.mjs';
import {createAnalysisPanel} from '/analysis.mjs';
import {PlaybackController} from '/playback.mjs';
import {prepareScoreRegions,scoreRegionAt,scoreRegionAtPoint} from '/score-follow.mjs';
import {movementChapters,chapterAtTime} from '/movements.mjs';
import {createMeasureNumberPanel,measureNumberLabel} from '/measure-numbers.mjs';
import {createResearchPanel} from '/research.mjs';

const $=id=>document.getElementById(id);
const audio=new PlaybackController($('audio'),$('video'),message=>$('media-state').textContent=message);
let project=null,mapping=new Map(),playbackRegions=new Map(),current=0,page=1,pageCount=0;
let draft=[],undoStack=[],activeButton=null,animationFrame=null,track=null,loadVersion=0;
let scoreRegions=[],activeScoreRegion=null,lastFollowedRegion=null;
let scoreMapDocument=null,scoreCorrections=null;
let scoreMeasures=null;
let chapters=[],chapterButtons=[];
const unsaved=new Map();
const format=t=>`${Math.floor(t/60)}:${(t%60).toFixed(2).padStart(5,'0')}`;
const endpoint=path=>`${path}?track=${encodeURIComponent(track)}`;
const analysisPanel=createAnalysisPanel((id,pdfPage,note)=>{
  if(!project)return;
  if(note?.locator_precision==='score_segment'){
    analysisPanel.follow();audio.currentTime=note.start_seconds;syncPlaybackPosition();
    showPage(pdfPage,true);updateTransport();return;
  }
  const i=project.measures.findIndex(m=>m.measure_id===id);if(i>=0)choose(i,true);
  if(pdfPage&&!mapping.size&&!scoreRegions.length)showPage(pdfPage);
});
const measureNumberPanel=createMeasureNumberPanel({onLocate:locateNumberedMeasure,onChange:data=>{
  scoreMeasures=data;scoreRegions=prepareScoreRegions(scoreMapDocument,project,scoreCorrections,scoreMeasures);
  activeScoreRegion=null;syncPlaybackPosition();configureScoreReview();
}});
const researchPanel=createResearchPanel({getRegions:()=>scoreRegions,onSelectTab:name=>analysisPanel.selectTab(name),
  onNavigate:navigation=>{
    if(!project||!navigation.page)return;
    if(navigation.canSeek){audio.currentTime=navigation.time;syncPlaybackPosition();updateTransport();showPage(navigation.page);}
    else{$('follow').checked=false;showPage(navigation.page,true);$('toast').textContent='已打开相关谱页 · 音频位置待核查，未改变播放时间；可重新勾选跟随播放。';}
  }});
new ResizeObserver(()=>document.documentElement.style.setProperty('--hud-height',document.getElementById('research-hud-bar').getBoundingClientRect().height+'px')).observe(document.getElementById('research-hud-bar'));
new ResizeObserver(()=>document.documentElement.style.setProperty('--toolbar-height',document.querySelector('.toolbar').getBoundingClientRect().height+'px')).observe(document.querySelector('.toolbar'));
new ResizeObserver(()=>document.documentElement.style.setProperty('--score-nav-height',document.querySelector('.pagebuttons').getBoundingClientRect().height+'px')).observe(document.querySelector('.pagebuttons'));
for(const [selector,variable] of [['header','--header-height'],['.transport','--transport-height']])new ResizeObserver(()=>document.documentElement.style.setProperty(variable,document.querySelector(selector).getBoundingClientRect().height+'px')).observe(document.querySelector(selector));
const messages={feature_variant_disagreement_over_2s:'两组特征的起点估计相差超过 2 秒',partial_final_bar:'MIDI 在末小节时值结束前终止',recording_edge_requires_listening:'录音首尾需要人工试听确认',cadenza_pdf_region_has_no_separate_barlines:'华彩：几个 MIDI 小节共用无独立小节线的谱面区域',pdf_coordinate_missing:'尚缺对应谱面坐标',pdf_geometry_extends_past_page:'谱线略超出页面底边，需要检查裁切',weak_independent_pitch_evidence:'音高支持较弱，需要试听核对',insufficient_pitched_reference:'此段有音高音符不足，不能用音高相似度判断同步'};
messages.meter_change_inside_bar='参考文件在候选小节内部换拍，分节位置需要核对';
messages.shared_pdf_region_requires_review='多个候选小节共用谱面区域，位置需要人工核对';
messages.pdf_region_boundary_candidate='谱面与参考文件的分段不同，区域边界仍需核对';
messages.movement_boundary_requires_listening='乐章边界与现场停顿需要人工试听确认';
messages.long_interval_check_cadenza_or_fermata='此处间隔较长，请检查停顿、延长或片头';
function controls(enabled){
  for(const id of ['previous','next','go','jump','pageprev','pagenext','anchor','undo','save','export','speed'])$(id).disabled=!enabled;
}
function showPage(n,browse=false){
  if(!project)return;
  page=Math.max(1,Math.min(pageCount,n));$('score').src=endpoint(`/page/${page}.png`);
  if(browse)analysisPanel.browse(page);else analysisPanel.follow();
  measureNumberPanel.renderPage(page);
  $('pagelabel').textContent=`原始 PDF · 第 ${page} / ${pageCount} 页`;highlight();updatePlayhead();
}
function locateNumberedMeasure(measure){
  const region=scoreRegions.find(r=>r.region_id===measure.region_id);
  if(region){
    audio.loop=null;$('loop').checked=false;analysisPanel.follow();
    audio.currentTime=region.audioStart;syncPlaybackPosition();updateTransport();
  }
  showPage(measure.page_number,!region);
  $('score-region-select').value=measure.region_id;loadScoreReview();
  $('measure-jump-movement').value=measure.movement;$('measure-jump-number').value=measure.score_measure_number;
  $('toast').textContent=region?`已定位到第 ${measure.movement} 乐章 · 小节 ${measureNumberLabel(measure)}；时间仍需试听核对。`:'已定位谱面；此小节暂缺录音时间，可在区域时间校正中补充。';
}
function scoreLocation(region){
  if(Number.isFinite(region.score_measure_number))return `PDF 第 ${region.page_number} 页 · 小节 ${measureNumberLabel(region)}`;
  return `PDF 第 ${region.page_number} 页 · ${region.printed_measure_number!=null?'原谱小节 '+region.printed_measure_number:'系统／乐句区域'}`;
}
function highlight(){
  if(!project)return;
  const box=scoreRegions.length?activeScoreRegion:mapping.get(project.measures[current].measure_id),node=$('highlight');
  node.hidden=!box||box.page_number!==page;if(node.hidden)return;
  const [x,y,w,h]=box.rect_pt;
  Object.assign(node.style,{left:`${x/box.page_width_pt*100}%`,top:`${y/box.page_height_pt*100}%`,width:`${w/box.page_width_pt*100}%`,height:`${h/box.page_height_pt*100}%`});
  const uncertain=box.review_status==='needs_review'||scoreRegions.length&&!box.manual_timing&&timingNeedsReview();
  node.style.borderColor=uncertain?'#c54242':'#bd7c19';
  node.style.background=uncertain?'#d9454522':'#e9b54229';
}
function revealPlayingRegion(){
  if(!$('follow').checked||$('highlight').hidden)return;
  const pane=document.querySelector('.score-scroll'),node=$('highlight');
  const target=node.getBoundingClientRect(),view=pane.getBoundingClientRect();
  // Keep the current system's top staff visible when the full orchestra is
  // taller than the viewport. Never repeatedly fight a reader's scrolling.
  if(target.top<view.top+12||target.top>view.bottom-60||target.bottom<view.top)
    pane.scrollTop+=target.top-view.top-18;
  if(target.right<view.left||target.left>view.right-30)pane.scrollLeft+=target.left-view.left-18;
}
function syncScoreRegion(){
  if(!scoreRegions.length||!project)return false;
  const next=scoreRegionAt(scoreRegions,audio.currentTime,$('stable-regions')?.checked||false),changed=next?.region_id!==activeScoreRegion?.region_id;
  activeScoreRegion=next;
  measureNumberPanel.activate(next);
  if(!changed)return false;
  if(next&&$('follow').checked&&next.page_number!==page)showPage(next.page_number);else highlight();
  if(next){
    $('location').textContent=scoreLocation(next);
    if(lastFollowedRegion!==next.region_id){lastFollowedRegion=next.region_id;requestAnimationFrame(revealPlayingRegion);}
  }else{
    $('location').textContent='此处不在已定位的原谱区域内';lastFollowedRegion=null;
  }
  updatePlayhead();
  renderScoreStatus();
  return changed;
}
function renderScoreStatus(){
  if(!scoreRegions.length)return;
  const region=activeScoreRegion;
  if(!region){$('status').textContent='当前区间未启用高亮';$('media-state').textContent='此处暂无满足当前筛选条件的谱面区域；不外推猜测位置。';return;}
  const scope=Number.isFinite(region.score_measure_number)?`小节 ${measureNumberLabel(region)}`:region.resolution==='bar_candidate'?'小节候选':`系统 ${region.system_index+1}`;
  $('current').textContent=`第 ${region.page_number} 页 · ${scope}`;
  $('status').textContent=region.manual_timing?'已人工校正':!region.stable_candidate?'定位待复核':timingNeedsReview()?'时间待试听复核':'自动候选 · 待试听';
  $('media-state').textContent=region.manual_timing?'当前区域使用已保存的人工时间校正。':region.stable_candidate?
    (timingNeedsReview()?'此处音轨对应关系需要试听复核；谱面边界仍为自动候选。':'自动高亮候选：参数对照较稳定，仍未逐音验收。'):'当前区域匹配分歧较大，红框仅供复核；可选择“仅显示稳定候选”隐藏。';
}
function timingNeedsReview(){
  return Boolean(project?.measures[current]?.flags.some(flag=>['feature_variant_disagreement_over_2s',
    'weak_independent_pitch_evidence','recording_edge_requires_listening',
    'long_interval_check_cadenza_or_fermata','movement_boundary_requires_listening'].includes(flag)));
}
function choose(index,seek=false){
  if(!project||!Number.isFinite(index))return;
  current=Math.max(0,Math.min(project.measures.length-1,Math.floor(index)));
  const m=project.measures[current];
  if(seek){analysisPanel.follow();audio.currentTime=m.start_seconds;}
  syncScoreRegion();
  const box=scoreRegions.length?activeScoreRegion:mapping.get(m.measure_id);
  $('jump').value=current+1;$('current').textContent=scoreRegions.length?`MIDI 参考段 ${current+1}`:`候选第 ${current+1} 小节`;
  $('interval').textContent=`${format(m.start_seconds)} – ${format(m.end_seconds)}`;
  const scope=box?.resolution==='bar'?'':box?.resolution?.includes('cadenza')?' · 华彩共用区域':' · 系统／乐句候选区域';
  $('location').textContent=box?scoreLocation(box):'尚无坐标 · 谱页位置待核对';
  $('status').textContent=m.flags.length?'需要重点复核':'尚未人工复核';
  $('notice').textContent=[...new Set(m.flags.map(f=>messages[f]||'该区域需要人工核对，详见本曲处理报告'))].join('\n');
  activeButton?.classList.remove('active');activeButton=$('list').children[current];activeButton?.classList.add('active');
  if(box&&$('follow').checked&&box.page_number!==page)showPage(box.page_number);else highlight();
  if(box&&$('follow').checked&&seek)requestAnimationFrame(revealPlayingRegion);
  updatePlayhead();
  renderScoreStatus();
}
function updatePlayhead(){
  if(!project)return;
  const m=project.measures[current],box=scoreRegions.length?activeScoreRegion:mapping.get(m.measure_id),
    region=scoreRegions.length?activeScoreRegion:playbackRegions.get(m.measure_id);
  const position=playheadPosition(project.time_map,audio.currentTime,box,region),line=$('playhead');
  analysisPanel.update(box?.page_number,m.sequence_index,{page,time:audio.currentTime,
    ...(box?.page_number===page?{system_index:box.system_index??0,
      x_pt:position?position.leftPercent/100*box.page_width_pt:box.rect_pt[0]}:{})});
  researchPanel.update({playingPage:box?.page_number??null,browsedPage:page,time:audio.currentTime,
    referenceId:m.measure_id,regionId:box?.region_id,systemIndex:box?.system_index,
    referenceSeconds:position?.referenceSeconds??null,
    x:position&&box?position.leftPercent/100*box.page_width_pt:null});
  line.hidden=!position||box.page_number!==page||!$('showplayhead').checked;
  if(!position){$('playheadlabel').textContent='暂无位置估计';return;}
  if(!line.hidden){
    line.style.left=`${position.leftPercent}%`;
    line.style.top=scoreRegions.length?`${box.rect_pt[1]/box.page_height_pt*100}%`:'0';
    line.style.bottom=scoreRegions.length?'auto':'0';
    line.style.height=scoreRegions.length?`${box.rect_pt[3]/box.page_height_pt*100}%`:'auto';
  }
  const scope=['bar','bar_candidate','numbered_bar_candidate'].includes(box.resolution)?'小节内':box.resolution?.includes('cadenza')?'华彩区域':'候选区域';
  $('playheadlabel').textContent=box.page_number!==page?'当前页不是播放页':`${scope}估计位置 · ${Math.round(position.fraction*100)}%`;
}
function syncPlaybackPosition(){
  if(!project)return;
  let lo=0,hi=project.measures.length;
  while(lo<hi){const mid=(lo+hi)>>1;if(project.measures[mid].start_seconds<=audio.currentTime+.001)lo=mid+1;else hi=mid;}
  const index=Math.max(0,lo-1);if(index!==current)choose(index);else syncScoreRegion();updatePlayhead();
}
function updateTransport(){
  $('progress').max=audio.duration||1;$('progress').value=audio.currentTime;
  $('transport-clock').textContent=`${format(audio.currentTime)} / ${format(audio.duration||0)}`;
  $('play').textContent=audio.paused?'播放':'暂停';
  const chapter=chapterAtTime(chapters,audio.currentTime);
  for(const {node,item} of chapterButtons){const active=item===chapter;node.setAttribute('aria-current',active?'true':'false');}
}
function configureChapters(scoreDocument){
  chapters=movementChapters(project,scoreDocument);chapterButtons=[];
  const nav=$('movement-chapters');nav.replaceChildren();nav.hidden=chapters.length<2;
  for(const item of chapters){
    const node=document.createElement('button');node.type='button';
    node.textContent=`${['I','II','III','IV'][item.movement-1]||item.movement} · 第${item.movement}乐章 ${format(item.start_seconds).split('.')[0]}`;
    node.title=`${item.title} · 跳至乐章起点（同步时间待复核）`;
    node.onclick=()=>{
      audio.loop=null;$('loop').checked=false;
      analysisPanel.follow();audio.currentTime=item.start_seconds;syncPlaybackPosition();
      showPage(item.first_pdf_page);updateTransport();
    };
    chapterButtons.push({node,item});nav.append(node);
  }
}
function animatePlayhead(){audio.tick();syncPlaybackPosition();updateTransport();animationFrame=!audio.paused&&!audio.ended?requestAnimationFrame(animatePlayhead):null;}
function stopAnimation(){if(animationFrame!==null)cancelAnimationFrame(animationFrame);animationFrame=null;syncPlaybackPosition();}
async function loadTrack(id){
  if(project&&track)unsaved.set(track,{draft:structuredClone(draft),undoStack:structuredClone(undoStack),reason:$('reason').value,
    audioHash:project.audio.sha256,scoreHash:project.symbolic_reference.sha256});
  const version=++loadVersion;audio.pause();stopAnimation();project=null;track=id;current=0;page=1;pageCount=0;
  scoreRegions=[];activeScoreRegion=null;lastFollowedRegion=null;
  scoreMapDocument=null;scoreCorrections=null;$('score-region-review').hidden=true;
  scoreMeasures=null;measureNumberPanel.load(null,track);
  if($('stable-regions-label'))$('stable-regions-label').hidden=true;
  audio.reset();controls(false);analysisPanel.reset(null);researchPanel.reset();$('play').disabled=true;
  chapters=[];chapterButtons=[];$('movement-chapters').replaceChildren();$('movement-chapters').hidden=true;
  $('video-panel').hidden=true;$('media-state').textContent='';$('loop').checked=false;
  loopStart=0;loopEnd=0;$('loop-label').textContent='';updateTransport();
  $('score').removeAttribute('src');$('highlight').hidden=true;$('playhead').hidden=true;
  $('list').replaceChildren();activeButton=null;$('current').textContent='正在载入';$('status').textContent='算法候选';
  $('pagelabel').textContent='正在载入曲目…';$('toast').textContent='';$('notice').textContent='';$('reason').value='';
  try{
    const response=await fetch(endpoint('/api/project'),{cache:'no-store'}),data=await response.json();
    if(version!==loadVersion)return;
    if(!response.ok)throw Error(data.error||'项目读取失败');
    project=data.alignment;mapping=new Map((data.symbolic_pdf_regions||data.mapping.measures).map(m=>[m.measure_id,m]));
    scoreMapDocument=data.mapping;scoreCorrections=data.score_region_anchors;
    scoreMeasures=data.score_measures;measureNumberPanel.load(scoreMeasures,track);
    scoreRegions=prepareScoreRegions(data.mapping,project,scoreCorrections,scoreMeasures);
    configureScoreReview();
    $('jump').closest('label').firstChild.textContent=scoreRegions.length?'参考段 ':'小节 ';
    pageCount=data.page_count;playbackRegions=buildPlaybackRegions(project.measures,mapping);
    let retained=unsaved.get(track);
    if(retained&&(retained.audioHash!==project.audio.sha256||retained.scoreHash!==project.symbolic_reference.sha256)){
      unsaved.delete(track);retained=null;
    }
    draft=retained?.draft||data.anchors?.anchors||[];undoStack=retained?.undoStack||[];
    $('reason').value=retained?.reason||'';$('jump').max=project.measures.length;$('jump').value=1;
    $('work-title').textContent=data.track.title;document.title=`${data.track.title} · 曲谱同步`;
    $('review-summary').textContent=`${project.measures.length} 个 MIDI 候选参考段尚未完成人工试听验收。${scoreRegions.length?`${scoreRegions.length} 个原谱区域独立定位；自动高亮与播放线仍需复核。`:data.mapping.measures.length?'原谱定位与播放线位置保留复核状态。':'此扫描谱尚无小节坐标，请手动翻页。'}`;
    const list=document.createDocumentFragment();
    project.measures.forEach((m,i)=>{const b=document.createElement('button');b.textContent=`${i+1} · ${format(m.start_seconds)}`;b.className=m.flags.length?'flag':'';b.onclick=()=>choose(i,true);list.append(b);});
    $('list').append(list);
    audio.configure(data.media,{audio:endpoint('/audio'),video:endpoint('/video')},project.audio.duration_seconds);
    configureChapters(data.mapping);
    audio.playbackRate=Number($('speed').value);audio.volume=Number($('volume').value);
    $('video-panel').hidden=!data.media?.video;$('play').disabled=false;
    $('source').replaceChildren();
    for(const [value,label] of data.media?.masterClock==='video'?[['video','视频音轨']]:data.media?.video?[['audio','独立音频'],['video','视频音轨']]:[['audio','音频']]){
      const option=document.createElement('option');option.value=value;option.textContent=label;$('source').append(option);
    }
    $('source').disabled=!audio.dualReady;
    $('media-sync-editor').hidden=!audio.dual;
    $('sync-points').value=(data.media?.anchors||[]).map(a=>`${a.masterTime},${a.videoTime}`).join('\n');
    $('same-performance').checked=false;$('sync-reason').value='';
    if(data.media?.qualityWarnings?.length)$('media-state').textContent=data.media.qualityWarnings.join(' ');
    if(scoreRegions.length)$('media-state').textContent='自动跟随原谱区域；定位与时间仍保留复核状态。';
    else if(!data.mapping.measures.length){$('notice').textContent='扫描谱小节坐标尚未核验，请手动翻页。';$('media-state').textContent='小节时间为自动候选；扫描谱尚无小节坐标，请手动翻页。';}
    document.body.classList.toggle('has-video',Boolean(data.media?.video));
    analysisPanel.load(track);researchPanel.load(track,data.mapping.pdf_sha256);
    showPage(data.mapping.first_score_page||1);choose(0);controls(true);
    $('toast').textContent=retained?`已恢复本页暂存的 ${draft.length} 个锚点`:`已载入 ${draft.length} 个人工锚点`;
    const url=new URL(location.href);url.searchParams.set('track',track);history.replaceState(null,'',url);
  }catch(error){if(version===loadVersion){$('pagelabel').textContent=`无法载入：${error.message}`;$('toast').textContent='可选择其他曲目后重试';}}
}
$('previous').onclick=()=>choose(current-1,true);$('next').onclick=()=>choose(current+1,true);
$('go').onclick=()=>choose(Number($('jump').value)-1,true);$('jump').onkeydown=e=>{if(e.key==='Enter')$('go').click();};
$('pageprev').onclick=()=>showPage(page-1,true);$('pagenext').onclick=()=>showPage(page+1,true);
$('follow').onchange=()=>{analysisPanel.follow();choose(current);revealPlayingRegion();};$('speed').onchange=()=>audio.playbackRate=Number($('speed').value);
const stableLabel=document.createElement('label');stableLabel.hidden=true;stableLabel.id='stable-regions-label';
const stableToggle=document.createElement('input');stableToggle.type='checkbox';stableToggle.id='stable-regions';
stableLabel.append(stableToggle,document.createTextNode('仅显示稳定候选'));document.querySelector('.pagebuttons').append(stableLabel);
stableToggle.onchange=()=>{activeScoreRegion=null;syncScoreRegion();highlight();updatePlayhead();};
audio.ontimeupdate=()=>{audio.tick();$('clock').textContent=format(audio.currentTime);syncPlaybackPosition();updateTransport();};
audio.onplay=()=>{analysisPanel.follow();choose(current);if(animationFrame===null)animationFrame=requestAnimationFrame(animatePlayhead);};
audio.onpause=()=>{stopAnimation();updateTransport();};audio.onended=audio.onpause;audio.onseeking=syncPlaybackPosition;audio.onseeked=()=>{syncPlaybackPosition();updateTransport();};
audio.onloadedmetadata=updateTransport;
$('play').onclick=()=>audio.paused?audio.play():audio.pause();
$('progress').oninput=()=>{analysisPanel.follow();audio.currentTime=Number($('progress').value);syncPlaybackPosition();updateTransport();};
$('volume').oninput=()=>audio.volume=Number($('volume').value);
$('source').onchange=async()=>{if(!await audio.selectSource($('source').value))$('source').value=audio.master===$('video')?'video':'audio';};
let loopStart=0,loopEnd=0;
$('loop-a').onclick=()=>{loopStart=audio.currentTime;$('loop-label').textContent=`A ${format(loopStart)}`;};
$('loop-b').onclick=()=>{loopEnd=audio.currentTime;$('loop-label').textContent=`A ${format(loopStart)} – B ${format(loopEnd)}`;};
$('loop').onchange=()=>{try{if($('loop').checked)audio.setLoop(loopStart,loopEnd);else audio.loop=null;}catch(error){$('loop').checked=false;$('media-state').textContent=error.message;}};
for(const button of document.querySelectorAll('[data-mode]'))button.onclick=()=>{
  document.body.dataset.mode=button.dataset.mode;
  for(const item of document.querySelectorAll('[data-mode]'))item.setAttribute('aria-pressed',String(item===button));
};
for(const button of document.querySelectorAll('[data-mobile-tab]'))button.onclick=()=>{
  document.body.dataset.mobileTab=button.dataset.mobileTab;
  for(const item of document.querySelectorAll('[data-mobile-tab]'))item.setAttribute('aria-pressed',String(item===button));
};
$('pane-width').oninput=()=>document.documentElement.style.setProperty('--side-width',$('pane-width').value+'%');
$('zoom').oninput=()=>$('sheet').style.width=$('zoom').value+'%';
$('fullscreen').onclick=async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await $('video-panel').requestFullscreen();}catch{$('media-state').textContent='当前浏览器不支持全屏';}};
$('pip').onclick=async()=>{try{if(document.pictureInPictureElement)await document.exitPictureInPicture();else await $('video').requestPictureInPicture();}catch{$('media-state').textContent='当前浏览器不支持视频浮窗，或视频尚未就绪';}};
$('sheet').onclick=event=>{
  if(!project)return;const bounds=$('sheet').getBoundingClientRect(),x=(event.clientX-bounds.left)/bounds.width,y=(event.clientY-bounds.top)/bounds.height;
  if(scoreRegions.length){const region=scoreRegionAtPoint(scoreRegions,page,x,y);if(region){analysisPanel.follow();audio.currentTime=region.audioStart;syncPlaybackPosition();updateTransport();}return;}
  const candidates=[...mapping.values()].filter(box=>{const [l,t,w,h]=box.rect_pt;return box.page_number===page&&x>=l/box.page_width_pt&&x<=(l+w)/box.page_width_pt&&y>=t/box.page_height_pt&&y<=(t+h)/box.page_height_pt;});
  const index=project.measures.findIndex(m=>m.measure_id===candidates[0]?.measure_id);if(index>=0)choose(index,true);
};
window.addEventListener('pagehide',()=>audio.pause());
function configureScoreReview(){
  const selected=$('score-region-select').value;
  $('score-region-review').hidden=!scoreRegions.length;
  if($('stable-regions-label'))$('stable-regions-label').hidden=!scoreRegions.length;
  $('score-region-select').replaceChildren();
  for(const region of scoreRegions){const option=document.createElement('option');option.value=region.region_id;
    option.textContent=`第${region.page_number}页 · 系统${region.system_index+1}${Number.isFinite(region.score_measure_number)?' · 小节 '+measureNumberLabel(region):region.resolution==='bar_candidate'?' · 小节候选'+(region.image_bar_index+1):''}`;
    $('score-region-select').append(option);}
  if(scoreRegions.some(r=>r.region_id===selected))$('score-region-select').value=selected;
  loadScoreReview();
}
function loadScoreReview(){
  const region=scoreRegions.find(r=>r.region_id===$('score-region-select').value);if(!region)return;
  $('score-region-start').value=region.audioStart.toFixed(2);$('score-region-end').value=region.audioEnd.toFixed(2);
  $('score-region-confirm').checked=false;$('score-region-reason').value='';
}
$('score-region-select').onchange=loadScoreReview;
$('score-region-current').onclick=()=>{if(activeScoreRegion){$('score-region-select').value=activeScoreRegion.region_id;loadScoreReview();}};
$('score-region-start-now').onclick=()=>$('score-region-start').value=audio.currentTime.toFixed(2);
$('score-region-end-now').onclick=()=>$('score-region-end').value=audio.currentTime.toFixed(2);
$('score-region-save').onclick=async()=>{
  if(!project||!scoreMapDocument)return;const version=loadVersion;audio.pause();
  try{
    const response=await fetch(endpoint('/api/score-region-anchor'),{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({track_id:track,audio_sha256:project.audio.sha256,pdf_sha256:scoreMapDocument.pdf_sha256,
        region_id:$('score-region-select').value,start_seconds:Number($('score-region-start').value),end_seconds:Number($('score-region-end').value),
        reason:$('score-region-reason').value,confirmed:$('score-region-confirm').checked})});
    const data=await response.json();if(version!==loadVersion)return;if(!response.ok)throw Error(data.error);
    scoreCorrections=data.score_region_anchors;scoreRegions=prepareScoreRegions(scoreMapDocument,project,scoreCorrections,scoreMeasures);
    activeScoreRegion=null;syncPlaybackPosition();configureScoreReview();$('toast').textContent='区域校正已保存并立即生效，原值保留在历史中。';
  }catch(error){if(version===loadVersion)$('toast').textContent=error.message;}
};
$('save-sync').onclick=async()=>{
  if(!project||!audio.dual)return;
  const version=loadVersion;audio.pause();
  try{
    const anchors=$('sync-points').value.trim().split('\n').map(line=>{
      const values=line.trim().split(/[,，\s]+/);
      if(values.length!==2||values.some(s=>s===''))throw Error('每行需要两个时间（秒），用逗号隔开');
      return {masterTime:Number(values[0]),videoTime:Number(values[1])};
    });
    const response=await fetch(endpoint('/api/media-sync'),{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({track_id:track,master_sha256:project.audio.sha256,video_sha256:audio.media.video.sha256,
        same_performance_confirmed:$('same-performance').checked,reason:$('sync-reason').value,anchors})});
    const data=await response.json();if(version!==loadVersion)return;
    if(!response.ok)throw Error(data.error);
    audio.media=data.media;audio.dualReady=true;audio.syncSlave(true);$('source').disabled=false;
    $('media-state').textContent='音画锚点已保存，覆盖区间内按人工映射同步。';
  }catch(error){if(version===loadVersion)$('media-state').textContent=error.message;}
};
$('showplayhead').onchange=updatePlayhead;$('score').onload=()=>{updatePlayhead();revealPlayingRegion();};
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
  const url=URL.createObjectURL(new Blob([JSON.stringify({track_id:track,alignment:project,measure_map:[...mapping.values()],score_regions:scoreRegions,score_measures:measureNumberPanel.exportData(),media_sync:audio.media,draft_anchors:draft,analysis:analysisPanel.exportData()},null,2)],{type:'application/json'}));
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
