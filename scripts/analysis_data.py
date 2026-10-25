"""Import the user's page guide and bibliography without inventing measure claims."""
import hashlib
from html import escape
import json
from pathlib import Path
import re

import mistune
from mahler4_guide import build_score_guide
from score_measure_data import load_score_measures

ROOT=Path(__file__).resolve().parents[1]
PAGE_HEADING=re.compile(r'^### PDF 第\s*(\d+)(?:\s*--\s*(\d+))?\s*页[：:]\s*(.+)$',re.M)
REFERENCE_HEADING=re.compile(r'^### 11\.(\d+)\s+(.+)$',re.M)
RENDER=mistune.create_markdown(escape=True,plugins=['url','table','strikethrough'])


def section(markdown,number):
    match=re.search(rf'^## {number}\. [^\n]+\n(.*?)(?=^## \d+\. |\Z)',markdown,re.M|re.S)
    return match.group(1).strip() if match else ''


def clean_space(value): return re.sub(r'\s+',' ',value).strip()


def movement_events(markdown):
    """Keep the draft's event suggestions without inventing score/time bounds."""
    guide=section(markdown,10)
    events=[]
    roman={'I':1,'II':2,'III':3,'IV':4}
    for line in guide.splitlines():
        match=re.match(r'^\|\s*(IV|III|II|I)-(\d+)\s*\|(.+)',line)
        if not match:continue
        cells=[value.strip() for value in match[3].strip().strip('|').split('|')]
        if len(cells)!=3:raise ValueError('分段导聆表格格式已变化，请复核导入器')
        position,focus,cue=cells
        events.append({'annotation_id':f'mahler4-event-{match[1]}-{match[2]}',
            'source_event_id':f'{match[1]}-{match[2]}','movement':roman[match[1]],
            'title':position,'analysis_focus':focus,'listening_cue':cue,
            'start_measure_id':None,'end_measure_id':None,
            'start_seconds':None,'end_seconds':None,'review_status':'unlocated',
            'claim_type':'gpt_draft_event_suggestion',
            'evidence':'用户提供 GPT 原稿第 10 节；原稿未给出具体小节、页码或录音时间。'})
    return events


