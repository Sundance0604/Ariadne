"""Build the deliberately small, agent-checked publication sample (not a full-work approval)."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from backend.video_export.content import read,write,digest,content_hash


def build():
    directory=ROOT/'works/ravel-left-hand-video';alignment=read(directory/'alignment.json')
    study=read(ROOT/'analysis/score-studies/ravel-study-20261026.json')
    base=ROOT/read(ROOT/'analysis/musicxml/current.json')['path']
    interpretation=ROOT/read(ROOT/'analysis/musicxml/interpretation-current.json')['path']
    frames=read(interpretation/'activation.json')['frames']
    window=next(w for w in study['windows'] if w['id']=='opening-bar-1')
    voices={v['id']:v for v in window['voices']}
    assert voices['cello-D']['notes'][0]['concert']=='D2' and voices['cello-G']['notes'][0]['concert']=='G2'
    assert voices['db-E']['notes'][0]['concert']=='E1' and voices['db-A']['notes'][0]['concert']=='A1'
    assert any(e['id']=='study-passing' and e['window_ids']==['horn-bassoon-bars-10-11'] for e in study['events'])
    opening=[f for f in frames if f['measure_id']=='xml-m0001']
    assert {p['part_id'] for f in opening for p in f['active_instruments']}=={'P32','P35','P36'}
    assert any('低音巴松'==p['label'] for f in frames if f['measure_id']=='xml-m0002' for p in f['active_instruments'])
    config={'format_version':'1.0','width':1920,'height':1080,'music_start_video':27.5,
        'music_start_confirmation':{'status':'user_confirmed','date':'2026-10-26','scope':'User confirmed the current Ravel music start is correct; not a signature for later alignment.'},
        'segments':[{'video_start':0,'video_end':95}], 'font':'Microsoft YaHei','font_size':32,
        'spacing':0,'yellow':'#FFDF42','minimum_caption_seconds':3,'characters_per_second':7,
        'score_zoom':1,'score_dpi':144,'crf':18,'preset':'fast',
        'layout':{
            'harmony':{'x':70,'y':60,'w':860,'h':160},
            'orchestration':{'x':1030,'y':45,'w':820,'h':160},
            'counterpoint':{'x':70,'y':400,'w':1030,'h':105},
            'form':{'x':70,'y':540,'w':1030,'h':105},
            'guide':{'x':70,'y':680,'w':1030,'h':150},
            'score':{'x':1260,'y':230,'w':600,'h':800},
            'interpretation':{'x':360,'y':880,'w':1200,'h':145,'font_size':38},
            'intro':{'x':180,'y':300,'w':1560,'h':600,'font_size':54}}}
    source_paths=['analysis/score-studies/ravel-study-20261026.json',
        'works/ravel-left-hand-video/metadata/recording.json',
        (interpretation/'activation.json').relative_to(ROOT).as_posix(),
        'analysis/essays/ravel-timbre-perspectives.md',
        'resource/ravel left hand piano concerto/analysis/Ravel_Left_Hand_Concerto_Full_Analysis.md']
    refs=[{'path':p,'sha256':digest(ROOT/p)} for p in source_paths]
    rows=[]
    def add(id,slot,start,end,text,phase='performance',precision='score_segment',basis=''):
        e={'id':id,'slot':slot,'video_start':start,'video_end':end,'text':text,'phase':phase,'timing_precision':precision}
        e['review']={'status':'approved','reviewer':'Codex','scope':'agent_source_check_for_short_video_excerpt',
            'human_signature':None,'sources':refs,'basis':basis or 'Selected score-study observations and existing prose, shortened without adding harmonic-function claims.',
            'content_sha256':content_hash(e)};rows.append(e)
    add('intro-title','interpretation',1,11,'莫里斯·拉威尔\n《左手钢琴协奏曲》\n钢琴：皮埃尔－洛朗·艾马尔','intro','source_interval')
    add('intro-reading','interpretation',11.5,24.5,'一只手，在钢琴上展开多个声部。\n聆听低音背景、旋律与伴奏之间的层次，\n以及独奏与乐队如何交换前景。','intro','source_interval')
    m=alignment['measures']
    add('opening-harmony','harmony',m[0]['start_seconds'],m[0]['end_seconds'],'E—A—D—G：四度骨架\n持续低音与分解音型相叠',basis='opening-bar-1 transcription; study-quartal reasoning; no third-based chord function asserted.')
    add('opening-orchestration','orchestration',m[0]['start_seconds'],m[0]['end_seconds'],'大提琴、低音提琴\n长音与六连音分层')
    add('bassoon-entry','orchestration',m[1]['start_seconds'],m[5]['end_seconds'],'低音巴松进入低弦背景\n旋律与伴奏分层',basis='XML m2 contains contrabassoon entry; caption describes an entry and texture, not an all-instruments-active list.')
    add('opening-counterpoint','counterpoint',m[0]['start_seconds'],m[0]['end_seconds'],'持续音与六连音\n构成不同节奏层',basis='study-arpeggio-layers; no imitation or strict counterpoint claimed.')
    add('opening-form','form',m[0]['start_seconds'],m[5]['end_seconds'],'开头：背景先建立，旋律随后进入',precision='page_range')
    add('opening-guide','guide',m[0]['start_seconds'],m[2]['end_seconds'],'先听持续音与流动音型的分工。',precision='page_range')
    add('texture-interpretation','interpretation',59,69,'相近的低音区里，长音托住流动音型；\n旋律从背景中显露，听觉的前景逐渐改变。',precision='page_range',basis='Interpretive listening prompt based on study-opening-orch and existing timbre essay; no exact bar-level formal boundary asserted.')
    add('horn-bassoon-counterpoint','counterpoint',m[9]['start_seconds'],m[10]['end_seconds'],'圆号与巴松节奏错开\n八度与六度先合并为层',basis='Directly transcribed horn-bassoon-bars-10-11; study-passing; limited to this checked window.')
    add('horn-bassoon-orchestration','orchestration',m[9]['start_seconds'],95,'圆号、巴松与低音巴松\n叠置于低弦背景',basis='XML m10-12 instrument entries and corresponding directly checked score pages; segment summary, not per-onset activity claim.')
    add('horn-bassoon-guide','guide',m[9]['start_seconds'],95,'把加倍合成一个音色层，再听各层如何交错。')
    target=directory/'video-export'
    if (target/'sample-captions.json').exists():raise ValueError('Existing caption reviews are preserved; use a separate revision')
    write(target/'sample-profile.json',config)
    write(target/'sample-captions.json',{'format_version':'1.0','video_sha256':alignment['audio']['sha256'],
        'alignment_sha256':digest(directory/'alignment.json'),'events':rows})
    print('Created 12 short-video captions with explicit agent review scope; no human signatures.')


if __name__=='__main__':build()
