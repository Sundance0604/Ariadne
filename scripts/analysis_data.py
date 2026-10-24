"""Import the user's page guide and bibliography without inventing measure claims."""
import hashlib
import json
from pathlib import Path
import re

import mistune

ROOT=Path(__file__).resolve().parents[1]
PAGE_HEADING=re.compile(r'^### PDF 第\s*(\d+)(?:\s*--\s*(\d+))?\s*页[：:]\s*(.+)$',re.M)
REFERENCE_HEADING=re.compile(r'^### 11\.(\d+)\s+(.+)$',re.M)
RENDER=mistune.create_markdown(escape=True,plugins=['url','table','strikethrough'])


def section(markdown,number):
    match=re.search(rf'^## {number}\. [^\n]+\n(.*?)(?=^## \d+\. |\Z)',markdown,re.M|re.S)
    return match.group(1).strip() if match else ''


def clean_space(value): return re.sub(r'\s+',' ',value).strip()


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
    metadata=json.loads((data_root/'metadata/recording.json').read_text(encoding='utf-8'))
    source=(root/metadata['analysis_document']['path']).resolve()
    if not source.is_relative_to(root.resolve()): raise ValueError('分析文档必须位于当前项目内')
    mapping=json.loads((data_root/'measure-map.json').read_text(encoding='utf-8'))
    alignment=json.loads((data_root/'alignment.json').read_text(encoding='utf-8'))
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