def build_movement_analysis(source,metadata,mapping,alignment):
    """Bind full draft movement chapters to real movement IDs, not equal slices."""
    raw=source.read_bytes();markdown=raw.decode('utf-8-sig')
    if metadata['recording']['audio_sha256']!=alignment['audio']['sha256']:
        raise ValueError('曲目资料绑定的录音与当前录音不一致')
    if metadata['analysis_document']['pdf_sha256']!=mapping['pdf_sha256']:
        raise ValueError('分析文档绑定的 PDF 与当前谱面不一致')
    annotations=[]
    event_candidates=movement_events(markdown)
    for spec in metadata['analysis_document']['movement_sections']:
        movement=spec['movement'];number=spec['section']
        heading=re.search(rf'^## {number}\. ([^\n]+)$',markdown,re.M)
        body=section(markdown,number)
        if not heading or not body:raise ValueError(f'分析稿缺少乐章 {movement} 对应的第 {number} 节')
        body=re.sub(r'\n?-{3,}\s*$','',body).strip()
        measures=[m for m in alignment['measures'] if m.get('movement')==movement]
        if not measures:raise ValueError(f'当前对齐缺少乐章 {movement} 的结构标记')
        measures.sort(key=lambda m:m['sequence_index'])
        ids={m['measure_id'] for m in measures}
        pages=sorted({m['page_number'] for m in mapping['measures'] if m['measure_id'] in ids})
        movement_map=next((m for m in mapping.get('movements',[]) if m['movement']==movement),{})
        first_page=min(pages) if pages else movement_map.get('first_pdf_page')
        last_page=max(pages) if pages else movement_map.get('last_pdf_page')
        if first_page is None or last_page is None:raise ValueError(f'缺少乐章 {movement} 的谱页范围')
        events=[e for e in event_candidates if e['movement']==movement]
        annotations.append({'annotation_id':f'mahler4-movement-{movement}',
            'movement':movement,'title':heading[1].strip(),
            'start_measure_id':measures[0]['measure_id'],'end_measure_id':measures[-1]['measure_id'],
            'start_sequence_index':measures[0]['sequence_index'],'end_sequence_index':measures[-1]['sequence_index'],
            'start_seconds':measures[0]['start_seconds'],'end_seconds':measures[-1]['end_seconds'],
            'start_pdf_page':first_page,'end_pdf_page':last_page,
            'category':'movement_listening_guide','markdown':body,'html':RENDER(body),
            'source_ids':[metadata['analysis_document']['document_id']],
            'source_section':number,'claim_type':'mixed_gpt_draft','review_status':'unreviewed',
            'editorial_status':'user_supplied_gpt_draft','locator_precision':'movement_range',
            'event_candidates':[e['annotation_id'] for e in events],
            'evidence':'按当前对齐文件的乐章标记绑定原稿整章；未将原稿事件按时长均分或推定具体小节。'})
    bibliography=section(markdown,12)
    entries=list(re.finditer(r'^(\d+)\. \*\*(.+?)\*\*([^\n]*)',bibliography,re.M))
    kinds=metadata['analysis_document'].get('reference_kinds',{})
    reading=metadata['analysis_document'].get('reference_reading_status',{})
    reference_evidence=metadata['analysis_document'].get('reference_evidence',{})
    references=[]
    for i,entry in enumerate(entries):
        end=entries[i+1].start() if i+1<len(entries) else len(bibliography)
        body=bibliography[entry.start():end].strip()
        body=re.split(r'^### 12\.\d+ ',body,flags=re.M)[0].strip()
        urls=list(dict.fromkeys(url.rstrip('.,;') for url in re.findall(r'https?://[^\s<>]+',body)))
        source_id=f'mahler4-ref-{entry[1]}'
        label=clean_space(re.sub(r'[*`]', '',entry[2]+entry[3]))
        references.append({'source_id':source_id,'citation_label':label,
            'title':label,'kind':kinds.get(entry[1],'reference'),
            'scope':'current_work','comparison_note':'','urls':urls,
            'doi_url':next((url for url in urls if url.startswith('https://doi.org/')),None),
            'markdown':body,'html':RENDER(body),
            'reading_status':reading.get(source_id,'listed_in_gpt_draft_not_independently_checked'),
            'verification_evidence':reference_evidence.get(source_id,'')})
    chapter_sources=metadata['analysis_document'].get('movement_source_ids',{})
    for note in annotations:
        linked=[ref['source_id'] for ref in references if any(url in note['markdown'] for url in ref['urls'])]
        explicit=chapter_sources.get(str(note['movement']),[])
        note['source_ids']=list(dict.fromkeys(note['source_ids']+linked+explicit))
    essays=annotations
    supplement=metadata['analysis_document'].get('score_guide_path')
    guide_metadata=None
    if supplement:
        guide_path=(ROOT/supplement).resolve()
        if not guide_path.is_relative_to(ROOT.resolve()):raise ValueError('分段导聆必须位于当前项目内')
        numbered=load_score_measures(guide_path.parent.parent,mapping)
        guide_mapping={**mapping,'bar_regions':numbered['measures']} if numbered else mapping
        annotations,guide_metadata=build_score_guide(guide_path,guide_mapping,alignment,essays,RENDER)
    precision='score_segment' if supplement else 'movement_range'
    full_html=RENDER(markdown)
    if supplement:
        full_html+='<h2>谱面分段导聆</h2>'+''.join(
            f'<h3>{note["start_pdf_page"]}–{note["end_pdf_page"]} 页 · {escape(note["title"])}</h3>'+note['html'] for note in annotations)
    return {'format_version':'1.1.0','source_document':{
        'document_id':metadata['analysis_document']['document_id'],'path':metadata['analysis_document']['path'],
        'sha256':hashlib.sha256(raw).hexdigest(),'title':markdown.splitlines()[0].lstrip('# ').strip(),
        'review_status':metadata['analysis_document'].get('review_status','user_supplied_gpt_draft'),
        'locator_precision':precision,'supplement':{'path':supplement,**guide_metadata} if supplement else None},
        'pdf_sha256':mapping['pdf_sha256'],'audio_sha256':alignment['audio']['sha256'],
        'work':metadata['work'],'recording':{**metadata['recording'],'duration_seconds':alignment['audio']['duration_seconds']},
        'annotations':annotations,'movement_essays':essays,'navigation_mode':precision,
        'event_candidates':event_candidates,'references':references,
        'full_html':full_html,'coverage':{'pdf_pages':mapping['page_count'],
            'guide_sections':len(annotations),'movement_sections':len(essays),
            'located_event_count':0,'unlocated_event_count':len(event_candidates),
            'missing_pages':list(range(1,mapping.get('first_score_page',1)))},
        'reference_note':metadata['analysis_document'].get('reference_note',
            f'{len(references)} 项资料按原稿导入；核验状态逐项标明。原稿声称的阅读情况不自动视为已核验记录。'),
        'notice':f'{len(annotations)} 段导聆 · 随谱面段落切换 · 同步时间待复核' if supplement else metadata['analysis_document'].get('editorial_note','GPT 分析稿 · 已关联四个乐章 · 细分事件与论点待核验'),
        'provenance_notice':metadata['analysis_document'].get('provenance_notice',
            f'原稿写作时未绑定具体 PDF 和录音；现按本次视频的乐章标记关联整章正文。{len(event_candidates)} 个细分事件缺少原谱定位依据，未制造时间边界。')}


