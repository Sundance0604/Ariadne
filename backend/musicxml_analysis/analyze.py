"""Evidence-bearing full-score harmony, orchestration and voice relations."""
from collections import Counter, defaultdict
from fractions import Fraction as F
from math import sqrt
import re


def active_pitched(events):
    return [e for e in events if e['analysis_eligible']]


def chord_description(events):
    from music21 import chord
    if not events:return {'pitch_classes':[],'bass':None,'label':'silence','chord':None}
    pitches=[e['concert_pitch'] for e in events]
    bass=min(pitches,key=lambda p:p['ps']);pcs=sorted({p['pc'] for p in pitches})
    # Use spelling, not only an integer pitch-class set. Enharmonic spellings
    # remain inspectable in evidence; music21's root heuristic is not a function.
    c=chord.Chord([p['name'].replace('b','-') for p in pitches])
    exact=c.isMajorTriad() or c.isMinorTriad() or c.isDiminishedTriad() or c.isAugmentedTriad() or c.isSeventh()
    identity=None
    if exact:
        identity={'root':c.root().name.replace('-','b'),'root_pc':c.root().pitchClass,
            'quality':c.commonName,'inversion':c.inversion(),'bass':bass['name'],
            'third':c.third.name.replace('-','b') if c.third else None,
            'fifth':c.fifth.name.replace('-','b') if c.fifth else None,
            'seventh':c.seventh.name.replace('-','b') if c.seventh else None,
            'status':'complete_notated_sonority_identity_not_function_or_cadence_proof'}
    structures=[]
    for pc in pcs:
        if 3<=len(pcs)<=5 and {(pc+5*i)%12 for i in range(len(pcs))}==set(pcs):structures.append('quartal')
        if len(pcs)==5 and {(pc+i)%12 for i in [0,2,4,7,9]}==set(pcs):structures.append('anhemitonic_pentatonic')
    label=(identity['root']+': '+identity['quality']+' / '+bass['name']) if identity else ' + '.join(structures) if structures else f'{len(pcs)}-pitch-class sonority'
    return {'pitch_classes':pcs,'spelled_pitches':sorted({p['name'] for p in pitches}),
        'bass':bass,'chord':identity,'structures':sorted(set(structures)),
        'label':label,'forte_class':c.forteClass,'interval_vector':c.intervalVector}


def key_contexts(data):
    from music21.analysis.discrete import KrumhanslSchmuckler
    from music21 import pitch
    profiles={mode:KrumhanslSchmuckler().getWeights(mode) for mode in ['major','minor']}
    events=active_pitched(data['events']);hist=defaultdict(lambda:[0.0]*12)
    for e in events:hist[e['measure_sequence']][e['concert_pitch']['pc']]+=float(F(e['duration_q']))
    contexts=[]
    def corr(a,b):
        ma=sum(a)/12;mb=sum(b)/12
        denominator=sqrt(sum((x-ma)**2 for x in a)*sum((x-mb)**2 for x in b))
        return sum((x-ma)*(y-mb) for x,y in zip(a,b))/denominator if denominator else 0
    for m in data['measures']:
        seq=m['sequence'];lo=max(1,seq-3);hi=min(len(data['measures']),seq+4)
        weights=[sum(hist[j][pc] for j in range(lo,hi+1)) for pc in range(12)]
        candidates=[]
        for tonic in range(12):
            for mode,profile in profiles.items():
                candidates.append({'tonic_pc':tonic,'tonic':pitch.Pitch(tonic+60).name.replace('-','b'),
                    'mode':mode,'correlation':round(corr(weights,[profile[(pc-tonic)%12] for pc in range(12)]),6)})
        candidates.sort(key=lambda c:-c['correlation'])
        contexts.append({'measure_id':m['measure_id'],'window_measures':[lo,hi],'duration_histogram':weights,
            'candidates':candidates[:3],'margin':round(candidates[0]['correlation']-candidates[1]['correlation'],6),
            'status':'duration_profile_hypotheses_not_established_tonality','doubling_policy':'all notated pitches counted; orchestral doubling biases histogram'})
    return contexts


