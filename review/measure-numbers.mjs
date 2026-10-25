export function measureNumberLabel(measure){
  const prefix=measure.numbering_status==='corrected'?'':'≈';
  const end=measure.score_measure_number+measure.count_span-1;
  return `${prefix}${measure.score_measure_number}${measure.count_span>1?'–'+end:''}`;
}

export function measureForNumber(measures,movement,number){
  if(!Number.isInteger(movement)||!Number.isInteger(number)||number<0)return null;
  const matches=measures.filter(m=>m.movement===movement&&m.score_measure_number<=number&&
    number<=m.score_measure_number+Math.max(1,m.count_span)-1);
  return matches.find(m=>m.numbering_status==='corrected'&&m.count_span>0)||
    matches.find(m=>m.numbering_anchor_id&&m.count_span>0)||matches.find(m=>m.count_span>0)||matches[0]||null;
}

export function numberedMeasureAtPoint(measures,page,xFraction,yFraction){
  return measures.filter(m=>{
    const [x,y,w,h]=m.rect_pt;
    return m.page_number===page&&xFraction>=x/m.page_width_pt&&xFraction<=(x+w)/m.page_width_pt&&
      yFraction>=y/m.page_height_pt&&yFraction<=(y+h)/m.page_height_pt;
  }).sort((a,b)=>a.rect_pt[2]*a.rect_pt[3]-b.rect_pt[2]*b.rect_pt[3])[0]||null;
}

