"""Structural and evidence checks for the full Prokofiev 3/I alignment."""

from __future__ import annotations

from collections import Counter, defaultdict
import json

import numpy as np

from prepare_preview import (AUDIO, EXPECTED_AUDIO_SHA256, EXPECTED_SCORE_SHA256,
                             HERE, MXL, digest, parse_xml)


def main() -> None:
    if digest(AUDIO)!=EXPECTED_AUDIO_SHA256 or digest(MXL)!=EXPECTED_SCORE_SHA256:
        raise AssertionError('Source files changed')
    data=json.loads((HERE/'prokofiev3-full-alignment.json').read_text())
    assert data['orchestra_pressed_keys'] is True
    qa=json.loads((HERE/'prokofiev3-full-alignment.qa.json').read_text())
    roles=json.loads((HERE/'prokofiev3-full-role-review.json').read_text())
    notes=data['notes']
    assert len(roles)==276
    assert max(x['measure'] for x in parse_xml(MXL,max_measure=276))==276
    assert all(0<=x['audio_start']<x['audio_end']<=580.001 for x in notes)
    assert all(notes[i]['audio_start']<=notes[i+1]['audio_start']
               for i in range(len(notes)-1))
    piano=[x for x in notes if x['part_id']=='P14']
    events=[];by_pitch=defaultdict(list)
    for note in piano:
        events.extend(((note['audio_start'],1),(note['audio_end'],-1)))
        by_pitch[note['midi_pitch']].append(note)
    active=maximum=0
    for _,delta in sorted(events,key=lambda pair:(pair[0],pair[1])):
        active+=delta;maximum=max(maximum,active)
    assert maximum<=10,maximum
    overlaps=[]
    for pitch,items in by_pitch.items():
        items.sort(key=lambda x:x['audio_start'])
        for previous,next_note in zip(items,items[1:]):
            if previous['audio_end']>next_note['audio_start']+.002:
                overlaps.append((pitch,previous['measure'],next_note['measure']))
    assert not overlaps,overlaps[:10]
    approved=json.loads((HERE/'prokofiev3-opening180.timeline.json').read_text())
    old={n['score_id']:(n['audio_start'],n['audio_end'])
         for n in approved['notes'] if n['audio_start']<180}
    retained={n['score_id']:(n['audio_start'],n['audio_end'])
              for n in notes if n['onset_source']=='reviewed_opening180'}
    assert set(old)==set(retained)
    assert all(old[key][0]==retained[key][0] for key in old)
    # Audited opening onsets remain fixed; release bounds can shorten tails.
    assert all(retained[key][1]<=old[key][1]+.0001 for key in old)
    p_after=[x for x in piano if x['audio_start']>=180]
    source_counts=Counter(x['onset_source'] for x in p_after)
    strong=(source_counts['separated_piano_transkun_score_match']+
            source_counts['separated_piano_spectral_attack_review']+
            source_counts['mixed_pitch_attack_needs_review'])
    coverage=strong/max(1,len(p_after))
    assert coverage>=.90,coverage
    by_window=[]
    for start in range(180,580,20):
        section=[x for x in p_after if start<=x['audio_start']<start+20]
        if not section:continue
        uncertain=[x for x in section if x['onset_source']=='score_clock_unmatched']
        by_window.append({'seconds':[start,min(start+20,580)],
                          'piano_notes':len(section),
                          'unmatched':len(uncertain),
                          'unmatched_fraction':round(len(uncertain)/len(section),3)})
    report={'source_hashes_verified':True,'score_measures':276,
            'aligned_notes':len(notes),'piano_notes':len(piano),
            'piano_max_simultaneous_held_keys':maximum,
            'piano_same_key_overlaps':len(overlaps),
            'approved_opening_onsets_retained':len(old),
            'piano_recording_attack_coverage_after_180':round(coverage,4),
            'piano_onset_sources_after_180':source_counts,
            'orchestra_lead_notes':sum(x['musical_role'] in
                  ('orchestra_melody','orchestra_chord') for x in notes),
            'orchestra_lead_measures':qa['orchestra_role_measures'],
            'piano_uncertainty_by_20s':by_window,
            'low_coverage_windows':[x for x in by_window
                                    if x['unmatched_fraction']>.10]}
    target=HERE/'prokofiev3-full-verification.json'
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in
                      ('piano_uncertainty_by_20s','low_coverage_windows')},
                     ensure_ascii=False,indent=2))
    print('low_coverage_windows',report['low_coverage_windows'])


if __name__=='__main__':main()
