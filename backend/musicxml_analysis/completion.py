"""Parallel harmonic readings and source-bound score-time activation evidence."""
from collections import defaultdict,Counter
from fractions import Fraction as F
from pathlib import Path
import bisect
import json
from backend.structure_analysis.common import read,write,digest,bounded_path
from .store import load_bundle
from .analyze import chord_description

QUALITY={'major triad':'大三和弦','minor triad':'小三和弦','diminished triad':'减三和弦','augmented triad':'增三和弦',
    'dominant seventh chord':'属七和弦','major seventh chord':'大七和弦','minor seventh chord':'小七和弦',
    'half-diminished seventh chord':'半减七和弦','diminished seventh chord':'减七和弦'}
INV=['原位','第一转位','第二转位','第三转位']
PART_NAMES=['长笛','短笛','双簧管','英国管','降E调单簧管','单簧管','低音单簧管','巴松','低音巴松',
    '圆号1／2','圆号3／4','小号1／2','小号3','长号1／2','长号3／大号','定音鼓','三角铁','打击乐组（Batteria）','钹','大鼓','锣',
    '竖琴','钢琴独奏','第一小提琴','第一小提琴分部2','第一小提琴分部3','第二小提琴','第二小提琴分部2','第二小提琴分部3',
    '中提琴','中提琴分部2','大提琴','大提琴分部2','大提琴分部3','低音提琴','低音提琴分部2','低音提琴分部3']


def functions(description,contexts):
    from music21 import chord,key,roman,pitch
    if not description['chord']:return []
    # Roman figures describe chord members/inversion, not orchestral octave
    # doublings. music21 can emit redundant altered figures if all octaves
    # are supplied. Preserve the bass and one spelled tone per pitch class.
    unique={}
    for p in sorted((pitch.Pitch(n.replace('b','-')) for n in description['spelled_pitches']),key=lambda p:p.ps):
        unique.setdefault(p.pitchClass,p)
    c=chord.Chord(list(unique.values()));result=[]
    for k in contexts[:2]:
        rn=roman.romanNumeralFromChord(c,key.Key(k['tonic'].replace('b','-'),k['mode']))
        result.append({'context':k['tonic']+('大调' if k['mode']=='major' else '小调'),'figure':rn.figure,
            'status':'conditional_key_reading_not_resolved_function'})
    return result


def label(description):
    c=description['chord']
    if c:return c['root']+QUALITY.get(c['quality'],c['quality'])+' / '+c['bass']+'（'+INV[min(c['inversion'],3)]+'）'
    if 'quartal' in description.get('structures',[]):return '四度结构 · '+', '.join(description['spelled_pitches'])
    if 'anhemitonic_pentatonic' in description.get('structures',[]):return '无半音五声音集 · '+', '.join(description['spelled_pitches'])
    return '实音集合 · '+', '.join(description['spelled_pitches'])


def readings(window,by_id,contexts):
    members=[by_id[id] for id in window['event_ids']];s=window['sonority'];out=[]
    literal={'id':window['id']+'-literal','kind':'complete_vertical','label':label(s),
        'description':s,'event_ids':window['event_ids'],'omitted_event_ids':[],
        'functions':functions(s,contexts),'basis':'当前有效记谱事件全部计入；级数随局部调性读法并列','status':'source_derived'}
    if s['chord'] or s.get('structures'):out.append(literal)
    # An octave-doubled bass PC can occur above the lowest pitch. Remove the
    # entire explicitly named bass layer, not merely the single lowest note.
    if s['bass']:
        bass_pc=s['bass']['pc'];bass_events=[e for e in members if e['concert_pitch']['pc']==bass_pc]
        upper=[e for e in members if e['concert_pitch']['pc']!=bass_pc]
        if upper and any(F(e['duration_q'])>=1 for e in bass_events):
            u=chord_description(upper)
            if u['chord']:
                out.append({'id':window['id']+'-bass-layer','kind':'bass_pitch_class_layer_reduction',
                    'label':u['chord']['root']+QUALITY.get(u['chord']['quality'],u['chord']['quality'])+' / '+s['bass']['name']+'持续层',
                    'description':u,'event_ids':[e['id'] for e in upper],'bass_event_ids':[e['id'] for e in bass_events],
                    'omitted_event_ids':[e['id'] for e in bass_events],'functions':functions(u,contexts),
                    'basis':'低音音级层单独列出；其余同时音构成上层和弦。不自动把低音判作和弦外音。',
                    'status':'alternative_layer_interpretation'})
    families=[('弦乐层',{f'P{i}' for i in range(24,38)}),('木管层',{f'P{i}' for i in range(1,10)}),
        ('铜管层',{f'P{i}' for i in range(10,16)}),('钢琴层',{'P23'})]
    if len(out)<2 and not s['chord']:
        for name,ids in families:
            ns=[e for e in members if e['part_id'] in ids]
            if not ns or len(ns)==len(members):continue
            d=chord_description(ns)
            if d['chord']:
                out.append({'id':window['id']+'-'+name,'kind':'instrument_family_layer','label':name+'：'+label(d),
                    'description':d,'event_ids':[e['id'] for e in ns],
                    'omitted_event_ids':[e['id'] for e in members if e not in ns],
                    'functions':functions(d,contexts),'basis':'只对明确列出的乐器层归约，其他声部仍保留。','status':'alternative_layer_interpretation'})
                if len(out)>=2:break
    if not out:out=[literal]
    elif not s['chord'] and not s.get('structures') and all(r['kind']!='complete_vertical' for r in out):
        # A useful layer is the headline; the full collection stays available.
        out=(out+[literal])[:2]
    return out[:2]