def build_analysis(source,metadata,mapping,alignment):
    raw=source.read_bytes()
    markdown=raw.decode('utf-8-sig')
    edited=metadata['analysis_document'].get('review_status')=='editorially_revised'
    if metadata['recording']['audio_sha256']!=alignment['audio']['sha256']:
        raise ValueError('曲目资料绑定的录音与当前录音不一致')
    if metadata['analysis_document']['pdf_sha256']!=mapping['pdf_sha256']:
        raise ValueError('分析文档绑定的 PDF 与当前谱面不一致，需重新核对页码')
    guide=section(markdown,9)
    headings=list(PAGE_HEADING.finditer(guide))
    if not headings: raise ValueError('未找到“逐页导聆纲要”中的 PDF 页码标题')
    index={m['measure_id']:m for m in alignment['measures']}
    annotations=[]
    covered=set()
    for i,heading in enumerate(headings):
        first=int(heading[1]);last=int(heading[2] or first)
        pages=set(range(first,last+1))
        if first<1 or last<first or pages&covered:
            raise ValueError('导聆页码范围无效或重叠')
        covered|=pages
        body=guide[heading.end():headings[i+1].start() if i+1<len(headings) else len(guide)].strip()
        body=re.sub(r'\n?-{8,}\s*$','',body).strip()
        matches=[index[m['measure_id']] for m in mapping['measures']
                 if m['page_number'] in pages and m['measure_id'] in index]
        matches.sort(key=lambda m:m['sequence_index'])
        if not matches: raise ValueError(f'PDF {first}–{last} 页没有当前曲目的小节关联')
        annotations.append({
            'annotation_id':f'page-guide-{first:03d}-{last:03d}',
            'start_pdf_page':first,'end_pdf_page':last,'title':heading[3].strip(),
            'start_measure_id':matches[0]['measure_id'],'end_measure_id':matches[-1]['measure_id'],
            'start_seconds':matches[0]['start_seconds'],'end_seconds':matches[-1]['end_seconds'],
            'category':'page_listening_guide','markdown':body,'html':RENDER(body),
            'source_ids':[metadata['analysis_document']['document_id']],
            'claim_type':'score_observation' if edited else 'hypothesis','review_status':'unreviewed',
            'editorial_status':'finished_prose' if edited else 'working_draft',
            'locator_precision':'source_pdf_page_range',
            'evidence':('成稿叙述；关键段落页码已按速度文字与页面图像修订，未宣称逐音符核验' if edited else
                       '用户原稿的逐页导聆范围；小节边界仅由页面映射关联，未新增逐小节分析结论')})
    expected=(set(range(1,int(mapping['page_count'])+1)) if mapping.get('page_count')
              else {m['page_number'] for m in mapping['measures']})
    missing=expected-covered
    if missing: raise ValueError(f'导聆缺少 PDF 页码：{sorted(missing)}')
    bibliography=section(markdown,11)
    entries=list(REFERENCE_HEADING.finditer(bibliography))
    references=[]
    for i,entry in enumerate(entries):
        body=bibliography[entry.end():entries[i+1].start() if i+1<len(entries) else len(bibliography)].strip()
        title=re.search(r'\*\*(.*?)\*\*',body,re.S)
        urls=list(dict.fromkeys(re.findall(r'https?://[^\s<>]+',body)))
        urls=[url.rstrip('.,;') for url in urls]
        doi=next((url for url in urls if url.startswith('https://doi.org/')),None)
        number=int(entry[1])
        legacy_ravel=metadata['work']['work_id']=='ravel-left-hand-concerto'
        extra=metadata['analysis_document'].get('reference_metadata',{}).get(f'analysis-ref-11-{number}',{})
        kind=extra.get('kind',('thesis' if number==6 else 'programme_note' if number in {3,7} else 'research_article')
                       if legacy_ravel else 'reference')
        references.append({'source_id':f'analysis-ref-11-{number}',
            'citation_label':entry[2].strip(),'title':clean_space(title[1]).strip('"') if title else entry[2].strip(),
            'kind':kind,'scope':extra.get('scope','comparison_other_work' if legacy_ravel and number==8 else 'current_work'),
            'comparison_note':extra.get('comparison_note','研究对象为 G 大调协奏曲' if legacy_ravel and number==8 else ''),
            'urls':urls,'doi_url':doi,'markdown':body,'html':RENDER(body),
            'reading_status':metadata['analysis_document'].get('reference_reading_status',{}).get(
                f'analysis-ref-11-{number}','listed_in_user_document_not_independently_checked')})
    result={'format_version':'1.0.0','source_document':{
        'document_id':metadata['analysis_document']['document_id'],'path':metadata['analysis_document']['path'],
        'sha256':hashlib.sha256(raw).hexdigest(),'title':markdown.splitlines()[0].lstrip('# ').strip(),
        'review_status':'editorially_revised' if edited else 'user_supplied_draft'},
        'pdf_sha256':mapping['pdf_sha256'],'audio_sha256':alignment['audio']['sha256'],
        'work':metadata['work'],'recording':{**metadata['recording'],
            'duration_seconds':alignment['audio']['duration_seconds']},
        'annotations':annotations,'references':references,'full_html':RENDER(markdown),
        'coverage':{'pdf_pages':len(expected),'guide_sections':len(annotations),'missing_pages':sorted(missing)},
        'reference_note':metadata['analysis_document'].get('reference_note',
            '参考资料与实际阅读状态逐项注明。'),
        'notice':metadata['analysis_document'].get('editorial_note',
            '按用户原稿页码关联；原稿中的曲式边界、音符与文献论点尚未独立核验。')}
    return result


