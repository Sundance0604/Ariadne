"""Replaceable motif interface: literal interval/rhythm witnesses, not theme names."""
from collections import defaultdict
from fractions import Fraction


class MotifAnalyzer:
    version='interval-ioi-exact-v1'

    def analyze(self, streams, notes, excerpts, length=5):
        byid={n['id']:n for n in notes};groups=defaultdict(list)
        for stream in streams:
            sequence=[byid[i] for i in stream['notes']]
            for excerpt in excerpts:
                values=[n for n in sequence if excerpt['start_tick']<=n['start_tick']<excerpt['end_tick']]
                for i in range(len(values)-length+1):
                    subset=values[i:i+length];ticks=[n['start_tick'] for n in subset]
                    differences=[b-a for a,b in zip(ticks,ticks[1:])]
                    intervals=[b['pitch']-a['pitch'] for a,b in zip(subset,subset[1:])]
                    if not differences or min(differences)<=0 or max(differences)>12*min(differences):continue
                    if len({n['pitch'] for n in subset})<3 or len(set(intervals))<2:continue
                    ratios=[str(Fraction(d,differences[0])) for d in differences]
                    signature=(tuple(intervals),tuple(ratios))
                    groups[signature].append({'stream_id':stream['id'],'part_id':stream['part_id'],'excerpt':excerpt['id'],
                        'start_tick':ticks[0],'end_tick':subset[-1]['key_end_tick'],
                        'note_ids':[n['id'] for n in subset],'pitches':[n['pitch'] for n in subset],
                        'onset_ticks':ticks,'ioi_ratios':ratios,'intervals_semitones':intervals})
        motifs=[];imitations=[]
        for signature,occurrences in sorted(groups.items()):
            # Simultaneous upper/lower projections of one chord sequence are
            # doubling evidence, not two temporal appearances of a theme.
            if len({o['start_tick'] for o in occurrences})<2:continue
            id=f'motif-{len(motifs)+1:04d}';witnesses=[]
            first=occurrences[0]
            for occurrence in occurrences[1:]:
                transposition=occurrence['pitches'][0]-first['pitches'][0]
                witness={'prototype':first,'answer':occurrence,'transposition_semitones':transposition,
                    'entrance_delay_ticks':occurrence['start_tick']-first['start_tick'],
                    'rhythm_scale':str(Fraction(occurrence['onset_ticks'][1]-occurrence['onset_ticks'][0],first['onset_ticks'][1]-first['onset_ticks'][0])),
                    'intervals_and_ratios_exact':True}
                witness['temporal_relation']='overlapping_entries' if occurrence['start_tick']<first['end_tick'] else 'nonoverlapping_transfer_or_recall'
                witnesses.append(witness)
                if first['part_id']!=occurrence['part_id'] and witness['entrance_delay_ticks']>0:
                    imitations.append({'id':f'imitation-{id}-{len(imitations):04d}','motif_id':id,**witness,
                        'classification':'delayed_correspondence_candidate','status':'not_certified_strict_imitation',
                        'alternatives':['Repeated accompaniment, registral projection or thematic transfer rather than contrapuntal imitation.']})
            motifs.append({'id':id,'intervals_semitones':list(signature[0]),'ioi_ratios':list(signature[1]),
                'occurrences':occurrences,'witnesses':witnesses,'theme_identity':'unassigned',
                'status':'literal_pattern_candidate_not_theme_equivalence'})
        return {'interface':'MotifAnalyzer.analyze(streams, notes, excerpts)','algorithm':self.version,
                'motifs':motifs,'imitation_candidates':imitations,
                'limitations':['Five-note interval/onset-ratio equality is necessary evidence, not sufficient proof of theme identity.','Augmentation is represented by an explicit rational time scale.']}
