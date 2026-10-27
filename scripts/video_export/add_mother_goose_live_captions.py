"""Add score-clock harmony/active-instrument captions to the editable video JSON.

Does not render media or replace the webpage's research snapshot.
"""
from pathlib import Path
from bisect import bisect_right
import json,re,sys,unicodedata,shutil
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from backend.video_export.content import read,write,digest


def instrument(label):
    s=unicodedata.normalize('NFKD',label).encode('ascii','ignore').decode().lower()
    solo='独奏' if 'solo' in s else ''
    if 'contrabassoon' in s:return '低音巴松'
    if any(v in s for v in ['contrebass','contrabass']):name='低音提琴'
    elif any(v in s for v in ['violoncell','violoncellos']):name='大提琴'
    elif any(v in s for v in ['viola','alto']):name='中提琴'
    elif any(v in s for v in ['violin','violon']):
        name='第一小提琴' if any(v in s for v in ['1er','violin 1']) else '第二小提琴' if any(v in s for v in ['2d','violin 2']) else '小提琴'
    elif any(v in s for v in ['cor anglais','english horn']):name='英国管'
    elif any(v in s for v in ['petite','piccolo']):name='短笛'
    elif any(v in s for v in ['flute','flutes']):name='长笛'
    elif any(v in s for v in ['hautbois','oboe']):name='双簧管'
    elif any(v in s for v in ['clarinet','clarinette']):name='单簧管'
    elif any(v in s for v in ['basson','bassoon']):name='巴松'
    elif any(v in s for v in ['cors','horn']):name='圆号'
    elif any(v in s for v in ['harp','harpe']):name='竖琴'
    elif 'celesta' in s:name='钢片琴'
    elif any(v in s for v in ['timbres','glockenspiel']):name='钟琴'
    elif any(v in s for v in ['timbales','timpani']):name='定音鼓'
    elif 'xylophone' in s:name='木琴'
    else:return label
    return solo+name


def main():
    folder=ROOT/'works/ravel-mother-goose-video';path=folder/'video-export/captions-optimized.json'
    document=read(path)
    if document.get('实时字幕'):raise ValueError('Real-time layer already exists; preserve user edits')
    live_dir=ROOT/read(folder/'playback/current.json')['path'];live=read(live_dir/'live.json')
    alignment=read(folder/'alignment.json')
    maps={m['movement']:m for m in alignment['time_maps']}
    def project(q,movement):
        points=maps[movement]['time_map'];seconds=q*.5
        xs=[p['midi_seconds'] for p in points]
        if seconds<xs[0]-1e-7 or seconds>xs[-1]+1e-7:return None
        j=max(0,min(len(points)-2,bisect_right(xs,seconds)-1));a,b=points[j:j+2]
        return a['audio_seconds']+(seconds-a['midi_seconds'])/(b['midi_seconds']-a['midi_seconds'])*(b['audio_seconds']-a['audio_seconds'])
    qualities={'major triad':'大三和弦','minor triad':'小三和弦','diminished triad':'减三和弦','augmented triad':'增三和弦','dominant seventh chord':'属七型和弦','major seventh chord':'大七和弦','minor seventh chord':'小七和弦','half-diminished seventh chord':'半减七和弦','diminished seventh chord':'减七和弦'}
    rows=[];last={};facts={}
    for frame in live['frames']:
        movement=int(frame['measure_id'].split('-')[1]);start=project(frame['start_q'],movement);end=project(frame['end_q'],movement)
        if start is None or end is None or end-start<.01:continue
        window=live['windows'].get(frame['harmony_window_id'])
        if window:
            chord=window.get('chord');bass=window.get('bass',{}).get('name','')
            if chord:
                inversion=['原位','第一转位','第二转位','第三转位'][chord.get('inversion',0)]
                harmony=f"{chord['root']}{qualities.get(chord['quality'],chord['quality'])} · {inversion}"
            else:
                pitches=list(dict.fromkeys(re.sub(r'-?\d+$','',p) for p in window.get('pitches',[])))
                harmony='当下音集：'+'、'.join(pitches)
            harmony+='\n最低记谱实音：'+bass if bass else ''
            if window.get('display_label'):harmony='泛音织体'
        else:harmony='此时无可用定音区间'
        parts=frame['active_instruments'];names=list(dict.fromkeys(instrument(p['label']) for p in parts))
        orchestra='记谱活动：'+'、'.join(names) if names else '此时无可用分部活动'
        for label,text,title in [('和弦',harmony,'实时和声'),('配器',orchestra,'实时配器')]:
            previous=last.get(label)
            if previous and previous['文字']==text and abs(previous['结束秒']-start)<1e-7:
                previous['结束秒']=end;previous['实时帧'].append(frame['id'])
            else:
                row={'编号':f"live-{label}-{frame['id']}",'栏目':label,'开始秒':start,'结束秒':end,'标题':title,'文字':text,'显示':True,'实时帧':[frame['id']]}
                rows.append(row);last[label]=row
        facts[frame['id']]={'小节':frame['measure_id'],'开始四分音符':frame['start_q'],'结束四分音符':frame['end_q'],
            '和声窗口':frame['harmony_window_id'],'源音符':window.get('event_ids',[]) if window else [],
            '活跃分部':[{'id':p['part_id'],'原名':p['label'],'中文显示':instrument(p['label']),'源音符':p['event_ids']} for p in parts]}
    backup=ROOT/'local/video-export/mother-goose/captions-before-realtime.json';backup.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,backup)
    # Keep all original wording editable. The two slow background channels are
    # disabled where the exact-interval layer now occupies the same slots.
    for row in document['字幕']:
        if row['栏目'] in {'和弦','配器'} and not row['编号'].startswith('ballet-interlude'):
            row['显示']=False;row['保留原因']='分段背景原稿保留；同槽位改用实时字幕，避免重叠'
    document['字幕'].extend(rows);document['字幕'].sort(key=lambda r:(float(r['开始秒']),r['栏目'],r['编号']))
    document['字号']['配器']=30
    document['实时字幕']={'来源':'XML实际记谱区间经独立DTW投影，非音频分离','实时条数':len(rows),'原分段稿条数':267,
        '连续显示规则':'按实际区间更新，不套用长段落的最短3秒阅读规则；同字相邻区间合并，不延长到下一音响',
        '无参考连接':'1045.2–1147.0及1361.6–1448.8仅保留已有音色导聆，不外推实时和声或乐器',
        '活跃名称规则':'中文乐器类名合并同名分部；全部原分部与源音符保存在实时证据，不把合并名称数当演奏人数',
        'source_sha256':digest(live_dir/'live.json'),'alignment_sha256':digest(folder/'alignment.json'),
        '证据文件':'works/ravel-mother-goose-video/video-export/realtime-evidence.json','human_signoff':None}
    write(folder/'video-export/realtime-evidence.json',{'frames':facts,'source_sha256':digest(live_dir/'live.json')})
    write(path,document)
    report=read(folder/'video-export/optimization-report.json');report['editable_sha256']=digest(path);report['realtime_layer']=document['实时字幕'];report['status']='editable_json_ready_user_will_render_and_review';write(folder/'video-export/optimization-report.json',report)
    print(json.dumps({'realtime_captions':len(rows),'original_rows_preserved':267,'output':str(path)},ensure_ascii=True))


if __name__=='__main__':main()