def load_analysis(root=ROOT,data_root=None):
    data_root=data_root or root
    # Some local works have structured, independently maintained annotations
    # while a full research document is still pending.
    standalone=data_root/'analysis/annotations.json'
    if not (data_root/'metadata/recording.json').exists() and standalone.exists():
        data=json.loads(standalone.read_text(encoding='utf-8'))
        alignment=json.loads((data_root/'alignment.json').read_text(encoding='utf-8'))
        mapping=json.loads((data_root/'measure-map.json').read_text(encoding='utf-8'))
        if data['audio_sha256']!=alignment['audio']['sha256'] or data['pdf_sha256']!=mapping['pdf_sha256']:
            raise ValueError('导聆与当前媒体或 PDF 指纹不一致')
        for note in data['annotations']:note['html']=RENDER(note['markdown'])
        data['full_html']=RENDER(data.get('markdown',''))
        return data
    metadata=json.loads((data_root/'metadata/recording.json').read_text(encoding='utf-8'))
    source=(root/metadata['analysis_document']['path']).resolve()
    if not source.is_relative_to(root.resolve()): raise ValueError('分析文档必须位于当前项目内')
    mapping=json.loads((data_root/'measure-map.json').read_text(encoding='utf-8'))
    alignment=json.loads((data_root/'alignment.json').read_text(encoding='utf-8'))
    if metadata['analysis_document'].get('locator_type')=='movement_sections':
        return build_movement_analysis(source,metadata,mapping,alignment)
    return build_analysis(source,metadata,mapping,alignment)


if __name__=='__main__':
    import argparse
    from review_library import track_context
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--track')
    args=parser.parse_args()
    _,data_root=track_context(ROOT,args.track)
    result=load_analysis(ROOT,data_root)
    output=data_root/'analysis/annotations.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    # Export data, not rendered report HTML; preserve the original Markdown source.
    saved={k:v for k,v in result.items() if k!='full_html'}
    output.write_text(json.dumps(saved,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'output':str(output),'coverage':result['coverage'],
                      'references':len(result['references'])},ensure_ascii=True))
