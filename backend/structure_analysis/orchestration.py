"""Instrument participation, written marks and explicable role hypotheses."""
from collections import defaultdict
from .common import overlap, evidence_ids


def notation_activity_bridges(notes,marks,ppq):
    """Only bridge short key gaps supported by the same native tremolo mark."""
    supports={n['id']:set() for n in notes}
    for mark in marks:
        if mark['kind'] not in {'single_chord_tremolo_candidate','two_note_tremolo_candidate'}:continue
        heads=set(mark.get('head_ids',[])+mark.get('left_head_ids',[])+mark.get('right_head_ids',[]))
        for n in notes:
            if n['part_id']==mark['part_id'] and n.get('midi_measure_candidate') in mark['midi_measure_candidates'] and any(l['id'] in heads for l in n['score_locations']):
                supports[n['id']].add(mark['id'])
    grouped=defaultdict(list)
    for n in notes:grouped[n['part_id']].append(n)
    bridges=[]
    for part,values in grouped.items():
        end=None;ending=[];support=set()
        for n in sorted(values,key=lambda n:(n['start_tick'],n['sounding_end_tick'])):
            if end is not None and 0<n['start_tick']-end<=ppq/16 and support&supports[n['id']]:
                bridges.append({'part_id':part,'start_tick':end,'end_tick':n['start_tick'],
                    'note_ids':ending+[n['id']],'mark_ids':sorted(support&supports[n['id']]),
                    'basis':'native_tremolo_continuity_candidate_not_new_sounding_note'})
            if end is None or n['sounding_end_tick']>end:
                end=n['sounding_end_tick'];ending=[n['id']];support=supports[n['id']]
            elif n['sounding_end_tick']==end:
                ending.append(n['id']);support|=supports[n['id']]
    return bridges


