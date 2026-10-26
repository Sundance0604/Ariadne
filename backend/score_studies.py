"""Small, editable score transcriptions and musical arguments, independent of MIDI.

This path does not read the automatic alignment or require a complete transcription.
Agent score checks and a human's signed review are recorded separately.
"""
from fractions import Fraction
from pathlib import Path
import re
from .structure_analysis.common import read,digest,bounded_path


def pitch_number(name):
    match=re.fullmatch(r'([A-G])(bb|##|b|#)?(-?\d+)',name or '')
    if not match:raise ValueError('Invalid score-study pitch: '+str(name))
    letter,alter,octave=match.groups()
    return 12*(int(octave)+1)+{'C':0,'D':2,'E':4,'F':5,'G':7,'A':9,'B':11}[letter]+{'bb':-2,'b':-1,None:0,'#':1,'##':2}[alter]


def validate_document(document,root,mapping=None):
    if document.get('schema_version')!='1.0.0':raise ValueError('Unknown score-study version')
    if mapping and document['edition']['pdf_sha256']!=mapping['pdf_sha256']:raise ValueError('Score-study navigation edition mismatch')
    sources={s['id']:s for s in document['score_sources']}
    for source in sources.values():
        if digest(bounded_path(root,source['path']))!=source['sha256']:raise ValueError('Score-study source fingerprint mismatch')
    windows={w['id']:w for w in document['windows']}
    if len(windows)!=len(document['windows']):raise ValueError('Duplicate score window')
    for w in windows.values():
        review=w['review']
        if review.get('human_status')!='pending':raise ValueError('Human signature must be handled in a separate reviewed revision')
        if review.get('method')!='direct_score_transcription' or not review.get('agent'):raise ValueError('Missing transcription provenance')
        for region in w['evidence_regions']:
            if region['source_id'] not in sources or not 1<=region['page']<=sources[region['source_id']]['page_count']:raise ValueError('Unknown score region')
            if len(region['rect_pt'])!=4 or min(region['rect_pt'])<0 or min(region['rect_pt'][2:])<=0:raise ValueError('Invalid source crop')
        if w.get('evidence_image'):
            image=bounded_path(root,w['evidence_image']['path'])
            if image.suffix.lower()!='.png' or digest(image)!=w['evidence_image']['sha256']:raise ValueError('Score-study evidence image mismatch')
        seen=set()
        for voice in w['voices']:
            if voice['id'] in seen:raise ValueError('Duplicate score voice')
            seen.add(voice['id'])
            values=voice['notes'] if w['mode']=='metric' else voice['samples']
            for n in values:
                if n.get('written') is not None:
                    if pitch_number(n['concert'])-pitch_number(n['written'])!=voice['transpose_semitones']:raise ValueError('Written/concert transposition disagreement')
                elif n.get('concert') is not None:raise ValueError('Rest with concert pitch')
            if w['mode']=='metric':
                previous=Fraction(0)
                for n in voice['notes']:
                    start,duration=Fraction(n['onset_q']),Fraction(n['duration_q'])
                    if start!=previous or duration<=0:raise ValueError('Score voice has a gap, overlap or invalid duration')
                    if n.get('tie_segments') and sum(map(Fraction,n['tie_segments']))!=duration:raise ValueError('Invalid tied duration')
                    previous=start+duration
                if previous!=Fraction(w['duration_q']):raise ValueError('Score voice does not fill the checked window')
            elif len(voice['samples'])!=len(w['attacks']):raise ValueError('Missing attack sample')
    units={u['id']:u for u in document['form']['units']}
    for u in units.values():
        seen=set();p=u
        while p.get('parent_id'):
            if p['id'] in seen or p['parent_id'] not in units:raise ValueError('Invalid formal hierarchy')
            seen.add(p['id']);p=units[p['parent_id']]
        if not set(u.get('material_ids',[]))<={m['id'] for m in document['form']['materials']}:raise ValueError('Unknown thematic material')
    ids=set()
    for event in document['events']:
        if event['id'] in ids or event['dimension'] not in {'harmony','counterpoint','form','orchestration'}:raise ValueError('Invalid study event')
        ids.add(event['id'])
        if not set(event.get('window_ids',[]))<=windows.keys():raise ValueError('Unknown symbolic window')
        if not set(event.get('unit_ids',[]))<=units.keys():raise ValueError('Unknown formal unit')
        if not event['observations'] or not event['reasoning']:raise ValueError('A musical claim needs observations and reasoning')
    return document


def sounding(voice,time):
    return next((n for n in voice['notes'] if Fraction(n['onset_q'])<=time<Fraction(n['onset_q'])+Fraction(n['duration_q'])),None)


