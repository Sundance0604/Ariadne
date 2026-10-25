const byId=id=>document.getElementById(id);
const el=(tag,text,className)=>{const node=document.createElement(tag);if(text)node.textContent=text;if(className)node.className=className;return node;};

function richText(target,html){
  // HTML is rendered locally by Mistune with raw HTML escaped and unsafe URLs blocked.
  target.innerHTML=html;
  for(const link of target.querySelectorAll('a')){link.target='_blank';link.rel='noopener noreferrer';}
}

export function annotationForPlayback(notes,page,sequence,position=null){
  if(notes.some(note=>note.locator_precision==='score_segment')){
    if(!Number.isFinite(page))return undefined;
    const point=[page,position?.system_index??0,position?.x_pt??0];
    const compare=(a,b)=>a[0]-b[0]||a[1]-b[1]||a[2]-b[2];
    return notes.find(note=>compare(point,note.score_start)>=0&&compare(point,note.score_end)<0);
  }
  return notes.find(note=>note.start_sequence_index!==undefined
    ?Number.isFinite(sequence)&&note.start_sequence_index<=sequence&&sequence<=note.end_sequence_index
    :page!==null&&note.start_pdf_page<=page&&page<=note.end_pdf_page);
}

export function annotationRangeLabel(note){
  const pages=note.start_pdf_page===note.end_pdf_page?`谱面第 ${note.start_pdf_page} 页`:`谱面第 ${note.start_pdf_page}–${note.end_pdf_page} 页`;
  return note.locator_precision==='movement_range'?`${pages} · 整乐章导聆，细分事件待定位`:
    note.locator_precision==='score_segment'?`${pages} · ${note.score_start?.[2]?'页内段落':'分段导聆'}`:pages;
}

