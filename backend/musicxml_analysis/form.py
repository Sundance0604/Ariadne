"""Revisable hierarchy, rhythmic/interval comparisons and cadence witnesses."""
from collections import defaultdict,Counter
from fractions import Fraction as F
import hashlib


def analyze_form(data,harmony,orchestration,study):
    measures=data['measures'];events=data['events'];by_id={e['id']:e for e in events}
    units=[]
    for old in study['form']['units']:
        members=[m for m in measures if old['pages'][0]<=m['page']<=old['pages'][1]]
        units.append({**old,'xml_measure_ids':[m['measure_id'] for m in members],
            'xml_range_basis':'page containment, not a newly adjudicated formal boundary',
            'key_evidence':[k['measure_id'] for k in harmony['key_contexts'] if k['measure_id'] in {m['measure_id'] for m in members}]})
    landmarks=[]
    for d in data['notation']:
        if d['kind']=='direction' and (d.get('rehearsal') or any(
            any(x in word.lower() for x in ['allegro','lento','andante','vivo','cadenza','strepitoso']) for word in d.get('words',[]))):
            landmarks.append({k:d[k] for k in ['id','part_id','measure_id','offset_q','words','rehearsal']})
    # Motif comparisons are explicit interval + duration-ratio fingerprints.
    # Upper registral strand is named as a reduction, never a notated voice.
    by_voice=defaultdict(lambda:defaultdict(list))
    for e in events:
        if e['analysis_eligible'] and 'stop' not in e['tie']:
            by_voice[e['voice_id']][F(e['score_start_q'])].append(e)
    fingerprints=defaultdict(list)
    for voice,onsets in by_voice.items():
        line=[max(ns,key=lambda e:e['concert_pitch']['ps']) for _,ns in sorted(onsets.items())]
        for i in range(len(line)-4):
            ns=line[i:i+5]
            if any(F(a['score_end_q'])!=F(b['score_start_q']) for a,b in zip(ns,ns[1:])):continue
            intervals=tuple(b['concert_pitch']['ps']-a['concert_pitch']['ps'] for a,b in zip(ns,ns[1:]))
            if len(set(intervals))==1:continue  # uniform scales/repetitions are weak thematic evidence
            base=F(ns[0]['duration_q']);rhythm=tuple(str(F(e['duration_q'])/base) for e in ns)
            fingerprints[(intervals,rhythm)].append({'voice_id':voice,'measure_id':ns[0]['measure_id'],
                'event_ids':[e['id'] for e in ns],'start_q':ns[0]['score_start_q'],
                'start_pitch':ns[0]['concert_pitch']['name']})
    motifs=[]
    for (intervals,rhythm),occurrences in fingerprints.items():
        if len(occurrences)<2:continue
        if len({o['measure_id'] for o in occurrences})<2:continue
        motifs.append({'id':'xml-motif-'+hashlib.sha256(str((intervals,rhythm)).encode()).hexdigest()[:12],
            'intervals':list(intervals),'duration_ratios':list(rhythm),'occurrences':occurrences,
            'method':'five-attack upper-registral-strand reduction, exact semitone intervals and duration ratios',
            'status':'material_relationship_candidate_not_theme_identity','frequent_pattern':len(occurrences)>30})
    cadences=[]
    windows=harmony['windows']
    for a,b in zip(windows,windows[1:]):
        ca,cb=a['sonority']['chord'],b['sonority']['chord']
        if not ca or not cb or F(a['end_q'])!=F(b['start_q']):continue
        if (ca['root_pc']-cb['root_pc'])%12==7 and ca['quality'] in {'major triad','dominant seventh chord'}:
            cadences.append({'id':f'xml-cad-{len(cadences)+1:04d}','from_window':a['id'],'to_window':b['id'],
                'measure_id':b['measure_id'],'root_motion':[ca['root'],cb['root']],
                'bass_motion':[ca['bass'],cb['bass']],'inversions':[ca['inversion'],cb['inversion']],
                'event_ids':a['event_ids']+b['event_ids'],
                'status':'dominant_to_tonic_root_relation_candidate_not_certified_cadence',
                'requires':['phrase ending','metrical placement','tonic context','soprano and bass resolution','ornament reduction']})
    boundaries=[];changes={c['to']:c for c in orchestration['changes']}
    for m in measures:
        lm=[x['id'] for x in landmarks if x['measure_id']==m['measure_id']]
        cd=[x['id'] for x in cadences if x['measure_id']==m['measure_id']]
        change=changes.get(m['measure_id'])
        if lm or cd or change and len(change['entered'])+len(change['left'])>=5:
            boundaries.append({'measure_id':m['measure_id'],'landmark_ids':lm,'cadence_candidate_ids':cd,
                'orchestration_change':change,'status':'boundary_evidence_not_automatic_formal_cut'})
    return {'hierarchy':units,'materials':study['form']['materials'],'material_links':study['form']['material_links'],
        'motif_comparisons':motifs,'landmarks':landmarks,'cadence_candidates':cadences,'boundary_evidence':boundaries,
        'status':'full-score_evidence_for_revisable_hierarchy_not_final_form_verdict',
        'limitations':['Form is not inferred solely from tempo words, page boundaries or orchestration changes.',
            'Motif fingerprints are reductive comparison evidence; same theme requires contextual adjudication.',
            'Cadence candidates require phrase and voice-leading checking; no automatic PAC classification.']}
