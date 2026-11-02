"""Choose orchestra foreground parts and distinguish melody from harmony."""
from __future__ import annotations

from collections import defaultdict
import json
from math import log1p
from statistics import median
from zipfile import ZipFile
from xml.etree import ElementTree as ET

import numpy as np

from parse_score import HERE,SOURCE,FIRST_GLOBAL_BAR,PART_FAMILY

DYNAMIC={'ppp':0,'pp':1,'p':2,'mp':3,'mf':4,'f':5,'ff':6,'fff':7,
         'sf':5,'sfz':6,'fp':4}
FAMILY_WEIGHT={'P1':.04,'P2':.11,'P3':.10,'P4':.09,'P5':-.04,
               'P6':.05,'P7':.01,'P8':-.08,'P15':.12,'P16':.02,
               'P17':-.04,'P18':-.11,'P19':-.14}


def written_dynamics():
    with ZipFile(SOURCE) as archive:
        root=ET.fromstring(archive.read('score.xml'))
    out={}
    for part in root.findall('./part'):
        part_id=part.get('id')
        if part_id not in PART_FAMILY:continue
        current=3
        for global_bar,measure in enumerate(part.findall('measure'),1):
            if global_bar<FIRST_GLOBAL_BAR:continue
            local_bar=global_bar-FIRST_GLOBAL_BAR+1
            values=[]
            for direction in measure.findall('direction'):
                group=direction.find('direction-type/dynamics')
                if group is not None:
                    values += [DYNAMIC[x.tag] for x in group if x.tag in DYNAMIC]
            if values:current=max(values)
            out[(local_bar,part_id)]=current
    return out


def acoustic_ratio(evidence,clock,part,notes):
    groups=defaultdict(list)
    for note in notes:groups[note['start_beat']].append(note['midi_pitch'])
    if not groups:return 0.
    chosen=list(groups.items())
    if len(chosen)>8:
        chosen=[chosen[round(i*(len(chosen)-1)/7)] for i in range(8)]
    ratios=[]
    for beat,pitches in chosen:
        center=float(clock(beat))
        grid=np.arange(max(0,center-.25),min(620,center+.25),.02)
        if len(grid)<8:continue
        curve=evidence.sample(part,pitches,grid)
        level=max(float(np.percentile(curve,80)),.035)
        ratios.append(min(1.8,float(np.max(curve))/level)
                 if np.max(curve)>.04 else 0.)
    return float(np.median(ratios)) if ratios else 0.


def classify(events,clock,evidence):
    dynamics=written_dynamics()
    by_measure=defaultdict(lambda:defaultdict(list))
    for event in events:by_measure[event['measure']][event['part_id']].append(event)
    selected={};rows=[];previous=set()
    for measure in range(1,420):
        parts=by_measure[measure]
        piano_attacks=len({round(e['start_beat'],4) for e in parts.get('P14',[])})
        orchestra_led=piano_attacks<=3
        candidates=[]
        for part_id,notes in parts.items():
            if part_id not in FAMILY_WEIGHT:continue
            attacks=len({round(e['start_beat'],4) for e in notes})
            pitch=median(e['midi_pitch'] for e in notes)
            length=median(e['end_beat']-e['start_beat'] for e in notes)
            dynamic=dynamics.get((measure,part_id),3)
            acoustic=acoustic_ratio(evidence,clock,part_id,notes)
            score=(FAMILY_WEIGHT[part_id]+.22*log1p(attacks)
                   +.022*(pitch-60)+.18*(dynamic-3)+.12*min(length,2)
                   +(.22 if part_id in previous else 0)
                   +.25*min(acoustic,1.4))
            candidates.append({'part':part_id,'score':round(score,3),
                               'attacks':attacks,'notes':len(notes),
                               'pitch':round(pitch,1),'dynamic':dynamic,
                               'acoustic':round(acoustic,3)})
        candidates.sort(key=lambda c:c['score'],reverse=True)
        chosen=[]
        if candidates:
            strongest=candidates[0]
            threshold=.55 if orchestra_led else 1.42 if piano_attacks>=10 else 1.12
            if strongest['score']>=threshold and (strongest['acoustic']>=.30 or orchestra_led):
                chosen=[strongest['part']]
                attack_beats={round(e['start_beat'],4) for e in parts[strongest['part']]}
                for cand in candidates[1:]:
                    if len(chosen)>=(3 if orchestra_led else 2):break
                    other={round(e['start_beat'],4) for e in parts[cand['part']]}
                    shared=len(attack_beats&other)/max(1,min(len(attack_beats),len(other)))
                    close=cand['score']>=strongest['score']-(.52 if orchestra_led else .28)
                    chordal=orchestra_led and cand['notes']>=1.6*cand['attacks']
                    if (close and (shared>=.4 or chordal) and cand['acoustic']>=.25):
                        chosen.append(cand['part'])
            # The score opens with a quiet bassoon/cello theme before the
            # piano enters. Its low register falls below the generic salience
            # cutoff, but this is the only pitched foreground line there.
            if measure in (1,2,3) and not chosen:
                chosen=['P5']
            elif measure==4 and not chosen:
                chosen=['P16']
            for part in chosen:
                cand=next(c for c in candidates if c['part']==part)
                selected[(measure,part)]={
                    'source':'written texture/dynamics plus recorded pitch attacks',
                    'confidence':'high' if cand['acoustic']>=.75 else 'review',
                    'score':cand['score'],'acoustic':cand['acoustic']}
        previous=set(chosen)
        rows.append({'measure':measure,'piano_attacks':piano_attacks,
                     'selected_parts':chosen,'candidates':candidates[:5]})
    return selected,rows


def role_for(event,selected,at_attack):
    if event['part_id']=='P14':return 'piano'
    if (event['measure'],event['part_id']) not in selected:return 'orchestra_support'
    foreground=[e for e in at_attack if (e['measure'],e['part_id']) in selected]
    if not foreground:return 'orchestra_support'
    top=max(e['midi_pitch'] for e in foreground)
    return ('orchestra_melody' if (top-event['midi_pitch'])%12==0
            else 'orchestra_chord')


def main():
    from scipy.interpolate import PchipInterpolator
    from audio_evidence import OrchestraEvidence
    score=json.loads((HERE/'score-events.json').read_text())
    clock_data=json.loads((HERE/'score-audio-clock.json').read_text())
    clock=PchipInterpolator(*zip(*clock_data['beat_time']))
    selected,rows=classify(score['notes'],clock,OrchestraEvidence(score))
    (HERE/'role-review.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
    print('foreground bars',sum(bool(r['selected_parts']) for r in rows),
          'multi-part bars',sum(len(r['selected_parts'])>1 for r in rows))


if __name__=='__main__':main()
