"""Extend the existing Prokofiev web edition with written note activity.

Reuses the frozen auxiliary clock and recording DTW, never PDF interpolation.
The previous playback snapshot and original analytical research are preserved.
"""
from pathlib import Path
from collections import defaultdict, Counter
from fractions import Fraction as F
import argparse, bisect, json, sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from prokofiev2_sync import WORK, SOURCE, read, write, record, digest, log


def compact(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf8')


def source_notes():
    """Enrich the already selected notes; include genuine unpitched activity."""
    from backend.musicxml_analysis.ingest import xml_root, note_metadata, pitch_record
    import music21 as m21
    root,_=xml_root(SOURCE);result={};unpitched=[]
    for part in root.findall('part'):
        pid=part.get('id');div=None;transposes={}
        for seq,measure in enumerate(part.findall('measure'),1):
            cursor=F(0);previous=F(0);ni=0
            for child in measure:
                if child.tag=='attributes':
                    if child.find('divisions') is not None:div=int(child.findtext('divisions'))
                    for t in child.findall('transpose'):
                        octave=int(t.findtext('octave-change','0'))
                        transposes[t.get('number','all')]=(int(t.findtext('diatonic','0'))+7*octave,
                            int(t.findtext('chromatic','0'))+12*octave)
                elif child.tag in {'backup','forward'}:
                    cursor+=(1 if child.tag=='forward' else -1)*F(child.findtext('duration','0'))/(div or 1)
                elif child.tag=='note':
                    ni+=1;duration=F(child.findtext('duration','0'))/(div or 1)
                    onset=previous if child.find('chord') is not None else cursor
                    if child.find('chord') is None:
                        previous=onset
                        if child.find('grace') is None:cursor+=duration
                    identity=f'{pid}-xml-m{seq:04d}-n{ni:04d}'
                    pitch=child.find('pitch');encoded=concert=None
                    if pitch is not None:
                        p=m21.pitch.Pitch();p.step=pitch.findtext('step');p.octave=int(pitch.findtext('octave'))
                        p.accidental=float(pitch.findtext('alter','0'));encoded=pitch_record(p)
                        dia,chrom=transposes.get(child.findtext('staff','1'),transposes.get('all',(0,0)))
                        interval=m21.interval.intervalFromGenericAndChromatic(dia+1 if dia>=0 else dia-1,chrom)
                        concert=pitch_record(p.transpose(interval)) if chrom or dia else encoded
                    meta={**note_metadata(child),'tie':[t.get('type') for t in child.findall('tie')],
                        'articulations':[x.tag for x in child.findall('notations/articulations/*')],
                        'notations_xml':[__import__('xml.etree.ElementTree',fromlist=['tostring']).tostring(x,encoding='unicode') for x in child.findall('notations')],
                        'encoded_pitch':encoded,'concert_pitch':concert,
                        'harmonic_notation':child.find('.//harmonic') is not None}
                    result[identity]=meta
                    if child.find('unpitched') is not None and pid!='P14' and div and duration>0 and child.find('grace') is None and child.get('print-object')!='no' and child.findtext('notehead')!='none':
                        unpitched.append({'id':identity,'part_id':pid,'sequence':seq,'onset_q':str(onset),
                            'duration_q':str(duration),'voice':child.findtext('voice','1'),'staff':child.findtext('staff','1'),**meta})
    return result,unpitched


def instrument_family(pid):
    n=int(pid[1:])
    return '木管' if n<=4 else '铜管' if n<=8 else '打击乐' if n<=13 else '键盘／拨弦' if n==15 else '弦乐'


def project_events(doc,metadata,unpitched):
    labels={p['id']:p['name'] for p in doc['parts']};events=[];audit=[]
    clipped={e['event_id'] for e in doc['clipped_reference_ends']}
    for old in doc['events']:
        meta=metadata[old['id']]
        if abs(meta['concert_pitch']['ps']-old['ps'])>1e-7:raise ValueError('Transpose differs from frozen reference')
        e={**old,**meta,'kind':'note','analysis_eligible':True,'exclusion_reason':None,
            'score_start_q':old['start_q'],'score_end_q':old['end_q'],'technique_context':[],
            'reference_end_clipped':old['id'] in clipped}
        events.append(e)
    for old in unpitched:
        m=doc['measures'][old['sequence']-1];a=F(old['onset_q']);b=a+F(old['duration_q']);length=F(m['duration_q'])
        if a<0 or a>=length:
            audit.append({'event_id':old['id'],'reason':'unpitched_outside_auxiliary_bar'});continue
        if b>length:audit.append({'event_id':old['id'],'reason':'unpitched_end_clipped_to_auxiliary_bar'});b=length
        start=str(F(m['start_q'])+a);end=str(F(m['start_q'])+b)
        events.append({**old,'measure_id':m['measure_id'],'movement':m['movement'],'label':labels[old['part_id']],
            'kind':'unpitched','ps':None,'analysis_eligible':False,'exclusion_reason':None,
            'start_q':start,'end_q':end,'score_start_q':start,'score_end_q':end,'technique_context':[]})
    return events,audit


def flow_notes(events,alignment):
    """Join contiguous tie segments without confusing a repeated attack with a tie."""
    from bisect import bisect_right
    points=alignment['time_map'];xs=[r['midi_seconds'] for r in points]
    def seconds(q):
        x=float(F(q))*.5;i=bisect_right(xs,x)-1
        if i<0 or x>xs[-1]+1e-8:return None
        if i==len(xs)-1:return points[-1]['audio_seconds']
        a,b=points[i],points[i+1]
        return a['audio_seconds']+(x-a['midi_seconds'])/(b['midi_seconds']-a['midi_seconds'])*(b['audio_seconds']-a['audio_seconds'])
    output=[];pending={};joined=0
    for e in sorted((e for e in events if e['kind']=='note'),key=lambda e:(F(e['start_q']),e['id'])):
        key=(e['movement'],e['part_id'],e['staff'],e['voice'],e['ps'])
        prior=pending.pop(key,None)
        if 'stop' in e['tie'] and prior and F(prior['end_q'])==F(e['start_q']):
            prior['end_q']=e['end_q'];prior['event_ids'].append(e['id']);joined+=1;row=prior
        else:
            row={'id':e['id'],'event_ids':[e['id']],'part_id':e['part_id'],'label':e['label'],
                'family':instrument_family(e['part_id']),'staff':e['staff'],'voice':e['voice'],
                'movement':e['movement'],'pitch':e['ps'],'pc':int(e['ps'])%12,'name':e['concert_pitch']['name'],
                'start_q':e['start_q'],'end_q':e['end_q']};output.append(row)
        if 'start' in e['tie']:pending[key]=row
    for row in output:row['start_seconds']=seconds(row['start_q']);row['end_seconds']=seconds(row['end_q'])
    return {'notes':output,'tied_segments_joined':joined,'clock':'video_seconds_from_existing_DTW',
        'limitations':['Encoded note duration only; not acoustic sustain or loudness.','Ties join only contiguous same-part/staff/voice/pitch segments.','Grace notes, Ossia and quarantined timing events are omitted; no fabricated durations.']}


def build():
    from backend.prokofiev2 import bundle
    from backend.musicxml_analysis.analyze import chord_description
    old,_=bundle(ROOT,WORK);pointer=read(WORK/'playback/current.json')
    out=WORK/'playback/yuja-jarvi-20261027-live-v1'
    if out.exists():raise ValueError('Live snapshot already exists; preserve it and choose a new version')
    doc=read(WORK/'sync/reference/written.json');alignment=read(WORK/'alignment.json');mapping=read(WORK/'measure-map.json')
    metadata,unpitched=source_notes();events,extra_audit=project_events(doc,metadata,unpitched)
    boxes={b['measure_id']:b for b in mapping['measures']};quarantine=set(doc['quarantine']['sequences'])
    measures=[{**m,'sequence':m['sequence_index'],'number':f"{m['movement']}-{m['local_number']}",
        'page':boxes[m['measure_id']]['page_number']} for m in doc['measures']]
    starts=defaultdict(list);ends=defaultdict(list);by_measure=defaultdict(list)
    for e in events:starts[F(e['start_q'])].append(e);ends[F(e['end_q'])].append(e);by_measure[e['measure_id']].append(e)
    points=sorted(set(starts)|set(ends)|{F(m['start_q']) for m in measures}|{F(doc['quarter_duration'])})
    frames=[];windows={};active={};mi=0;cache={};harmony_by_measure=defaultdict(list)
    for start,end in zip(points,points[1:]):
        for e in ends[start]:active.pop(e['id'],None)
        for e in starts[start]:active[e['id']]=e
        while mi+1<len(measures) and F(measures[mi+1]['start_q'])<=start:mi+=1
        m=measures[mi];es=list(active.values());pitched=[e for e in es if e['kind']=='note'];groups=defaultdict(list)
        for e in es:groups[e['part_id']].append(e)
        incomplete=m['sequence_index'] in quarantine
        uncertainty=['钢琴XML时值待核；当前活动与音集不完整'] if incomplete else []
        instruments=[{'part_id':pid,'label':rows[0]['label'],'family':instrument_family(pid),
            'instrument_names':[rows[0]['label']],'pitches':sorted({e['concert_pitch']['name'] for e in rows if e['concert_pitch']}),
            'roles':[],'event_ids':[e['id'] for e in rows],'unpitched':all(e['kind']=='unpitched' for e in rows)} for pid,rows in groups.items()]
        identity=f'prok2-live-{len(frames)+1:06d}';onset=str(start-F(m['start_q']))
        frame={'id':identity,'start_q':float(start),'end_q':float(end),'measure_id':m['measure_id'],'number':m['number'],
            'page':m['page'],'onset_q':onset,'harmony_window_id':identity if pitched or incomplete else None,
            'active_instruments':instruments,'activity_uncertainty':uncertainty}
        frames.append(frame)
        if pitched or incomplete:
            key=tuple(sorted({(e['concert_pitch']['name'],e['ps']) for e in pitched}))
            if key not in cache:cache[key]=chord_description(pitched)
            sonority=cache[key];names=sorted({e['concert_pitch']['name'] for e in pitched},key=lambda n:next(e['ps'] for e in pitched if e['concert_pitch']['name']==n))
            w={**sonority,'id':identity,'measure_id':m['measure_id'],'start_q':str(start),'end_q':str(end),
                'onset_q':onset,'event_ids':[e['id'] for e in pitched],'pitches':names,'incomplete':incomplete}
            if incomplete:w['chord']=None;w['display_label']='已知部分音集：'+('、'.join(names) or '无可用定音')+'（钢琴时值待核）'
            elif any(e['harmonic_notation'] for e in pitched):w['chord']=None;w['display_label']='含泛音记号的XML编码音：'+'、'.join(names)+'（实响另核）'
            windows[identity]=w;harmony_by_measure[m['measure_id']].append(w)
    clock=[{'tick':0,'midi_seconds':0,'seconds_per_tick':.5/960}]
    research=read(old/'research.json');analysis=read(old/'analysis.json')
    scope='当前表为XML有效定音与非定音事件的DTW候选投影；休止、装饰音、Ossia和异常钢琴时值未冒充有效音符。'
    research['musicxml']={'summary':{'measures':len(measures),'parts':len(doc['parts'])-1,'events':len(events)},
        'measures':measures,'table_scope':'written_activity_with_explicit_timing_exclusions','scope_note':scope,'review_status':'agent_candidate_human_pending'}
    research['notice']='实时音集与活跃乐器来自XML记谱区间及原录音DTW；并非声音源分离或人工逐音审定。'
    forms=[{'id':s['id'],'title':s['title'],'start_q':doc['measures'][s['first_sequence']-1]['start_q'],
        'end_q':doc['measures'][s['last_sequence']-1]['end_q'],'xml_range':[s['first_sequence'],s['last_sequence']+1],
        'level':'guide_segment','argument':'沿用已有38段导聆范围，不新增严格曲式裁定'} for s in read(WORK/'analysis/sections.json')['sections']]
    live={'available':True,'work_id':doc['work_id'],'projection':{'ppq':960,'reference_clock':clock,
        'reference_end_seconds':float(F(doc['quarter_duration']))*.5,'reference_end_quarter':float(F(doc['quarter_duration'])),
        'audio_sha256':alignment['audio']['sha256'],'alignment_sha256':digest(WORK/'alignment.json'),
        'source_sha256':digest(SOURCE),'reference_sha256':digest(WORK/'sync/reference/written.json')},
        'frames':frames,'windows':windows,'readings':{},'form':{'sections':forms,'models':[]},
        'hud_cases':{'cases':[],'contexts':[]},'roman_audit':None,'limitations':[scope,
            'Chord identities reuse the existing chord_description method; no new functional harmony or GNN.',
            'Timing is the existing DTW candidate; no claim of independent per-note calibration.']}
    evidence={}
    for m in measures:
        ws=[{**w,'sonority':{**w,'label':w.get('display_label') or '、'.join(w['pitches'])}} for w in harmony_by_measure[m['measure_id']]]
        evidence[m['measure_id']]={'measure':m,'scope_note':scope,'events':by_measure[m['measure_id']],
            'part_registry':doc['parts'],'harmony':ws,'harmonic_readings':{},'orchestration':[],
            'intervals':[],'chordal_intervals':[],'hierarchy':[],'motif_comparisons':[],'cadences':[],
            'limitations':(['钢琴时值异常，不能把缺失活动理解为钢琴休止。'] if m['sequence_index'] in quarantine else [])}
    flow=flow_notes(events,alignment);flow.update(work_id=doc['work_id'],source=record(SOURCE),
        video=alignment['audio'],alignment_sha256=digest(WORK/'alignment.json'),coverage=alignment['score_time_coverage'])
    out.mkdir(parents=True)
    for name,value in [('analysis.json',analysis),('research.json',research),('live.json',live),('evidence.json',{'measures':evidence}),('flow.json',flow)]:compact(out/name,value)
    audit={'source':record(SOURCE),'events':len(events),'pitched':sum(e['kind']=='note' for e in events),
        'unpitched':sum(e['kind']=='unpitched' for e in events),'activation_frames':len(frames),'chord_cache_entries':len(cache),
        'tied_segments_joined':flow['tied_segments_joined'],'quarantine':doc['quarantine'],
        'clipped_reference_ends':doc['clipped_reference_ends'],'unpitched_audit':extra_audit,
        'old_snapshot':pointer,'human_signoff':None,'expert_review':None}
    write(out/'audit.json',audit)
    manifest={'schema_version':1,'work_id':doc['work_id'],'scope':'Existing web synchronization plus written activity; sample export reads the same flow notes.',
        'inputs':[record(p) for p in [WORK/'alignment.json',WORK/'measure-map.json',WORK/'media-sync.json',
            WORK/'sync/reference/written.json',SOURCE,Path(__file__),ROOT/'backend/musicxml_analysis/analyze.py',
            old/'analysis.json',old/'research.json',WORK/'analysis/sections.json']],
        'files':{p.name:{'sha256':digest(p),'bytes':p.stat().st_size} for p in out.glob('*.json')},'human_signoff':None,'expert_review':None}
    write(out/'manifest.json',manifest)
    write(WORK/'sync/history/playback-before-live.json',pointer)
    write(WORK/'playback/current.json',{'path':out.relative_to(ROOT).as_posix(),'manifest_sha256':digest(out/'manifest.json')})
    log(f'Activated: {len(frames)} note windows; {len(events)} events; {len(flow["notes"])} tied flow bars')


if __name__=='__main__':build()