def build(root,output):
    import mido
    root=Path(root).resolve();bundle=load_bundle(root,root);out=bounded_path(root,output)
    if out.exists():raise ValueError('Choose a new completion directory')
    tables=bundle['tables'];events=tables['events']['events'];by_id={e['id']:e for e in events}
    contexts={k['measure_id']:k['candidates'] for k in tables['harmony']['key_contexts']}
    print('Computing parallel full-score harmonic readings.',flush=True)
    interpretations={w['id']:readings(w,by_id,contexts[w['measure_id']]) for w in tables['harmony']['windows']}
    names={p['id']:PART_NAMES[i] for i,p in enumerate(tables['parts']['parts'])}
    instrument_registry={i['id']:i['name'] for p in tables['parts']['parts'] for i in p['score_instruments']}
    active_events=[e for e in events if (e['analysis_eligible'] or e['kind']=='unpitched') and not e['exclusion_reason'] and F(e['duration_q'])>0]
    starts=defaultdict(list);ends=defaultdict(list)
    for e in active_events:starts[F(e['score_start_q'])].append(e);ends[F(e['score_end_q'])].append(e)
    points=sorted(set(starts)|set(ends)|{F(m['start_q']) for m in tables['measures']['measures']})
    windows=tables['harmony']['windows'];hstarts=[F(w['start_q']) for w in windows]
    ms=tables['measures']['measures'];mstarts=[F(m['start_q']) for m in ms];active={};frames=[]
    for a,b in zip(points,points[1:]):
        for e in ends[a]:active.pop(e['id'],None)
        for e in starts[a]:active[e['id']]=e
        mi=bisect.bisect_right(mstarts,a)-1;m=ms[mi];hi=bisect.bisect_right(hstarts,a)-1
        h=windows[hi] if hi>=0 and a<F(windows[hi]['end_q']) else None
        groups=defaultdict(list)
        for e in active.values():groups[e['part_id']].append(e)
        instruments=[];pitched=[e for e in active.values() if e['concert_pitch']]
        bass=min((e['concert_pitch']['ps'] for e in pitched),default=None)
        for pid,ns in groups.items():
            roles=[]
            if any(e['concert_pitch'] and e['concert_pitch']['ps']==bass for e in ns):roles.append('低音支撑')
            if any(F(e['duration_q'])>=1 for e in ns):roles.append('持续层')
            if any(F(e['duration_q'])<=F(1,2) for e in ns):roles.append('短音／运动层')
            if any(e['kind']=='unpitched' for e in ns):roles.append('节奏／音色层')
            instruments.append({'part_id':pid,'label':names[pid],
                'instrument_names':sorted({instrument_registry[e['instrument_ref']] for e in ns if e.get('instrument_ref') in instrument_registry}),
                'pitches':sorted({e['concert_pitch']['name'] for e in ns if e['concert_pitch']}),
                'roles':roles,'event_ids':[e['id'] for e in ns]})
        frames.append({'id':f'xml-live-{len(frames)+1:06d}','start_q':float(a),'end_q':float(b),
            'measure_id':m['measure_id'],'number':m['number'],'page':m['page'],'onset_q':str(a-F(m['start_q'])),
            'harmony_window_id':h['id'] if h else None,'active_instruments':instruments})
    # The existing recording alignment remains authoritative for playback.
    # Only tempo/measure structure bridges its reference clock to XML quarters.
    alignment=read(root/'alignment.json');midi_path=bounded_path(root,alignment['symbolic_reference']['path'])
    if digest(midi_path)!=alignment['symbolic_reference']['sha256']:raise ValueError('Recording reference MIDI changed')
    midi=mido.MidiFile(midi_path);tick=0;seconds=0.;tempo=500000;clock=[{'tick':0,'midi_seconds':0,'seconds_per_tick':tempo/1000000/midi.ticks_per_beat}]
    for event in mido.merge_tracks(midi.tracks):
        seconds+=mido.tick2second(event.time,midi.ticks_per_beat,tempo);tick+=event.time
        if event.type=='set_tempo':
            tempo=event.tempo;clock.append({'tick':tick,'midi_seconds':seconds,'seconds_per_tick':tempo/1000000/midi.ticks_per_beat})
    checks=[]
    if len(alignment['measures'])!=len(ms):raise ValueError('Recording/XML measure structure differs')
    for old,m in zip(alignment['measures'],ms):
        start=abs(old['score_start_quarter']-float(F(m['start_q'])))<1e-7
        duration=abs(old['score_end_quarter']-old['score_start_quarter']-float(F(m['duration_q'])))<1e-7
        checks.append({'measure_id':m['measure_id'],'start_agrees':start,'duration_agrees':duration})
        if not start or not duration and m!=ms[-1]:raise ValueError('Unresolved XML/reference structural clock mismatch')
    projection={'xml_sha256':bundle['manifest']['source']['sha256'],'midi_sha256':digest(midi_path),
        'audio_sha256':alignment['audio']['sha256'],'alignment_sha256':digest(root/'alignment.json'),
        'ppq':midi.ticks_per_beat,'reference_clock':clock,'reference_end_seconds':alignment['symbolic_reference']['duration_seconds'],
        'reference_end_quarter':alignment['measures'][-1]['score_end_quarter'],'measure_checks':checks,
        'status':'existing_DTW_recording_projection_estimated_not_per_note_calibrated',
        'basis':'MIDI tempo and measure structure only, not MIDI–PDF note correspondence; no fixed BPM or time-per-page mapping',
        'tail_policy':'Do not extrapolate the truncated reference into the last 0.4 XML quarters.'}
    units=[('intro',1,33,'管弦乐引子：材料的预呈示与积累'),('cadenza-1',33,64,'首次独奏华彩：展开与呈示功能交叠'),
        ('orchestral-return',63,88,'乐队重入与主题确认'),('lyric',88,126,'更慢的抒情对比与连接'),
        ('allegro',126,480,'快段及其内部发展'),('cadenza-2',480,521,'后华彩：回忆与重组'),
        ('reconstruction',520,531,'重叠式乐队重建'),('coda',531,536,'Allegro压缩尾声')]
    form=[]
    for id,first,last,title in units:
        members=[m for m in ms if first<=m['sequence']<last]
        counts=Counter(k['candidates'][0]['tonic']+' '+k['candidates'][0]['mode'] for k in tables['harmony']['key_contexts'] if k['measure_id'] in {m['measure_id'] for m in members})
        form.append({'id':id,'title':title,'xml_range':[first,last],'range_semantics':'half_open_with_explicit_overlap_at_m520',
            'start_q':members[0]['start_q'],'end_q':str(F(members[-1]['start_q'])+F(members[-1]['duration_q'])),
            'key_profile_summary':dict(counts),'evidence_measure_ids':[m['measure_id'] for m in members],
            'status':'agent_structural_synthesis_not_human_expert_signoff'})
    boundary63=F(ms[62]['start_q'])+F(7,4)
    for section in form:
        if section['id']=='cadenza-1':section['end_q']=str(boundary63)
        if section['id']=='orchestral-return':section['start_q']=str(boundary63)
        if section['id']=='reconstruction':section['start_q']=str(F(ms[519]['start_q'])+2)
    out.mkdir(parents=True)
    documents={'harmonic-readings.json':{'readings':interpretations},'activation.json':{'frames':frames},'recording-projection.json':projection,
        'form-synthesis.json':{'sections':form,'boundary_details':[
            {'measure_id':'xml-m0063','onset_q':'7/4','meaning':'乐队弱起重入；不把m63全小节归入同一功能'},
            {'measure_id':'xml-m0520','onset_q':'2','meaning':'低弦进入，钢琴尚未退出'},
            {'measure_id':'xml-m0520','onset_q':'11/4','meaning':'低音单簧管随后进入'}],
            'models':[{'name':'速度与织体的四阶段回旋','reading':'慢段呈示／华彩—快段发展—后华彩回忆与重建—快尾声','status':'functional_description'},
                {'name':'奏鸣功能读法','reading':'呈示、发展及回归功能交叠；主题与调性对应不足处保留双重功能，不宣告标准奏鸣曲式','status':'alternative_formal_model'}]}}
    for name,document in documents.items():(out/name).write_text(json.dumps(document,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    manifest={'base_run':bundle['run_path'],'base_manifest_sha256':digest(root/bundle['run_path']/'manifest.json'),
        'source':bundle['manifest']['source'],'analysis_code_sha256':digest(Path(__file__)),
        'files':{name:{'sha256':digest(out/name),'bytes':(out/name).stat().st_size} for name in documents},
        'summary':{'harmonic_windows':len(interpretations),'ambiguous_windows':sum(len(r)>1 or len(r[0]['functions'])>1 for r in interpretations.values()),
            'activation_frames':len(frames),'formal_sections':len(form),'human_signoffs':0},
        'review_status':'agent_rule_reviewed_with_explicit_alternatives; human_expert_signoff_not_claimed'}
    write(out/'manifest.json',manifest);write(root/'analysis/musicxml/interpretation-current.json',{
        'path':out.relative_to(root).as_posix(),'manifest_sha256':digest(out/'manifest.json')})
    print(json.dumps(manifest['summary']),flush=True)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    build(Path(__file__).resolve().parents[2],args.output)
