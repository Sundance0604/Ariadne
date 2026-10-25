export const node=(tag,text,className)=>{const n=document.createElement(tag);if(text)n.textContent=text;if(className)n.className=className;return n;};
export function rich(target,html){
  target.innerHTML=html;
  for(const link of target.querySelectorAll('a')){link.target='_blank';link.rel='noopener noreferrer';}
}
const states={verified:'已核对',pending:'待核查',disputed:'存在争议',not_applicable:'不适用',
  relevant_sections_checked:'已核对相关章节',key_pages_checked:'已检查关键谱页',
  publisher_metadata_checked:'已核对出版信息，未读全文',
  candidate_alignment:'候选同步',page_range:'仅页级定位',score_segment_candidate:'候选谱面区域',score_segment:'谱面段落'};
export function verificationText(v){return [['score','谱面'],['literature','文献'],['location','定位'],['timing','时间']]
  .map(([key,label])=>`${label}：${states[v[key]]||'见阅读记录'}`).join(' · ');}
export function appendSources(target,item,sources){
  const section=node('div',null,'research-sources');section.append(node('h4','来源与阅读范围'));
  for(const ref of item.sources||[]){
    const source=sources.find(s=>s.source_id===ref.source_id);
    const label=source?.citation_label||source?.title||ref.source_id;
    section.append(node('p',`${label} · ${ref.locator} · ${ref.claim_attribution==='authors'?'作者的观点':'谱面依据'}`));
    section.append(node('small',`阅读：${states[source?.reading_status]||'本轮未核查全文，详见来源记录'}`));
    if(source?.reading_note)section.append(node('p',source.reading_note,'analysis-note'));
    for(const url of source?.urls||[]){
      if(!/^https?:\/\//i.test(url))continue;
      const link=node('a',' 打开来源');link.href=url;link.target='_blank';link.rel='noopener noreferrer';section.append(link);
    }
  }
  target.append(section);
}