def harmony(data):
    from music21 import roman,key,chord
    events=active_pitched(data['events']);starts=defaultdict(list);ends=defaultdict(list)
    for e in events:starts[F(e['score_start_q'])].append(e);ends[F(e['score_end_q'])].append(e)
    points=sorted(set(starts)|set(ends)|{F(m['start_q']) for m in data['measures']})
    contexts=key_contexts(data);context_by={x['measure_id']:x for x in contexts}
    windows=[];active={};mi=0;cache={};roman_cache={};measure_members=defaultdict(list)
    for e in events:measure_members[e['measure_id']].append(e)
    for start,end in zip(points,points[1:]):
        for e in ends[start]:active.pop(e['id'],None)
        for e in starts[start]:active[e['id']]=e
        while mi+1<len(data['measures']) and F(data['measures'][mi+1]['start_q'])<=start:mi+=1
        m=data['measures'][mi];members=list(active.values())
        if not members:continue
        key_spelling=tuple(sorted(e['concert_pitch']['name'] for e in members))
        if key_spelling not in cache:cache[key_spelling]=chord_description(members)
        identity=cache[key_spelling];theories=[]
        if identity['chord']:
            for k in context_by[m['measure_id']]['candidates'][:2]:
                ck=(key_spelling,k['tonic'],k['mode'])
                if ck not in roman_cache:
                    c=chord.Chord([e['concert_pitch']['name'].replace('b','-') for e in members])
                    rn=roman.romanNumeralFromChord(c,key.Key(k['tonic'].replace('b','-'),k['mode']))
                    roman_cache[ck]=rn.figure
                theories.append({'context':k['tonic']+' '+k['mode'],'roman':roman_cache[ck],
                    'status':'conditional_on_unverified_local_key','key_correlation':k['correlation']})
        by_part=defaultdict(list)
        for e in members:by_part[e['part_id']].append(e['id'])
        uncertain=[e['id'] for e in members if any('tremolo' in x and ('start' in x or 'stop' in x) for x in e['notations_xml'])]
        windows.append({'id':f'xml-h-{len(windows)+1:06d}','measure_id':m['measure_id'],'start_q':str(start),'end_q':str(end),
            'onset_q':str(start-F(m['start_q'])),'event_ids':sorted(active),'parts':dict(by_part),
            'sonority':identity,'roman_hypotheses':theories,'two_note_tremolo_event_ids':uncertain,
            'basis':'simultaneous notated intervals in concert pitch; half-open boundaries; invisible and grace events excluded',
            'status':'computed_from_source_not_human_harmonic_reduction'})
    # Per-measure arpeggiated collections are explicitly not simultaneous chords.
    reductions=[{'measure_id':m['measure_id'],'event_ids':[e['id'] for e in measure_members[m['measure_id']]],
        'pitch_classes':sorted({e['concert_pitch']['pc'] for e in measure_members[m['measure_id']]}),
        'simultaneous':False,'basis':'whole XML measure pitch union; inspect windows for actual verticals'} for m in data['measures']]
    # Explicit layered reductions: sustained events and upper triads over a bass.
    layers=[]
    by_id={e['id']:e for e in events}
    for w in windows:
        members=[by_id[id] for id in w['event_ids']]
        held=[e for e in members if F(e['duration_q'])>=1]
        bass=w['sonority']['bass']['ps'];upper=[e for e in members if e['concert_pitch']['ps']>bass]
        upper_description=chord_description(upper) if upper else None
        if len(held)>=2 or upper_description and upper_description['chord']:
            layers.append({'window_id':w['id'],'measure_id':w['measure_id'],
                'held_event_ids':[e['id'] for e in held],'held_sonority':chord_description(held),
                'upper_above_lowest_event_ids':[e['id'] for e in upper] if upper_description and upper_description['chord'] else [],
                'upper_sonority':upper_description if upper_description and upper_description['chord'] else None,
                'status':'explicit_duration_or_register_reduction_not_certified_structural_chord'})
    return {'windows':windows,'key_contexts':contexts,'arpeggiated_collections':reductions,'layer_reductions':layers,
        'limitations':['Written note duration is not acoustic sustain. Pedal and tremolo notation remain separate evidence.',
            'Complete vertical identity is not a harmonic function. Roman numerals are conditional key hypotheses.',
            'Ornamental events are not globally stripped by nearest-chord fitting.']}