export function createMeasureNumberPanel({onLocate,onChange}){
  const $=id=>document.getElementById(id);
  let data=null,track=null,page=1,selectedId=null,activeId=null,saving=false,version=0;
  const buttons=new Map();
  function selection(){return data?.measures.find(m=>m.region_id===selectedId);}
  function renderSelection(){
    const selected=selection(),node=$('measure-selection');
    node.hidden=!selected||selected.page_number!==page;
    if(node.hidden)return;
    const [x,y,w,h]=selected.rect_pt;
    Object.assign(node.style,{left:`${x/selected.page_width_pt*100}%`,top:`${y/selected.page_height_pt*100}%`,
      width:`${w/selected.page_width_pt*100}%`,height:`${h/selected.page_height_pt*100}%`});
  }
  function select(measure){
    selectedId=measure.region_id;
    $('measure-number-location').textContent=`第 ${measure.movement} 乐章 · PDF 第 ${measure.page_number} 页 · 系统 ${measure.system_index+1}`;
    $('measure-number-value').value=measure.score_measure_number;
    $('measure-count-span').value=measure.count_span;
    $('measure-number-reason').value='';$('measure-number-confirm').checked=false;
    $('measure-number-state').textContent=measure.numbering_status==='corrected'?'该处编号已人工校正；后续号码仍需核对。':'自动计数候选；先核对边界与编号，再保存。';
    renderSelection();
  }
  function renderPage(nextPage){
    page=nextPage;buttons.clear();$('measure-number-layer').replaceChildren();
    $('measure-number-layer').hidden=!data||!$('show-measure-numbers').checked;
    for(const measure of data?.measures||[]){
      if(measure.page_number!==page)continue;
      const svg=tag=>document.createElementNS('http://www.w3.org/2000/svg',tag);
      $('measure-number-layer').setAttribute('viewBox',`0 0 ${measure.page_width_pt} ${measure.page_height_pt}`);
      const node=svg('g');node.setAttribute('class','measure-number');node.setAttribute('role','button');node.setAttribute('tabindex','0');
      node.dataset.regionId=measure.region_id;
      node.setAttribute('aria-label',`第 ${measure.movement} 乐章，${measure.numbering_status==='corrected'?'已校正':'候选'}小节 ${measure.score_measure_number}，点击定位`);
      node.setAttribute('aria-current',String(measure.region_id===activeId));
      node.title=`${node.getAttribute('aria-label')}；${measure.geometry_status==='needs_review'?'边界待核对':'边界有多个谱表支持'}，时间待试听。`;
      const [x,y,w]=measure.rect_pt,[cx,bottom,height=13,safeWidth]=measure.label_position_pt||[x+w/2,y-2];
      const label=measureNumberLabel(measure),width=safeWidth??Math.min(36,w-2),font=Math.min(9,height-3,(width-4)/(label.length*.58));
      const background=svg('rect');
      for(const [key,value] of Object.entries({x:cx-width/2,y:bottom-height,width,height,rx:2}))background.setAttribute(key,value);
      const text=svg('text');text.textContent=label;
      for(const [key,value] of Object.entries({x:cx,y:bottom-3,'text-anchor':'middle','font-size':font}))text.setAttribute(key,value);
      const title=svg('title');title.textContent=node.title;node.append(background,text,title);
      node.onclick=event=>{event?.stopPropagation();select(measure);onLocate(measure);};
      node.onkeydown=event=>{if(['Enter',' '].includes(event.key)){event.preventDefault();select(measure);onLocate(measure);}};
      buttons.set(measure.region_id,node);$('measure-number-layer').append(node);
    }
    renderSelection();
  }
  function load(nextData,nextTrack=track){
    const sameTrack=nextTrack===track;version++;saving=false;
    data=nextData;track=nextTrack;if(!sameTrack){selectedId=null;activeId=null;}
    $('measure-number-controls').hidden=!data;$('measure-number-review').hidden=!data;
    $('measure-number-save').disabled=false;
    $('measure-jump-movement').replaceChildren();
    for(const movement of [...new Set((data?.measures||[]).map(m=>m.movement))]){
      const option=document.createElement('option');option.value=movement;option.textContent=`第 ${movement} 乐章`;
      $('measure-jump-movement').append(option);
    }
    if(!data){selectedId=null;activeId=null;$('measure-number-location').textContent='先点击谱面上方的小节号';}
    else if(selection())select(selection());
    renderPage(page);
  }
  function activate(region){
    const next=region?.region_id;
    if(next!==activeId){buttons.get(activeId)?.setAttribute('aria-current','false');activeId=next;buttons.get(activeId)?.setAttribute('aria-current','true');}
  }
  $('show-measure-numbers').onchange=()=>renderPage(page);
  function go(){
    const measure=measureForNumber(data?.measures||[],Number($('measure-jump-movement').value),Number($('measure-jump-number').value));
    if(!measure){$('toast').textContent='该乐章尚未找到这个小节号，请检查编号范围。';return;}
    select(measure);onLocate(measure);
  }
  $('measure-jump-go').onclick=go;
  $('measure-jump-number').onkeydown=event=>{if(event.key==='Enter')go();};
  $('measure-number-current').onclick=()=>{
    const measure=data?.measures.find(m=>m.region_id===activeId);
    if(measure)select(measure);else $('measure-number-state').textContent='当前未高亮到具体小节，请点击谱面上方的号码选择。';
  };
  $('measure-number-save').onclick=async()=>{
    const measure=selection();if(!data||!measure||saving)return;
    const start_number=Number($('measure-number-value').value),count_span=Number($('measure-count-span').value);
    if(!$('measure-number-value').value.trim()||!$('measure-count-span').value.trim()||!Number.isInteger(start_number)||start_number<0||!Number.isInteger(count_span)||count_span<0){
      $('measure-number-state').textContent='请填写非负整数的小节号和本框小节数。';return;
    }
    const generation=version;saving=true;$('measure-number-save').disabled=true;
    try{
      const response=await fetch(`/api/score-measure-number?track=${encodeURIComponent(track)}`,{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({track_id:track,pdf_sha256:data.pdf_sha256,geometry_sha256:data.geometry_sha256,
          region_id:measure.region_id,start_number,count_span,reason:$('measure-number-reason').value,
          confirmed:$('measure-number-confirm').checked})});
      const payload=await response.json();if(generation!==version)return;if(!response.ok)throw Error(payload.error||'编号保存失败');
      load(payload.score_measures,track);onChange(payload.score_measures);
      $('measure-number-state').textContent='编号已保存，后续自动号码已更新；旧值保留在校正历史中。';
    }catch(error){if(generation===version)$('measure-number-state').textContent=error.message;}
    finally{if(generation===version){saving=false;$('measure-number-save').disabled=false;}}
  };
  return {load,renderPage,activate,exportData:()=>data};
}