def derive(window):
    """Numbers come only from the separately entered score window."""
    if window['mode']=='metric':
        points=sorted({Fraction(n['onset_q']) for v in window['voices'] for n in v['notes']})
        verticals=[]
        for time in points:
            active=[(v['id'],sounding(v,time)) for v in window['voices']]
            active=[(id,n) for id,n in active if n and n['concert'] is not None]
            pitches=[pitch_number(n['concert']) for _,n in active]
            verticals.append({'onset_q':str(time),'pitch_classes':sorted({p%12 for p in pitches}),
                'bass':min(pitches) if pitches else None,'voice_pitches':{id:n['concert'] for id,n in active}})
        pairs=[]
        for pair in window.get('compare_voices',[]):
            a,b=[next(v for v in window['voices'] if v['id']==id) for id in pair]
            samples=[]
            for time in points:
                na,nb=sounding(a,time),sounding(b,time)
                if na and nb and na['concert'] and nb['concert']:
                    samples.append({'onset_q':str(time),'a':na['concert'],'b':nb['concert'],
                        'semitones':pitch_number(na['concert'])-pitch_number(nb['concert'])})
            pairs.append({'voices':pair,'samples':samples})
        return {'verticals':verticals,'voice_pairs':pairs,'clock':'notated_quarter_units_not_recording_seconds'}
    attacks=[]
    for i,label in enumerate(window['attacks']):
        pitches=[pitch_number(v['samples'][i]['concert']) for v in window['voices']]
        attacks.append({'label':label,'pitch_classes':sorted({p%12 for p in pitches}),'bass':min(pitches)})
    motion=[{'voice':v['id'],'from':v['samples'][0]['concert'],'to':v['samples'][1]['concert'],
        'semitones':pitch_number(v['samples'][1]['concert'])-pitch_number(v['samples'][0]['concert'])} for v in window['voices']]
    return {'attacks':attacks,'motion':motion,'scope':window['scope']}


def study_markdown(document,event):
    lines=['**谱面观察**',*['- '+s for s in event['observations']], '', '**理论推导**',*['- '+s for s in event['reasoning']]]
    for w in document['windows']:
        if w['id'] not in event.get('window_ids',[]):continue
        lines+=['',f'### 符号底稿：{w["title"]}',w['scope'],
            '逐谱录入与图像核对：代理；人工签核：待完成。没有把代理读谱标为人类审核。']
        if w.get('evidence_image'):lines+=['',f'![原谱对照，人工签核待完成](/api/score-study-image?window_id={w["id"]}&track={document["track_id"]})','']
        lines+=['| 声部 | 记谱音 → 实音 | 起点／时值（四分音符单位） |','|---|---|---|']
        for v in w['voices']:
            values=v['notes'] if w['mode']=='metric' else v['samples']
            for i,n in enumerate(values):
                pitches='休止' if n['written'] is None else n['written']+' → '+n['concert']
                timing=f'{n["onset_q"]}／{n["duration_q"]}' if w['mode']=='metric' else w['attacks'][i]+'（仅攻击切片）'
                lines.append(f'| {v["label"]} | {pitches} | {timing} |')
        d=derive(w)
        if d.get('voice_pairs'):
            lines+=['','**音程见证（半音数，保留复音程）**']
            for pair in d['voice_pairs']:
                lines.append('- '+' ↔ '.join(pair['voices'])+'：'+'；'.join(s['onset_q']+'：'+s['a']+'/'+s['b']+'='+str(s['semitones']) for s in pair['samples']))
        if d.get('motion'):
            lines+=['','**相邻攻击的声部进行**',*['- '+m['voice']+'：'+m['from']+' → '+m['to']+'，'+str(m['semitones'])+'半音' for m in d['motion']]]
    if event.get('unit_ids'):
        lines+=['','**结构层级**']
        for u in document['form']['units']:
            if u['id'] in event['unit_ids']:lines.append('- '+u['level']+' · '+u['title']+'：'+u['argument'])
    lines+=['','**边界与未决项**',*['- '+s for s in event['limits']]]
    return '\n'.join(lines)


def load_studies(root,directory,mapping=None):
    pointer=Path(directory)/'analysis/score-studies/current.json'
    if not pointer.exists():return None
    binding=read(pointer);path=bounded_path(root,binding['path'])
    if not path.is_relative_to(Path(directory).resolve()/'analysis/score-studies'):raise ValueError('Score study outside work')
    if digest(path)!=binding['sha256']:raise ValueError('Score-study record fingerprint mismatch')
    document=validate_document(read(path),root,mapping);events=[]
    for e in document['events']:
        events.append({'id':e['id'],'dimension':e['dimension'],'claim_level':'theoretical_analysis',
            'short_label':e['title'],'detail_markdown':study_markdown(document,e),'analysis_origin':'score_study',
            'score_spans':[{'precision':'page_range','pdf_page_start':e['pages'][0],'pdf_page_end':e['pages'][1],'region_ids':[]}],
            'sources':[{'source_id':id,'locator':e['source_locator'],'claim_attribution':'score'} for id in e['source_ids']],
            'verification':{'score':'agent_score_checked','literature':'not_applicable','location':'page_range','timing':'candidate_alignment'},
            'related_essay_ids':[],'analysis_framework':e['framework'],'related_window_ids':e.get('window_ids',[])})
    return {'document':document,'events':events,'path':binding['path'],
        'derived_windows':{w['id']:derive(w) for w in document['windows']}}
