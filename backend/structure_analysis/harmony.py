"""Vertical slices, arpeggiated collections and conservative harmonic hypotheses."""
from collections import defaultdict
from .common import overlap, evidence_ids, PITCH_NAMES

TEMPLATES={'major':(0,4,7),'minor':(0,3,7),'diminished':(0,3,6),'augmented':(0,4,8),
    'dominant7':(0,4,7,10),'major7':(0,4,7,11),'minor7':(0,3,7,10),
    'half_diminished7':(0,3,6,10),'diminished7':(0,3,6,9)}


def sonority(pitches):
    pcs=sorted({p%12 for p in pitches})
    if not pcs:return {'pitch_classes':[],'bass':None,'candidates':[],'structures':[]}
    bass=min(pitches);candidates=[]
    for root in range(12):
        for quality,intervals in TEMPLATES.items():
            tones=[(root+i)%12 for i in intervals]
            missing=set(tones)-set(pcs)
            if set(pcs)==set(tones) or quality=='dominant7' and set(pcs)<=set(tones) and missing=={(root+7)%12}:
                candidates.append({'root_pc':root,'quality':quality,'chord_tones':tones,
                    'omitted_pcs':sorted(missing),'inversion_index':tones.index(bass%12),
                    'status':'set_identity_candidate_not_function_proof'})
    structures=[]
    for root in pcs:
        if 3<=len(pcs)<=5 and {(root+5*i)%12 for i in range(len(pcs))}==set(pcs):structures.append('stacked_fourths')
        if len(pcs)==5 and {(root+i)%12 for i in (0,2,4,7,9)}==set(pcs):structures.append('anhemitonic_pentatonic')
    if not structures and not candidates:structures=['dyad' if len(pcs)==2 else 'single_pitch' if len(pcs)==1 else 'unclassified_or_layered']
    return {'pitch_classes':pcs,'bass':bass,'candidates':candidates,'structures':sorted(set(structures))}


def roman_candidates(chord):
    # Written two-sharp signature alone permits both D major and B minor.
    # These are explicit competing contexts, not automatically established keys.
    output=[]
    for tonic,scale,label in [(2,(0,2,4,5,7,9,11),'D major'),(11,(0,2,3,5,7,8,10),'B natural minor')]:
        degree=(chord['root_pc']-tonic)%12
        if degree not in scale:continue
        numeral=('I','II','III','IV','V','VI','VII')[scale.index(degree)]
        if chord['quality'] in {'minor','minor7','diminished','diminished7','half_diminished7'}:numeral=numeral.lower()
        if 'diminished' in chord['quality']:numeral+='ø' if chord['quality']=='half_diminished7' else '°'
        inversion=chord['inversion_index'];seventh='7' in chord['quality']
        numeral+=('7','6/5','4/3','4/2')[inversion] if seventh else ('','6','6/4')[inversion]
        output.append({'context':label,'roman':numeral,'status':'signature_context_hypothesis_requires_phrase_validation'})
    return output


def tonal_centers(notes,start,end):
    histogram=[0]*12
    for n in notes:histogram[n['pitch']%12]+=max(0,min(end,n['sounding_end_tick'])-max(start,n['start_tick']))
    candidates=[]
    for tonic in range(12):
        for mode,scale in [('major',(0,2,4,5,7,9,11)),('natural_minor',(0,2,3,5,7,8,10))]:
            members={(tonic+i)%12 for i in scale}
            outside=sum(weight for pc,weight in enumerate(histogram) if pc not in members)
            candidates.append({'tonic_pc':tonic,'mode':mode,'out_of_scale_note_ticks':outside,
                'tonic_note_ticks':histogram[tonic],'status':'diatonic_duration_fit_not_tonic_or_modulation_proof'})
    return sorted(candidates,key=lambda c:(c['out_of_scale_note_ticks'],-c['tonic_note_ticks'],c['tonic_pc']))[:3]


