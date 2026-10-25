"""Reproduce the local Mahler 4 video project using supplied auxiliary MIDIs.

--align runs the expensive offline alignment. --publish packages an existing
algorithmic result, retaining its original analysis-audio provenance.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys

import mido
import pypdfium2 as pdfium

from midi_score import read_midi
from prepare_video import ROOT, digest, prepare

DATA = ROOT / 'works/mahler-4'
SOURCE = ROOT / 'resource/mahler No.4'
MOVEMENTS = [(5,48,'I · Bedächtig. Nicht eilen'),
             (49,77,'II · In gemächlicher Bewegung. Ohne Hast'),
             (78,101,'III · Ruhevoll. Poco adagio'),
             (102,127,'IV · Sehr behaglich')]


def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')


def combine_midis():
    files=sorted(SOURCE.glob('*.mid'))
    if len(files)!=4:raise ValueError('需要四个乐章的 MIDI')
    result=mido.MidiFile(ticks_per_beat=240)
    offset=0;movements=[]
    for i,path in enumerate(files):
        midi=mido.MidiFile(path)
        if midi.ticks_per_beat!=240:raise ValueError('合并器需要当前素材的 240 PPQ')
        score=read_midi(path)
        movements.append({'movement':i+1,'path':path.relative_to(ROOT).as_posix(),
            'sha256':digest(path),'start_tick':offset,'duration_seconds':score['duration'],
            'measures':len(score['measures'])})
        for track in midi.tracks:
            copied=mido.MidiTrack(event.copy() for event in track)
            if copied:copied[0].time+=offset
            result.tracks.append(copied)
        offset+=max(sum(e.time for e in track) for track in midi.tracks)
    reference=DATA/'auxiliary.mid'
    if reference.exists():
        pending=DATA/'auxiliary.pending.mid';result.save(pending)
        if digest(pending)!=digest(reference):
            pending.unlink();raise ValueError('已有辅助 MIDI 不同，拒绝覆盖；请使用独立项目')
        pending.unlink()
    else:result.save(reference)
    save(DATA/'midi-movements.json',movements)
    return movements


def publish(raw_path,media,movements):
    target=DATA/'alignment.json'
    if target.exists():
        old=json.loads(target.read_text(encoding='utf-8'))
        if old.get('human_anchors') or any(m.get('review_status') in {'verified','corrected'} for m in old.get('measures',[])):
            raise ValueError('已有人工复核结果，拒绝覆盖')
    result=json.loads(raw_path.read_text(encoding='utf-8'))
    if result.get('human_anchors') or any(m.get('review_status') in {'verified','corrected'} for m in result['measures']):
        raise ValueError('此封装入口仅用于未复核候选；人工纠正版请独立保留')
    expected={media['video']['sha256'],media['analysisAudio']['sha256']}
    if result['audio']['sha256'] not in expected or result['symbolic_reference']['sha256']!=digest(DATA/'auxiliary.mid'):
        raise ValueError('对齐结果与当前视频 / MIDI 不匹配')
    result['analysis_audio']=result.get('analysis_audio',result['audio'])
    result['audio']={**media['video'],'duration_seconds':media['video']['duration_seconds']}
    result['playback_clock']='video'
    result['limitations']+=['Movement breaks, applause and MIDI/PDF numbering require listening review.',
        'No per-measure PDF coordinates have been validated for this scanned score.']
    starts=[];index=0
    for movement,(first,last,title) in zip(movements,MOVEMENTS):
        starts.append({'movement':movement['movement'],'title':title,'first_pdf_page':first,
                       'last_pdf_page':last,'first_sequence_index':index+1})
        for measure in result['measures'][index:index+movement['measures']]:
            measure['movement']=movement['movement']
            measure['flags']=list(dict.fromkeys(measure['flags']+['pdf_coordinate_missing']))
            measure['pdf_mapping_status']='missing'
        index+=movement['measures']
    if index!=len(result['measures']):raise ValueError('合并 MIDI 小节数不一致')
    for i in [0,index-1]:result['measures'][i]['flags'].append('recording_edge_requires_listening')
    for start in starts[1:]:
        for i in [start['first_sequence_index']-2,start['first_sequence_index']-1]:
            result['measures'][i]['flags'].append('movement_boundary_requires_listening')
    for m in result['measures']:m['flags']=list(dict.fromkeys(m['flags']))
    result['quality']['original_feature_flag_counts']=result['quality'].get('original_feature_flag_counts',result['quality']['flag_counts'])
    result['quality']['flag_counts']=dict(Counter(f for m in result['measures'] for f in m['flags']))
    # No guessed page/bar subdivision: page ranges were visually checked at
    # the four actual movement headings; within-movement mapping remains empty.
    pdf=next(SOURCE.glob('*.pdf'))
    with pdfium.PdfDocument(pdf) as document:pages=len(document)
    mapping={'format_version':'1.0.0','pdf_path':pdf.relative_to(ROOT).as_posix(),
        'pdf_sha256':digest(pdf),'page_count':pages,'first_score_page':5,
        'status':'movement_headings_checked_bar_coordinates_missing',
        'measures':[],'movements':starts,
        'limitations':['原谱扫描件尚无逐小节坐标；不按时长均分谱页，不显示虚构高亮。']}
    existing_map=DATA/'measure-map.json'
    if existing_map.exists():
        previous_map=json.loads(existing_map.read_text(encoding='utf-8'))
        if previous_map.get('measures') or previous_map.get('score_regions'):
            if previous_map.get('pdf_sha256')!=mapping['pdf_sha256']:
                raise ValueError('已有谱面定位绑定另一 PDF，拒绝覆盖')
            reference=previous_map.get('symbolic_reference_sha256')
            if reference and reference!=result['symbolic_reference']['sha256']:
                raise ValueError('已有谱面定位绑定另一符号参考，拒绝覆盖')
            mapping=previous_map
            result['limitations']=[v for v in result['limitations'] if not v.startswith('No per-measure PDF coordinates')]
            result['limitations']+=mapping.get('limitations',[])
            if target.exists():
                old_by_id={m['measure_id']:m for m in old['measures']}
                for measure in result['measures']:
                    prior=old_by_id.get(measure['measure_id'],{})
                    if prior.get('pdf_mapping_status') not in {None,'missing'}:
                        measure['pdf_mapping_status']=prior['pdf_mapping_status']
                        measure['flags']=[f for f in measure['flags'] if f!='pdf_coordinate_missing']
    notes=[]
    for i,((first,last,title),start) in enumerate(zip(MOVEMENTS,starts)):
        a=start['first_sequence_index'];b=starts[i+1]['first_sequence_index']-1 if i+1<len(starts) else index
        notes.append({'annotation_id':f'movement-{i+1}','title':title,
            'start_measure_id':result['measures'][a-1]['measure_id'],
            'end_measure_id':result['measures'][b-1]['measure_id'],
            'start_sequence_index':a,'end_sequence_index':b,
            'start_pdf_page':first,'end_pdf_page':last,
            'category':'score_heading','claim_type':'score_observation','review_status':'unreviewed',
            'source_ids':['supplied-score'],'evidence':f'已查看原 PDF 第 {first} 页乐章标题图像。音轨与 MIDI 小节边界尚待人工试听。',
            'markdown':f'原谱这一乐章位于 PDF 第 **{first}–{last} 页**，乐章标题已按页面图像核验。\n\n'
                '可手动翻阅和放大总谱；当前尚无逐小节谱面坐标。时间轴来自 MIDI 辅助离线对齐，'
                '乐章间停顿、反复与片头片尾仍需试听确认。\n\n完整音乐学导聆和文献研究尚未编写。'})
    analysis={'format_version':'1.0.0','audio_sha256':media['video']['sha256'],'pdf_sha256':mapping['pdf_sha256'],
        'source_document':{'document_id':'supplied-score','path':mapping['pdf_path'],
            'sha256':mapping['pdf_sha256'],'title':'马勒第四 · 原谱乐章标题','review_status':'score_headings_checked'},
        'work':{'work_id':'mahler-symphony-4','title':'第四交响曲','original_title':'Symphonie Nr. 4',
            'composer':{'name':'古斯塔夫·马勒','original_name':'Gustav Mahler'},
            'instrumentation':'管弦乐与独唱（原谱第四乐章标有 Singstimme）'},
        'recording':{'soloists':[],'conductor':{'name':'克劳迪奥·阿巴多','original_name':'Claudio Abbado'},
            'ensemble':{'name':'琉森节日管弦乐团','original_name':'Lucerne Festival Orchestra','abbreviation':'LFO'},
            'duration_seconds':media['video']['duration_seconds'],
            'artist_information_note':'阵容与 2009 年份来自用户提供的视频文件名；独唱者和发行信息尚未核验。'},
        'annotations':notes,'references':[],'coverage':{'pdf_pages':pages,'guide_sections':0,'missing_pages':list(range(1,pages+1))},
        'reference_note':'尚未进行独立文献研究。当前仅列示原谱可核验的乐章标题。',
        'notice':'原谱乐章标题 · 完整导聆待编写 · 时间与小节坐标待复核',
        'markdown':'当前仅完成原谱四个乐章标题与页码范围核验，尚无完整音乐学分析。'}
    result['quality']['flag_counts']=dict(Counter(f for m in result['measures'] for f in m['flags']))
    result['limitations']=list(dict.fromkeys(result['limitations']))
    save(DATA/'measure-map.json',mapping);save(DATA/'alignment.json',result)
    if (DATA/'metadata/recording.json').exists():
        # Once a user document is bound, alignment recomputes must not replace
        # its annotations/references with the initial movement-title placeholder.
        from analysis_data import load_analysis
        imported=load_analysis(ROOT,DATA)
        save(DATA/'analysis/annotations.json',{k:v for k,v in imported.items() if k!='full_html'})
    else:save(DATA/'analysis/annotations.json',analysis)
    save(DATA/'project.json',{'format_version':'1.0.0','title':'马勒第四 · 视频本地试验',
        'inputs':[media['video'],{'kind':'pdf','path':mapping['pdf_path'],'sha256':mapping['pdf_sha256']},*movements],
        'privacy':{'processing':'local_only','media_uploaded':False},
        'processing_status':{'video_playback':'implemented','video_audio_extraction':'complete',
            'midi_auxiliary_alignment':'algorithmic_candidate',
            'pdf_bar_coordinates':mapping.get('status','missing'),
            'pdf_omr_only_alignment':'not_completed','human_listening_review':'pending',
            'musicological_analysis':'user_document_bound' if (DATA/'metadata/recording.json').exists() else 'pending'}})
    catalog=json.loads((ROOT/'library.json').read_text(encoding='utf-8'))
    if not any(t['id']=='mahler-4' for t in catalog['tracks']):
        catalog['tracks'].append({'id':'mahler-4','title':'马勒 · 第四交响曲（视频）','data_root':'works/mahler-4'})
        save(ROOT/'library.json',catalog)
    print(json.dumps({'measures':index,'pages':pages,'bar_coordinates':len(mapping['measures']),
        'score_regions':len(mapping.get('score_regions',[])),'verified_measures':0}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--align',action='store_true')
    parser.add_argument('--publish',type=Path,help='Existing raw result (never a human-corrected result)')
    args=parser.parse_args()
    DATA.mkdir(parents=True,exist_ok=True)
    manifest_path=DATA/'media-sync.json'
    if manifest_path.exists():
        media=json.loads(manifest_path.read_text(encoding='utf-8'))
        if media['video']['sha256']!=digest(next(SOURCE.glob('*.mp4'))):raise ValueError('视频已变化')
    else:media=prepare(next(SOURCE.glob('*.mp4')),DATA)
    movements=combine_midis()
    raw=args.publish
    if args.align:
        raw=DATA/'alignment.raw.json'
        subprocess.run([sys.executable,str(ROOT/'scripts/align_recording.py'),'--audio',str(ROOT/media['video']['path']),
            '--midi',str(DATA/'auxiliary.mid'),'--output',str(raw)],check=True)
    if raw:publish(raw.resolve(),media,movements)