def orchestration(data):
    events=data['events'];by_measure=defaultdict(list);by_part=defaultdict(list)
    names={p['id']:p['name'] for p in data['parts']}
    for e in events:
        if (e['analysis_eligible'] or e['kind']=='unpitched') and not e['exclusion_reason']:
            by_measure[e['measure_id']].append(e);by_part[e['part_id']].append(e)
    measures=[]
    for m in data['measures']:
        values=by_measure[m['measure_id']];groups=defaultdict(list)
        for e in values:groups[e['part_id']].append(e)
        pitched=[e for e in values if e['concert_pitch']]
        lowest=min((e['concert_pitch']['ps'] for e in pitched),default=None)
        highest=max((e['concert_pitch']['ps'] for e in pitched),default=None)
        rows=[]
        for pid,ns in groups.items():
            ps=[e['concert_pitch'] for e in ns if e['concert_pitch']]
            roles=[]
            if lowest is not None and any(p['ps']==lowest for p in ps):roles.append('lowest-register support')
            if highest is not None and any(p['ps']==highest for p in ps):roles.append('highest-register layer; melody not inferred from height alone')
            if any(F(e['duration_q'])>=F(m['duration_q'])/2 for e in ns):roles.append('sustained layer')
            attacks=[e for e in ns if 'stop' not in e['tie']]
            if len({e['onset_q'] for e in attacks})>=4:roles.append('active figuration or repeated attacks')
            if any(e['kind']=='unpitched' for e in ns):roles.append('unpitched rhythmic or colour layer')
            rows.append({'part_id':pid,'name':names[pid],'event_ids':[e['id'] for e in ns],
                'instrument_refs':sorted({e['instrument_ref'] for e in ns if e.get('instrument_ref')}),
                'attack_count':len(attacks),'range':[min(ps,key=lambda p:p['ps'])['name'],max(ps,key=lambda p:p['ps'])['name']] if ps else None,
                'written_techniques':sorted({e['technique_context'] for e in ns if e['technique_context']}),
                'articulations':sorted({a for e in ns for a in e['articulations']+e['music21_articulations']}),
                'role_observations':roles,'status':'measured_register_duration_activity_not_final_expressive_role'})
        measures.append({'measure_id':m['measure_id'],'parts':rows,'active_part_ids':sorted(groups),
            'resting_part_ids':sorted(set(names)-groups.keys()),'pitched_event_count':len(pitched)})
    changes=[]
    for a,b in zip(measures,measures[1:]):
        entered=set(b['active_part_ids'])-set(a['active_part_ids']);left=set(a['active_part_ids'])-set(b['active_part_ids'])
        if entered or left:changes.append({'from':a['measure_id'],'to':b['measure_id'],'entered':sorted(entered),'left':sorted(left)})
    ranges=[]
    for part in data['parts']:
        values=by_part[part['id']];ps=[e['concert_pitch'] for e in values if e['concert_pitch']]
        ranges.append({'part_id':part['id'],'name':part['name'],'event_count':len(values),
            'range':[min(ps,key=lambda p:p['ps'])['name'],max(ps,key=lambda p:p['ps'])['name']] if ps else None,
            'event_ids_at_extrema':[e['id'] for e in values if e['concert_pitch'] and e['concert_pitch']['ps'] in [min(p['ps'] for p in ps),max(p['ps'] for p in ps)]] if ps else []})
    return {'measures':measures,'changes':changes,'part_ranges':ranges,'limitations':['Part names can denote divisi or shared instruments, not individual players.','Register/attack rules cannot alone certify melody, accompaniment or perceived fusion.']}


