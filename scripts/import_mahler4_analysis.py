"""Bind the supplied GPT draft to local Mahler 4 movement identities.

The draft is never edited. Event suggestions without score locations stay
unlocated; they do not become equal slices of the performance.
"""
import json
from pathlib import Path

from analysis_data import ROOT, load_analysis

DATA=ROOT/'works/mahler-4'
SOURCE='resource/mahler No.4/analysis/Mahler_Symphony_No4_Full_Analysis.md'


def import_analysis():
    alignment=json.loads((DATA/'alignment.json').read_text(encoding='utf-8'))
    mapping=json.loads((DATA/'measure-map.json').read_text(encoding='utf-8'))
    path=DATA/'metadata/recording.json'
    metadata=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {
        'format_version':'1.0.0',
        'work':{'work_id':'mahler-symphony-4','title':'第四交响曲','original_title':'Symphonie Nr. 4',
            'composer':{'name':'古斯塔夫·马勒','original_name':'Gustav Mahler'},
            'instrumentation':'管弦乐与终曲独唱（详细编制与分析论点待核验）'},
        'recording':{'recording_id':'mahler4-abbado-lucerne-2009-local-video','soloists':[],
            'conductor':{'name':'克劳迪奥·阿巴多','original_name':'Claudio Abbado'},
            'ensemble':{'name':'琉森节日管弦乐团','original_name':'Lucerne Festival Orchestra','abbreviation':'LFO'},
            'artist_information_source':'user_supplied_video_filename',
            'artist_information_note':'指挥、乐团与 2009 年份来自用户提供的视频文件名；独唱者、发行资料及所据版本尚未独立核验。'}}
    if metadata.get('recording',{}).get('audio_sha256') not in [None,alignment['audio']['sha256']]:
        raise ValueError('已有分析资料属于另一录音，拒绝直接改绑')
    metadata['recording']['audio_sha256']=alignment['audio']['sha256']
    metadata['analysis_document']={**metadata.get('analysis_document',{}),'document_id':'mahler4-user-gpt-analysis',
        'path':SOURCE,'pdf_sha256':mapping['pdf_sha256'],
        'review_status':metadata.get('analysis_document',{}).get('review_status','user_supplied_gpt_draft'),
        'locator_type':'movement_sections',
        'score_guide_path':'works/mahler-4/analysis/score-guide.json',
        'movement_sections':[{'movement':m,'section':m+2} for m in range(1,5)],
        'reference_kinds':{**{'1':'programme_note','2':'programme_note','3':'programme_note',
            '4':'source_index','5':'source_index','6':'chapter','7':'thesis'},
            **metadata.get('analysis_document',{}).get('reference_kinds',{})}}
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    result=load_analysis(ROOT,DATA)
    output=DATA/'analysis/annotations.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    saved={k:v for k,v in result.items() if k!='full_html'}
    output.write_text(json.dumps(saved,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'annotations':len(result['annotations']),'unlocated_events':len(result['event_candidates']),
        'references':len(result['references']),'source_sha256':result['source_document']['sha256']},ensure_ascii=True))


if __name__=='__main__':import_analysis()
