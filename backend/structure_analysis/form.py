"""Multi-signal candidate boundaries and a hierarchy without a sonata template."""
from .common import overlap, evidence_ids


def analyze(notes, excerpts, ppq, meters, orchestration, harmony, motifs, tempo_events=None):
    boundaries=[];units=[{'id':'work','level':'work','parent_id':None,'function':'unassigned'},
        {'id':'movement-1','level':'movement','parent_id':'work','function':'continuous_movement','basis':'supplied_work_and_single_movement_scope'}]
    for excerpt in excerpts:
        lo,hi=excerpt['start_tick'],excerpt['end_tick'];signals={}
        def add(tick,kind,ref):
            if lo<tick<hi:signals.setdefault(tick,{}).setdefault(kind,[]).append(ref)
        for edge in orchestration['activity_edges']:
            if edge['excerpt']==excerpt['id'] and len(edge['entered'])+len(edge['exited'])>=3:
                add(edge['tick'],'instrumentation',edge['id'])
                if len(edge['entered'])>=3 or len(edge['exited'])>=3:add(edge['tick'],'texture_density',edge['id'])
        for tick,num,den in meters:
            if lo<tick<hi:add(tick,'meter',f'meter-{tick}-{num}-{den}')
        for tempo in tempo_events or []:
            if lo<tempo['tick']<hi:add(tempo['tick'],'reference_tempo',f'tempo-{tempo["tick"]}')
        for motif in motifs['motifs']:
            for occurrence in motif['occurrences']:
                if occurrence['excerpt']==excerpt['id']:add(occurrence['start_tick'],'literal_motif',motif['id'])
        windows=[w for w in harmony['windows'] if w['excerpt']==excerpt['id']]
        for a,b in zip(windows,windows[1:]):
            ca,cb=a['sonority']['candidates'],b['sonority']['candidates']
            if len(ca)==len(cb)==1 and ca[0]['quality']=='dominant7' and cb[0]['quality'] in {'major','minor'} and (ca[0]['root_pc']-cb[0]['root_pc'])%12==7:
                add(b['start_tick'],'dominant_tonic_sonority',a['id']+'→'+b['id'])
        accepted=[]
        for tick,evidence in sorted(signals.items()):
            # Texture density and entry/exit are one feature family; do not count twice.
            independent=set(evidence)-{'texture_density'}
            status='multi_signal_candidate' if len(independent)>=2 else 'single_signal_insufficient'
            boundaries.append({'id':f'boundary-{excerpt["id"]}-{tick}','excerpt':excerpt['id'],'tick':tick,
                'signals':evidence,'independent_signal_families':sorted(independent),'status':status,
                'function':'undetermined_not_automatic_section_or_recapitulation',
                'rationale':'A meter or instrumentation change alone cannot prove formal division.',
                'alternatives':['Local articulation inside a continuing phrase or thematic statement.']})
            if status=='multi_signal_candidate' and (not accepted or tick-accepted[-1]>=ppq*2):accepted.append(tick)
        cuts=[lo]+accepted+[hi]
        for index,(start,end) in enumerate(zip(cuts,cuts[1:])):
            section_id=f'section-{excerpt["id"]}-{index}'
            source=[n for n in notes if overlap(n,start,end)]
            units.append({'id':section_id,'level':'section','parent_id':'movement-1','excerpt':excerpt['id'],
                'start_tick':start,'end_tick':end,'note_ids':evidence_ids(source),
                'function':'candidate_structural_span','status':'hypothesis',
                'clipped_at_excerpt_start':start==lo,'clipped_at_excerpt_end':end==hi,
                'boundary_ids':[b['id'] for b in boundaries if b['excerpt']==excerpt['id'] and b['tick'] in {start,end}],
                'warning':'Excerpt edges are processing limits, not claimed formal boundaries.'})
            occurrences=[(m,o) for m in motifs['motifs'] for o in m['occurrences'] if o['excerpt']==excerpt['id'] and start<=o['start_tick']<o['end_tick']<=end]
            for j,(motif,occurrence) in enumerate(occurrences):
                phrase_id=f'phrase-{section_id}-{j}'
                units.append({'id':phrase_id,'level':'phrase','parent_id':section_id,'excerpt':excerpt['id'],
                    'start_tick':occurrence['start_tick'],'end_tick':occurrence['end_tick'],
                    'function':'motif_bearing_phrase_fragment','status':'fragment_not_certified_complete_phrase',
                    'note_ids':occurrence['note_ids'],'cadence':'undetermined'})
                units.append({'id':f'occurrence-{phrase_id}','level':'motif','parent_id':phrase_id,'excerpt':excerpt['id'],
                    'start_tick':occurrence['start_tick'],'end_tick':occurrence['end_tick'],
                    'motif_id':motif['id'],'note_ids':occurrence['note_ids'],'theme_identity':'unassigned'})
    return {'boundaries':boundaries,'units':units,'formal_model':'unassigned_pending_independent_evidence',
        'limitations':['No automatic sonata/ternary label.','Hierarchy supports fragments and overlapping motif occurrences; it does not certify complete periods.','Cadential sonority is not automatically a phrase-ending cadence.']}