def counterpoint(data):
    from music21 import interval,pitch
    from bisect import bisect_right
    measure_starts=[F(m['start_q']) for m in data['measures']]
    events=active_pitched(data['events']);voices=defaultdict(list);warnings=[]
    for e in events:voices[e['voice_id']].append(e)
    lines={};excluded=[]
    for vid,values in voices.items():
        starts=defaultdict(list)
        for e in values:starts[F(e['score_start_q'])].append(e)
        blocked=[e for ns in starts.values() if len(ns)>1 for e in ns]
        values=[ns[0] for ns in starts.values() if len(ns)==1]
        values.sort(key=lambda e:F(e['score_start_q']))
        overlapping={e['id'] for a,b in zip(values,values[1:]) if F(a['score_end_q'])>F(b['score_start_q']) for e in [a,b]}
        excluded.append({'voice_id':vid,'reason':'chordal/divisi or overlapping attacks omitted from continuous line only at those spans',
            'event_ids':[e['id'] for e in blocked]+sorted(overlapping)})
        values=[e for e in values if e['id'] not in overlapping and not any(
            F(e['score_start_q'])<F(b['score_end_q']) and F(e['score_end_q'])>F(b['score_start_q']) for b in blocked)]
        if not values:continue
        # Join ties only within the same source voice, pitch and contiguous time.
        joined=[]
        for e in values:
            if joined and 'stop' in e['tie'] and joined[-1]['pitch']==e['concert_pitch']['name'] and joined[-1]['end']==F(e['score_start_q']):
                joined[-1]['end']=F(e['score_end_q']);joined[-1]['event_ids'].append(e['id'])
            else:joined.append({'start':F(e['score_start_q']),'end':F(e['score_end_q']),
                'pitch':e['concert_pitch']['name'],'ps':e['concert_pitch']['ps'],'event_ids':[e['id']],'measure_id':e['measure_id']})
        lines[vid]=joined
    relations=[];motions=[]
    ids=list(lines)
    for i,va in enumerate(ids):
        for vb in ids[i+1:]:
            if va.split(':')[0]==vb.split(':')[0]:continue
            a=lines[va];b=lines[vb];ia=ib=0;previous=None
            while ia<len(a) and ib<len(b):
                x,y=a[ia],b[ib];start=max(x['start'],y['start']);end=min(x['end'],y['end'])
                if start<end:
                    iv=interval.Interval(pitch.Pitch(x['pitch'].replace('b','-')),pitch.Pitch(y['pitch'].replace('b','-')))
                    r={'id':f'xml-cp-{len(relations)+1:06d}','voices':[va,vb],'start_q':str(start),'end_q':str(end),
                        'event_ids':x['event_ids']+y['event_ids'],'pitches':[x['pitch'],y['pitch']],
                        'interval':iv.name,'directed_interval':iv.directedName,'semitones':y['ps']-x['ps'],
                        'measure_id':data['measures'][bisect_right(measure_starts,start)-1]['measure_id'],
                        'status':'notated_voice_pair_interval_not_species_counterpoint_verdict'}
                    relations.append(r)
                    if previous and F(previous['end_q'])==start:
                        dx=x['ps']-previous['_ps'][0];dy=y['ps']-previous['_ps'][1]
                        motion='oblique' if (dx==0)!=(dy==0) else 'stationary' if dx==dy==0 else 'contrary' if dx*dy<0 else 'parallel' if dx==dy else 'similar'
                        if motion!='stationary':motions.append({'from':previous['id'],'to':r['id'],'measure_id':r['measure_id'],
                            'voices':[va,vb],'motion':motion,'semitones':[dx,dy],
                            'parallel_perfect_candidate':motion=='parallel' and iv.simpleName in {'P1','P5','P8'} and previous['interval'].startswith('P'),
                            'status':'voice_motion_observation_not_automatic_compositional_error'})
                    previous={**r,'_ps':[x['ps'],y['ps']]}
                if x['end']<=y['end']:ia+=1
                else:ib+=1
    # For chordal/divisi voices keep all interval witnesses per simultaneous
    # attack; do not invent top/bottom voice identity across changing chords.
    doublings=[]
    for vid,values in voices.items():
        groups=defaultdict(list)
        for e in values:groups[(e['measure_id'],e['onset_q'])].append(e)
        for (mid,onset),ns in groups.items():
            if len(ns)<2:continue
            ordered=sorted(ns,key=lambda e:e['concert_pitch']['ps'])
            doublings.append({'voice_id':vid,'measure_id':mid,'onset_q':onset,'event_ids':[e['id'] for e in ordered],
                'pitches':[e['concert_pitch']['name'] for e in ordered],
                'adjacent_intervals':[interval.Interval(pitch.Pitch(a['concert_pitch']['name'].replace('b','-')),pitch.Pitch(b['concert_pitch']['name'].replace('b','-'))).name for a,b in zip(ordered,ordered[1:])],
                'status':'same_XML_voice_chord_or_divisi_not_independent_lines'})
    return {'independent_line_ids':list(lines),'excluded_chordal_voices':excluded,'intervals':relations,'motions':motions,'chordal_intervals':doublings,
        'limitations':['Only non-overlapping monophonic XML voices enter continuous voice-pair analysis.',
            'Chord/divisi attacks are preserved separately, without nearest-note fabricated voice identity.',
            'Parallel perfect intervals are observations, not errors in Ravel. No automatic fugue/canon certification.']}