def analyze(notes, excerpts, ppq):
    pitched=[n for n in notes if not n['is_drum']];windows=[];reductions=[];leading=[]
    for excerpt in excerpts:
        lo,hi=excerpt['start_tick'],excerpt['end_tick']
        source=[n for n in pitched if overlap(n,lo,hi)]
        ticks=sorted({lo,hi}|{max(lo,n['start_tick']) for n in source}|
            {min(hi,n['sounding_end_tick']) for n in source}|
            {n['key_end_tick'] for n in source if lo<n['key_end_tick']<hi})
        previous=None
        for start,end in zip(ticks,ticks[1:]):
            active=[n for n in source if overlap(n,start,end)]
            if not active:previous=None;continue
            result=sonority([n['pitch'] for n in active]);root=result['candidates'][0] if len(result['candidates'])==1 else None
            for candidate in result['candidates']:candidate['roman_candidates']=roman_candidates(candidate)
            complete=all(n['correspondence']['octave_agrees'] for n in active)
            window={'id':f'h-{excerpt["id"]}-{start:07d}-{end:07d}','excerpt':excerpt['id'],'start_tick':start,'end_tick':end,
                'note_ids':evidence_ids(active),'sonority':result,'basis':'simultaneous_key_or_CC64_sustained_notes',
                'key_held_sonority':sonority([n['pitch'] for n in active if n['key_end_tick']>start]),
                'key_held_note_ids':evidence_ids([n for n in active if n['key_end_tick']>start]),
                'pedal_residue_note_ids':evidence_ids([n for n in active if n['key_end_tick']<=start]),
                'pdf_input_complete':complete,'unlocated_or_octave_disputed_note_ids':[n['id'] for n in active if not n['correspondence']['octave_agrees']],
                'framework':'pitch-class set and actual sounding bass; tonal function requires context',
                'rationale':'Vertical membership comes from note interval overlap; arpeggiated collections are separate.',
                'alternatives':['A recognized sonority is not proof of a tonal function or cadence.']}
            windows.append(window)
            if previous:
                pairs=[]
                for part in {n['part_id'] for n in active}:
                    before=[n for n in previous['active'] if n['part_id']==part]
                    after=[n for n in active if n['part_id']==part]
                    if before and after:
                        a=min(before,key=lambda n:n['pitch']);b=min(after,key=lambda n:abs(n['pitch']-a['pitch']))
                        pairs.append({'part_id':part,'from_note':a['id'],'to_note':b['id'],'semitones':b['pitch']-a['pitch']})
                leading.append({'id':f'vl-{window["id"]}','from':previous['window']['id'],'to':window['id'],
                    'method':'nearest_pitch_in_same_part_candidate_not_notated_voice_identity','pairs':pairs})
            previous={'window':window,'active':active}
        # Half-open fixed *reference* quarter windows, explicitly reductions.
        # Do not use their pitch union as a simultaneous chord.
        for start in range(lo,hi,ppq*3):
            end=min(start+ppq*3,hi);members=[n for n in source if overlap(n,start,end)]
            if not members:continue
            result=sonority([n['pitch'] for n in members]);onsets=sorted({n['start_tick'] for n in members})
            reductions.append({'id':f'hr-{excerpt["id"]}-{start:07d}','excerpt':excerpt['id'],'start_tick':start,'end_tick':end,
                'note_ids':evidence_ids(members),'collection':result,'simultaneous':False,
                'basis':'three_reference_quarters_pitch_union_not_a_PDF_measure',
                'onset_count':len(onsets),'distinct_vertical_sonorities':len({tuple(w['sonority']['pitch_classes']) for w in windows if w['excerpt']==excerpt['id'] and start<=w['start_tick']<end}),
                'tonal_center_candidates':tonal_centers(members,start,end),
                'bass_support_candidates':sorted({n['pitch'] for n in members if n['sounding_end_tick']-n['start_tick']>=ppq})})
    nonchord=[]
    bypart=defaultdict(list)
    for n in pitched:bypart[n['part_id']].append(n)
    for part,values in bypart.items():
        values.sort(key=lambda n:(n['start_tick'],n['pitch']))
        for a,b,c in zip(values,values[1:],values[2:]):
            if not a['start_tick']<b['start_tick']<c['start_tick']:continue
            held=[n for n in pitched if n['part_id']!=part and n['start_tick']<=a['start_tick'] and n['sounding_end_tick']>=c['key_end_tick']]
            base=sonority([n['pitch'] for n in held]);candidates=base['candidates']
            if len(candidates)!=1 or b['pitch']%12 in base['pitch_classes']:continue
            x,y=b['pitch']-a['pitch'],c['pitch']-b['pitch']
            if a['pitch']%12 not in base['pitch_classes'] or c['pitch']%12 not in base['pitch_classes']:continue
            kind='passing' if x*y>0 else 'neighbor' if a['pitch']==c['pitch'] else None
            if kind and 0<abs(x)<=2 and 0<abs(y)<=2:
                nonchord.append({'id':f'nct-{b["id"]}','kind':kind+'_candidate','note_ids':[a['id'],b['id'],c['id']]+evidence_ids(held),
                    'rationale':'Stepwise departure/return over independently held chord; metric accent remains unverified.'})
    return {'windows':windows,'arpeggiated_reductions':reductions,'voice_leading':leading,'nonchord_candidates':nonchord,
            'limitations':['No automatic tonic/modulation certification.','MIDI key-release/CC64 sustain is distinct from PDF pedal interpretation.','Non-chord-tone identification is partial; suspensions requiring unresolved ties remain unclassified.']}