def analyze(notes, pdf, excerpts, ppq, counterpoint):
    edges=[];regions=[];raw_edges=[]
    bridges=notation_activity_bridges(notes,pdf['marks'],ppq)
    for excerpt in excerpts:
        selected=[n for n in notes if overlap(n,excerpt['start_tick'],excerpt['end_tick'])]
        ticks=sorted({excerpt['start_tick'],excerpt['end_tick']}|{n['start_tick'] for n in selected}|{n['sounding_end_tick'] for n in selected})
        previous=set();previous_raw=set()
        for tick in ticks:
            active=[n for n in selected if n['start_tick']<=tick<n['sounding_end_tick']]
            raw_parts={n['part_id'] for n in active}
            if raw_parts!=previous_raw:
                raw_edges.append({'id':f'reference-activity-{excerpt["id"]}-{tick}','excerpt':excerpt['id'],'tick':tick,
                    'entered':sorted(raw_parts-previous_raw),'exited':sorted(previous_raw-raw_parts),
                    'active_parts':sorted(raw_parts),'note_ids':evidence_ids(active),'basis':'literal_reference_key_and_CC64_intervals'})
            previous_raw=raw_parts
            bridged=[b for b in bridges if b['start_tick']<=tick<b['end_tick']]
            parts=raw_parts|{b['part_id'] for b in bridged}
            if parts!=previous:
                edges.append({'id':f'activity-{excerpt["id"]}-{tick}','excerpt':excerpt['id'],'tick':tick,
                    'entered':sorted(parts-previous),'exited':sorted(previous-parts),'active_parts':sorted(parts),
                    'note_ids':sorted(set(evidence_ids(active))|{id for b in bridged for id in b['note_ids']}),
                    'reference_active_parts':sorted(raw_parts),'notation_continuity_parts':sorted(parts-raw_parts),
                    'basis':'reference_intervals_plus_native_tremolo_continuity_candidates',
                    'pdf_duration_status':'not_fully_rhythm_verified'})
            previous=parts
        previous_region=None
        for start in range(excerpt['start_tick'],excerpt['end_tick'],ppq*3):
            end=min(start+ppq*3,excerpt['end_tick']);members=[n for n in selected if overlap(n,start,end)]
            instruments=[];pitched=[n for n in members if not n['is_drum']]
            low=min((n['pitch'] for n in pitched),default=None)
            for part in sorted({n['part_id'] for n in members}):
                values=[n for n in members if n['part_id']==part];pitches=[n['pitch'] for n in values if not n['is_drum']]
                roles=[]
                if pitches and low in pitches:roles.append({'role':'Bass','reason':'Contains the lowest sounding pitch in this reference window.'})
                if any(n['sounding_end_tick']-n['start_tick']>=ppq*2 for n in values):roles.append({'role':'Pedal','reason':'At least one note spans two reference quarters; harmonic pedal function remains a hypothesis.'})
                onsets=sorted({n['start_tick'] for n in values if start<=n['start_tick']<end})
                if len(onsets)>=4:roles.append({'role':'Rhythmic Drive','reason':'At least four distinct attacks in the window.'})
                if len(values)>=6 and len(set(pitches))<=4:roles.append({'role':'Ostinato','reason':'Restricted pitch vocabulary with repeated attacks; pattern review required.'})
                if len(values)>len(onsets)+1:roles.append({'role':'Harmonic Support','reason':'Multiple simultaneous notes in the part.'})
                if part in {'piano','contrabassoon','oboe','english-horn'} and pitches and not any(len([n for n in values if n['start_tick']==t])>1 for t in onsets):
                    roles.append({'role':'Melody','reason':'Monophonic line candidate; register and phrase context require analyst review.'})
                doubling=[r['id'] for r in counterpoint['relations'] if r['start_tick']==start and r['kind']=='unison_or_octave_doubling' and any(i.startswith(part+':') for i in r['stream_ids'])]
                if doubling:roles.append({'role':'Doubling','reason':'Matched onset grid and constant octave/unison interval.','relation_ids':doubling})
                locations=[p for n in values for p in n['score_locations']]
                mark_ids=[m['id'] for m in pdf['marks'] if m['part_id']==part and any(m['page']==p['page'] and m['physical_system_index']==p['physical_system_index'] for p in locations)]
                instruments.append({'part_id':part,'note_ids':evidence_ids(values),'sounding_range_midi':None if not pitches else [min(pitches),max(pitches)],
                    'roles':roles or [{'role':'Undetermined','reason':'No conservative role rule applies.'}],
                    'written_mark_ids':mark_ids,'role_status':'algorithmic_hypotheses_not_score_facts'})
            parts={i['part_id'] for i in instruments};before=set() if previous_region is None else set(previous_region['active_parts'])
            region={'id':f'orch-{excerpt["id"]}-{start}','excerpt':excerpt['id'],'start_tick':start,'end_tick':end,
                'active_parts':sorted(parts),'instruments':instruments,'note_ids':evidence_ids(members),
                'what_changed':{'entered':sorted(parts-before),'exited':sorted(before-parts)},
                'structural_effect':{'layer_count':len(parts),'register_span':0 if not pitched else max(n['pitch'] for n in pitched)-min(n['pitch'] for n in pitched),
                    'interpretation':'Candidate expansion/contraction or transfer of participating layers, not an automatic form boundary.'},
                'framework':'instrument activity + registral texture + role hypotheses',
                'alternatives':['MIDI release gaps are not necessarily perceptual exits. Written dynamics and timbral effect are distinct.']}
            if members:regions.append(region)
            previous_region=region
    return {'activity_edges':edges,'reference_activity_edges':raw_edges,'notation_activity_bridges':bridges,'regions':regions,'written_marks':pdf['marks'],
            'limitations':['Dynamics are native PDF glyph observations, not velocity-derived loudness.','Slur/tremolo/hairpin/technique assignment is partial and retained as candidate marks.','Role rules do not establish perceptual salience or intention.']}
