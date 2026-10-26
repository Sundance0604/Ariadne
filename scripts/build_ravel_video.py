"""Package a separate Ravel video clock, reusing the original score research.

Prepare the video, trim an explicitly reviewed analysis interval, and run
align_recording.py on that WAV first. This packages those observations; it
does not infer musical start/end from total duration or change the audio edition.
"""
import argparse
from collections import Counter
import copy
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from backend.structure_analysis.common import read,write,digest,bounded_path
from backend.musicxml_analysis.store import load_bundle
from backend.musicxml_analysis.live_store import load_live
from backend.musicxml_analysis.projection import rebind_projection


def build(output,raw_path,music_start,music_end,track_id='ravel-left-hand-video'):
    output,raw_path=Path(output).resolve(),Path(raw_path).resolve()
    if not output.is_relative_to(ROOT/'works') or not raw_path.is_relative_to(ROOT):
        raise ValueError('Use a separate work folder inside this repository')
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',track_id):raise ValueError('Invalid track ID')
    catalog=read(ROOT/'library.json')
    if any(t['id']==track_id for t in catalog['tracks']):raise ValueError('Track ID already registered; preserve the old edition and use a new ID')
    media=read(output/'media-sync.json');video=media['video']
    if video['sha256']!='f73028a0e26be3347fa11875a74df8f2ee12919bbb2c45fcd11d22db00b0e3d8':
        raise ValueError('This recording-metadata adapter is only for the supplied Aimard performance')
    if not media['hasAudio'] or media['masterClock']!='video':raise ValueError('Video must carry its own audio')
    if digest(bounded_path(ROOT,video['path']))!=video['sha256']:raise ValueError('Video changed')
    if not 0<=music_start<music_end<=video['duration_seconds']:raise ValueError('Invalid music interval')
    protected=['alignment.json','measure-map.json','metadata/recording.json','project.json',
        'analysis/structural-events.json','analysis/hermeneutic-essays.json',
        'analysis/musicxml/current.json','analysis/musicxml/interpretation-current.json']
    before={p:digest(ROOT/p) for p in protected}
    for name in ['review-anchors.json','score-region-anchors.json']:
        if (output/name).exists():raise ValueError('Existing local review must not be overwritten')
    if (output/'alignment.json').exists():raise ValueError('Existing video edition protected; use a new output folder')
    raw=read(raw_path)
    if raw.get('human_anchors') or any(m['review_status'] in {'verified','corrected'} for m in raw['measures']):
        raise ValueError('Raw packaging does not overwrite human review')
    if digest(bounded_path(ROOT,raw['audio']['path']))!=raw['audio']['sha256']:
        raise ValueError('Trimmed analysis audio changed')
    if abs(raw['audio']['duration_seconds']-(music_end-music_start))>.02:
        raise ValueError('Raw alignment does not cover the selected analysis interval')
    old=read(ROOT/'alignment.json');mapping=read(ROOT/'measure-map.json')
    if raw['symbolic_reference']['sha256']!=old['symbolic_reference']['sha256']:
        raise ValueError('Cannot reuse score geometry for another symbolic reference')
    if len(raw['measures'])!=len(old['measures']):raise ValueError('Measure counts differ')
    result=copy.deepcopy(raw);result['analysis_audio']=result['audio'];result['audio']=video
    result['playback_clock']='video'
    result['alignment_transform']={'raw_alignment_path':raw_path.relative_to(ROOT).as_posix(),
        'raw_alignment_sha256':digest(raw_path),'raw_audio_clock':'trimmed_video_audio_seconds',
        'video_seconds_offset':music_start,'source_video_sha256':video['sha256'],
        'method':'add the decoded music interval offset to DTW audio coordinates; do not scale time'}
    result['score_time_coverage']={'start_seconds':music_start,'end_seconds':music_end,
        'review_status':'agent_audiovisual_boundary_estimate_human_listening_pending',
        'basis':'Opening and ending video frames plus low-frequency tonal onset / final decay spectrogram; applause excluded from DTW input.'}
    for m,prior in zip(result['measures'],old['measures']):
        if m['measure_id']!=prior['measure_id'] or m['score_start_quarter']!=prior['score_start_quarter']:
            raise ValueError('Reference measure structure differs')
        for field in ['start_seconds','end_seconds']:m[field]+=music_start
        for field in ['printed_measure_number','numbering_status','pdf_mapping_status']:
            if field in prior:m[field]=prior[field]
        m['flags']=list(dict.fromkeys(m['flags']+[f for f in prior['flags'] if f.startswith(('pdf_','cadenza_pdf_'))]))
    for m in [result['measures'][0],result['measures'][-1]]:
        m['flags'].append('recording_edge_requires_listening');m['review_status']='needs_review'
    for point in result['time_map']:point['audio_seconds']+=music_start
    for marker in result['rehearsal_markers']:marker['audio_seconds']+=music_start
    result['quality']['flag_counts']=dict(Counter(f for m in result['measures'] for f in m['flags']))
    result['limitations']+=['Independent Aimard video performance; Zimerman recording times were not reused.',
        'Music interval estimated from audiovisual evidence; no human timing or expert note-by-note signoff.',
        'Before/after the music interval show the video without activating score-time harmony or instruments.']
    write(output/'alignment.json',result);write(output/'measure-map.json',mapping)
    metadata=read(ROOT/'metadata/recording.json')
    metadata['recording']={'recording_id':'ravel-left-hand-aimard-letonja-strasbourg-video',
        'soloists':[{'name':'皮埃尔-洛朗·艾马尔','original_name':'Pierre-Laurent Aimard','role':'钢琴独奏'}],
        'conductor':{'name':'Marko Letonja','original_name':'Marko Letonja'},
        'ensemble':{'name':'斯特拉斯堡爱乐乐团','original_name':'Strasbourg Philharmonic Orchestra'},
        'audio_sha256':video['sha256'],'artist_information_source':'supplied_video_embedded_description',
        'artist_information_note':'独奏者、指挥与乐团来自用户视频的内嵌说明；本版使用视频自带音轨。演出日期未独立核验。'}
    metadata['analysis_document']['editorial_note']='复用同版总谱导聆与研究；本视频为独立演出，已重新计算候选同步，时间仍待试听复核。'
    write(output/'metadata/recording.json',metadata)
    base=load_bundle(ROOT,ROOT);live=load_live(ROOT,ROOT,base)
    projection=rebind_projection(ROOT,output/'alignment.json',base,live['tables']['recording-projection'])
    projection_path=output/'musicxml-recording-projection.json';write(projection_path,projection)
    write(output/'project.json',{'format_version':'1.0.0','project_id':track_id,
        'title':'拉威尔 · 左手钢琴协奏曲（艾马尔视频）','shared_score_track':'ravel-left-hand',
        'inputs':[{'kind':'video',**video},{'kind':'pdf','path':mapping['pdf_path'],'sha256':mapping['pdf_sha256']},
            {'kind':'midi',**result['symbolic_reference']}],
        'files':{'alignment':'alignment.json','measure_map':'measure-map.json','recording_metadata':'metadata/recording.json',
            'musicxml_recording_projection':{'path':projection_path.relative_to(ROOT).as_posix(),'sha256':digest(projection_path)}},
        'privacy':{'processing':'local_only','media_uploaded':False,'video_published':False},
        'processing_status':{'midi_auxiliary_alignment':'independent_video_audio_DTW_candidate',
            'score_research':'shared_original_sources_not_duplicated','human_listening_review':'pending'}})
    index=next(i for i,t in enumerate(catalog['tracks']) if t['id']=='ravel-left-hand')
    catalog['tracks'].insert(index+1,{'id':track_id,'title':'拉威尔 · 左手钢琴协奏曲（艾马尔视频）',
        'data_root':output.relative_to(ROOT).as_posix(),'score_source':'ravel-left-hand'})
    after={p:digest(ROOT/p) for p in protected}
    if before!=after:raise ValueError('Original audio edition changed')
    write(output/'reports/source-preservation.json',{'before':before,'after':after,'unchanged':before==after})
    write(ROOT/'library.json',catalog)
    print(json.dumps({'track':track_id,'measures':len(result['measures']),
        'music_interval':[music_start,music_end],'original_preserved':True}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'works/ravel-left-hand-video')
    parser.add_argument('--raw',type=Path,required=True)
    parser.add_argument('--music-start',type=float,required=True)
    parser.add_argument('--music-end',type=float,required=True)
    parser.add_argument('--track-id',default='ravel-left-hand-video')
    args=parser.parse_args();build(args.output,args.raw,args.music_start,args.music_end,args.track_id)