export function createAnalysisPanel(onSeek){
  let data=null,playingPage=null,playingSequence=null,position=null,browsedPage=null,selectedId=null,renderedId=null,track=null,loadVersion=0;
  const tabs=['guide','recording','references','research'];
  function selectTab(name){
    for(const tab of tabs){const selected=tab===name;byId(`tab-${tab}`).setAttribute('aria-selected',String(selected));byId(`tab-${tab}`).tabIndex=selected?0:-1;byId(`panel-${tab}`).hidden=!selected;}
  }
  for(const name of tabs){
    byId(`tab-${name}`).onclick=()=>selectTab(name);
    byId(`tab-${name}`).onkeydown=event=>{if(!['ArrowLeft','ArrowRight'].includes(event.key))return;event.preventDefault();const step=event.key==='ArrowRight'?1:-1;const next=tabs[(tabs.indexOf(name)+step+tabs.length)%tabs.length];selectTab(next);byId(`tab-${next}`).focus();};
  }
  function updateGuide(){
    if(!data)return;
    const segmented=data.navigation_mode==='score_segment';
    const displayPage=segmented?(browsedPage??position?.page??playingPage):playingPage;
    const note=(segmented&&selectedId?data.annotations.find(n=>n.annotation_id===selectedId):null)||
      annotationForPlayback(data.annotations,displayPage,playingSequence,browsedPage===null?position:null);
    if(displayPage===null&&!note){
      byId('guide-title').textContent='此处尚未定位到谱页';
      byId('guide-playing-page').textContent='播放位置待核对';
      byId('guide-range').textContent='';byId('guide-body').replaceChildren();
      byId('guide-section').value='';renderedId=null;return;
    }
    byId('guide-playing-page').textContent=displayPage===null?'跟随乐章候选位置 · 谱页定位待复核':`${!segmented||browsedPage===null?'跟随播放':'浏览谱页'} · PDF 第 ${displayPage} 页`;
    if(!note){byId('guide-title').textContent='这一页尚无导聆';byId('guide-body').replaceChildren();byId('guide-range').textContent='';byId('guide-section').value='';renderedId=null;return;}
    byId('guide-range').textContent=annotationRangeLabel(note);
    byId('guide-section').value=note.annotation_id;
    if(note.annotation_id!==renderedId){
      byId('guide-title').textContent=note.title;
      richText(byId('guide-body'),note.html);
      const events=segmented?[]:(data.event_candidates||[]).filter(event=>event.movement===note.movement);
      if(events.length){
        const details=el('details',null,'full-analysis');details.append(el('summary',`分段导聆清单（${events.length} 项，待定位）`));
        details.append(el('p','这些事件来自原稿，尚未确认起止小节；清单供阅读，不用于播放跳转。','analysis-note'));
        for(const event of events){
          details.append(el('h3',`${event.source_event_id} · ${event.title}`),el('p',event.analysis_focus),el('p',event.listening_cue));
        }
        byId('guide-body').append(details);
      }
      renderedId=note.annotation_id;
      if(!byId('panel-guide').hidden){const pane=byId('guide-body').closest('.analysis-content');if(pane)pane.scrollTop=0;}
    }
  }
  function fact(list,label,text){list.append(el('dt',label),el('dd',text));}
  function renderRecording(){
    const panel=byId('recording-details');panel.replaceChildren();
    panel.append(el('h3',`${data.work.composer.name} · ${data.work.title}`),el('p',data.work.original_title,'original-title'));
    const facts=el('dl');fact(facts,'作曲家',`${data.work.composer.name} / ${data.work.composer.original_name}`);
    fact(facts,'演奏编制',data.work.instrumentation);
    for(const soloist of data.recording.soloists)fact(facts,soloist.role,`${soloist.name}\n${soloist.original_name}`);
    fact(facts,'指挥',`${data.recording.conductor.name}\n${data.recording.conductor.original_name}`);
    fact(facts,'乐团',`${data.recording.ensemble.name}（${data.recording.ensemble.abbreviation}）\n${data.recording.ensemble.original_name}`);
    const seconds=data.recording.duration_seconds;fact(facts,'录音时长',`${Math.floor(seconds/60)} 分 ${Math.round(seconds%60)} 秒`);
    if(data.recording.album)fact(facts,'专辑',data.recording.album);
    panel.append(facts,el('p',data.recording.artist_information_note||'演奏阵容由你确认，专辑信息来自当前 MP3 标签。','analysis-note'));
  }
  function renderReferences(){
    const panel=byId('reference-list');panel.replaceChildren();
    const labels={research_article:'研究论文',thesis:'学位论文',programme_note:'作品导赏',book:'专著',chapter:'书籍章节',source_index:'资料索引'};
    byId('reference-count').textContent=`${data.references.length} 项参考资料 · 来自分析原稿`;
    for(const ref of data.references){
      const card=el('article',null,'reference-card');
      card.append(el('span',labels[ref.kind]||'参考资料','reference-type'),el('h3',ref.citation_label));
      if(ref.scope==='comparison_other_work')card.append(el('p',`延伸比较：${ref.comparison_note||'其他作品'}`,'comparison-note'));
      const body=el('div',null,'analysis-rich');richText(body,ref.html);card.append(body);panel.append(card);
      const readingLabels={listed_in_gpt_draft_not_independently_checked:'按 GPT 原稿导入，未独立核对',
        primary_page_checked:'已核对来源原始页面',abstract_checked:'已核对摘要，未核对全文',
        full_text_checked:'已核对全文',relevant_sections_checked:'已核对相关章节',
        official_programme_note_checked:'已核对官方导赏正文',publisher_metadata_checked:'已核对出版信息，未核对全文',
        official_indexed_title_abstract_checked:'已核对官方库索引中的题名页和摘要，全文未读取',
        not_read:'未阅读'};
      if(readingLabels[ref.reading_status])card.append(el('p',`核验状态：${readingLabels[ref.reading_status]}。${ref.verification_evidence||''}`,'analysis-note'));
    }
  }
  async function load(){
    if(!track)return;
    const version=++loadVersion,currentTrack=track;
    byId('analysis-load-state').textContent='正在读取分析文档…';
    try{
      const response=await fetch(`/api/analysis?track=${encodeURIComponent(currentTrack)}`,{cache:'no-store'}),payload=await response.json();
      if(version!==loadVersion)return;
      if(!response.ok)throw Error(payload.error||'分析文档读取失败');
      data=payload;renderedId=null;
      const select=byId('guide-section');select.replaceChildren();
      for(const note of data.annotations){const option=el('option',`${note.start_pdf_page}${note.end_pdf_page!==note.start_pdf_page?'–'+note.end_pdf_page:''} 页 · ${note.title}`);option.value=note.annotation_id;select.append(option);}
      richText(byId('analysis-full-text'),data.full_html);
      byId('analysis-source-name').textContent=[data.source_document.path.split('/').at(-1),data.provenance_notice].filter(Boolean).join(' · ');
      renderRecording();renderReferences();updateGuide();
      const edited=data.source_document.review_status==='editorially_revised';
      byId('analysis-load-state').textContent=data.notice||(edited?'导聆成稿修订版 · 按谱页定位':'用户分析工作稿 · 页码与论点待复核');
      byId('reference-reading-note').textContent=data.reference_note;
    }catch(error){if(version===loadVersion)byId('analysis-load-state').textContent=`未载入分析：${error.message}`;}
  }
  byId('guide-section').onchange=()=>{const note=data?.annotations.find(n=>n.annotation_id===byId('guide-section').value);if(note){onSeek(note.start_measure_id,note.start_pdf_page,note);if(data.navigation_mode==='score_segment'){browsedPage=note.start_pdf_page;selectedId=note.annotation_id;updateGuide();}}};
  byId('analysis-refresh').onclick=load;
  function reset(nextTrack){
    track=nextTrack;loadVersion++;data=null;playingPage=null;playingSequence=null;position=null;browsedPage=null;selectedId=null;renderedId=null;
    for(const id of ['guide-body','recording-details','reference-list','analysis-full-text','guide-section'])byId(id).replaceChildren();
    for(const id of ['guide-range','guide-playing-page','reference-count','reference-reading-note','analysis-source-name'])byId(id).textContent='';
    byId('guide-title').textContent='正在载入导聆';
    byId('analysis-load-state').textContent=track?'正在读取分析文档…':'等待载入曲目';
    selectTab('guide');
  }
  return {reset,selectTab,load(nextTrack){reset(nextTrack);return load();},
    browse(page){browsedPage=page;selectedId=null;updateGuide();},
    follow(){browsedPage=null;selectedId=null;},
    update(page,sequence,nextPosition=null){
      playingPage=page??null;playingSequence=sequence??null;position=nextPosition;
      const selected=data?.annotations.find(note=>note.annotation_id===selectedId);
      if(selected&&Number.isFinite(position?.time)&&position.time>=selected.end_seconds){browsedPage=null;selectedId=null;}
      updateGuide();
    },exportData(){
    if(!data)return null;
    return {source_document:data.source_document,work:data.work,recording:data.recording,
      annotations:data.annotations,event_candidates:data.event_candidates||[],references:data.references};
  }};
}
