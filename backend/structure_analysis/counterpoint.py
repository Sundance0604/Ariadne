"""Traceable voice projections; doubling is not automatically counterpoint."""
from collections import defaultdict
from .common import evidence_ids, overlap


def streams(notes):
    grouped=defaultdict(lambda:defaultdict(list))
    for n in notes:
        if not n['is_drum']:grouped[(n['part_id'],n.get('track_index',0))][n['start_tick']].append(n)
    output=[]
    for (part,track),onsets in sorted(grouped.items()):
        groups=[sorted(v,key=lambda n:n['pitch']) for _,v in sorted(onsets.items())]
        # Track identity prevents alternating piano staves or divided strings
        # from being spliced into a fictitious melodic outline.
        prefix=f'{part}:track{track}'
        output.append({'id':prefix+':upper','part_id':part,'notes':[g[-1] for g in groups],
            'identity':'monophonic_MIDI_track_candidate' if all(len(g)==1 for g in groups) else 'highest_note_projection_not_score_voice'})
        if any(len(g)>1 for g in groups):output.append({'id':prefix+':lower','part_id':part,
            'notes':[g[0] for g in groups],'identity':'lowest_note_projection_not_score_voice'})
    return output


def analyze(notes, excerpts, ppq):
    projected=streams(notes);relations=[];compound=[]
    for excerpt in excerpts:
        for start in range(excerpt['start_tick'],excerpt['end_tick'],ppq*3):
            end=min(start+ppq*3,excerpt['end_tick']);active=[]
            for stream in projected:
                selected=[n for n in stream['notes'] if n['start_tick']<end and n['key_end_tick']>start]
                if selected:active.append((stream,selected))
            for i,(a,an) in enumerate(active):
                for b,bn in active[i+1:]:
                    at={n['start_tick']:n for n in an};bt={n['start_tick']:n for n in bn};joint=sorted(at.keys()&bt.keys())
                    sampled=False
                    if len(joint)<2:
                        ticks=sorted({start}|{n['start_tick'] for n in an+bn if start<=n['start_tick']<end})
                        aa={};bb={}
                        for tick in ticks:
                            av=[n for n in an if n['start_tick']<=tick<n['key_end_tick']]
                            bv=[n for n in bn if n['start_tick']<=tick<n['key_end_tick']]
                            if av and bv:
                                aa[tick]=max(av,key=lambda n:n['start_tick']);bb[tick]=max(bv,key=lambda n:n['start_tick'])
                        joint=sorted(aa)
                        if len(joint)<2:continue
                        comparison_a,comparison_b=aa,bb;sampled=True
                    else:comparison_a,comparison_b=at,bt
                    same_part=a['part_id']==b['part_id']
                    if same_part and all(comparison_a[t]['id']==comparison_b[t]['id'] for t in joint):continue
                    intervals=[comparison_b[t]['pitch']-comparison_a[t]['pitch'] for t in joint]
                    aligned=at.keys()==bt.keys()
                    if aligned and not sampled and len(set(intervals))==1:
                        kind='unison_or_octave_doubling' if intervals[0]%12==0 else 'parallel_interval_support'
                    else:kind='rhythmically_differentiated_layers'
                    if same_part:kind='register_projection_relationship'
                    motion=[]
                    for x,y in zip(joint,joint[1:]):
                        da=comparison_a[y]['pitch']-comparison_a[x]['pitch'];db=comparison_b[y]['pitch']-comparison_b[x]['pitch']
                        motion.append({'from_tick':x,'to_tick':y,'a_semitones':da,'b_semitones':db,
                            'type':'oblique' if da==0 or db==0 else 'contrary' if da*db<0 else 'similar'})
                    relations.append({'id':f'cp-{excerpt["id"]}-{start}-{a["id"]}-{b["id"]}',
                        'excerpt':excerpt['id'],'start_tick':start,'end_tick':end,'kind':kind,'stream_ids':[a['id'],b['id']],
                        'note_ids':evidence_ids(an+bn),'simultaneous_intervals_semitones':intervals,
                        'comparison_ticks':joint,'comparison_basis':'held_key_overlap_samples' if sampled else 'joint_attacks',
                        'onset_ticks_a':sorted(at),'onset_ticks_b':sorted(bt),'motions':motion,
                        'voice_identity':[a['identity'],b['identity']],
                        'rationale':'Compare actual onset grids, vertical intervals and successive pitch motion; no fugue/canon claim.',
                        'status':'candidate_requires_score_voice_review'})
            for part in {n['part_id'] for n in notes}:
                selected=[n for n in notes if n['part_id']==part and overlap(n,start,end)]
                slow=[n for n in selected if n['key_end_tick']-n['start_tick']>=ppq/2]
                fast=[n for n in selected if n['key_end_tick']-n['start_tick']<ppq/4]
                if slow and len(fast)>=6 and any(f['start_tick']>s['start_tick'] and f['start_tick']<s['key_end_tick'] for f in fast for s in slow):
                    compound.append({'id':f'compound-{part}-{start}','excerpt':excerpt['id'],'part_id':part,
                        'start_tick':start,'end_tick':end,'note_ids':evidence_ids(slow+fast),
                        'kind':'sustained_line_and_fast_figuration_candidate','long_note_ids':evidence_ids(slow),
                        'fast_note_ids':evidence_ids(fast),'status':'implicit_polyphony_candidate_not_independent_voice_proof'})
    return {'streams':[{**s,'notes':[n['id'] for n in s['notes']]} for s in projected],
            'relations':relations,'compound_melodies':compound,
            'limitations':['Register projections are not recovered notated voices.','Parallel intervals and octave doubling do not establish strict counterpoint.','Imitation witnesses are generated separately by the motif analyzer.']}
