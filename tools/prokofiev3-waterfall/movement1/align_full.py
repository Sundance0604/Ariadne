"""Combine the complete score, recorded piano and orchestral attack evidence.

The 0–180 s reviewed onsets are retained. Later piano attacks are matched
one-to-one to a separated-piano transcription; orchestral foreground attacks
are matched in ordered part phrases to pitch-specific stereo evidence.
Unmasked support follows the corrected ensemble clock. Releases are bounded
by repeats and physical key capacity; where key-off cannot be heard they are
explicitly marked as estimates.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import json
from pathlib import Path
import re

import numpy as np
import pretty_midi
from scipy.interpolate import PchipInterpolator
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks

from align_opening import DT, PITCH_MIN, PITCH_MAX
from classify_full_score import classify, role_for
from piano_sustain import PianoSustain, bound_releases
from prepare_preview import (AUDIO, EXPECTED_AUDIO_SHA256, EXPECTED_SCORE_SHA256,
                             HERE, MXL, digest, parse_xml)

END = 580.0
EARLY = 180.0
MIDI_CROPS = (
    ('piano-audio125-transkun.mid', 0, 0, 120),
    ('piano-audio115-185-transkun.mid', 115, 120, 180),
    ('piano-audio175-250-transkun.mid', 175, 180, 247.5),
    ('piano-audio245-320-transkun.mid', 245, 247.5, 317.5),
    ('piano-audio315-390-transkun.mid', 315, 317.5, 387.5),
    ('piano-audio385-460-transkun.mid', 385, 387.5, 457.5),
    ('piano-audio455-530-transkun.mid', 455, 457.5, 527.5),
    ('piano-audio525-580-transkun.mid', 525, 527.5, 580),
)


def piano_transcription() -> dict[int, list[dict]]:
    notes = defaultdict(list)
    for filename, offset, start, stop in MIDI_CROPS:
        data = pretty_midi.PrettyMIDI(str(HERE/filename))
        for instrument in data.instruments:
            for note in instrument.notes:
                attack = note.start + offset
                if start <= attack < stop:
                    notes[note.pitch].append({'start': attack,
                                              'end': note.end+offset,
                                              'file': filename})
    for items in notes.values():
        items.sort(key=lambda x: x['start'])
    return notes


def score_clock() -> PchipInterpolator:
    record = json.loads((HERE/'prokofiev3-full-global-clock.json').read_text())
    if (record['source_audio_sha256'] != EXPECTED_AUDIO_SHA256 or
            record['source_score_sha256'] != EXPECTED_SCORE_SHA256):
        raise ValueError('Global clock belongs to different sources')
    return PchipInterpolator(*zip(*record['beat_time']))


def measured_clock_correction(piano_events: list[dict],
                              piano: dict[int, list[dict]],
                              clock: PchipInterpolator) -> np.ndarray:
    """Small robust per-bar correction where multiple score pitches agree."""
    residual = defaultdict(list)
    for event in piano_events:
        predicted = float(clock(event['start_beat']))
        if predicted < EARLY:
            continue
        times = [note['start'] for note in piano.get(event['midi_pitch'], [])]
        if not times:
            continue
        index = int(np.searchsorted(times, predicted))
        nearby = times[max(0,index-2):index+2]
        delta = min((time-predicted for time in nearby),
                    key=abs, default=10)
        if abs(delta) <= .22:
            residual[event['measure']].append(delta)
    raw = np.zeros(276)
    weight = np.zeros(276)
    for measure, values in residual.items():
        if len(values) < 4:
            continue
        median = float(np.median(values))
        mad = float(np.median(abs(np.asarray(values)-median)))
        if mad > .09:
            continue
        raw[measure-1] = np.clip(median, -.16, .16)
        weight[measure-1] = min(len(values), 12)
    numerator = gaussian_filter1d(raw*weight, .8)
    denominator = gaussian_filter1d(weight, .8)
    correction = np.divide(numerator, denominator,
                           out=np.zeros_like(raw), where=denominator>1.0)
    correction[:43] = 0  # retain the approved first three minutes
    return correction


def corrected_time(beat: float, clock: PchipInterpolator,
                   corrections: np.ndarray) -> float:
    centers = np.arange(276)*4+2
    offset = np.interp(beat, centers, corrections,
                       left=corrections[0], right=corrections[-1])
    return float(clock(beat)+offset)


def match_piano(piano_events: list[dict], piano: dict[int, list[dict]],
                clock: PchipInterpolator, corrections: np.ndarray) -> dict[int, dict]:
    """Ordered sequence match for each pitch; a detection is used only once."""
    by_pitch = defaultdict(list)
    for event in piano_events:
        by_pitch[event['midi_pitch']].append(event)
    result = {}
    for pitch, score_notes in by_pitch.items():
        score_notes.sort(key=lambda x: x['start_beat'])
        detections = piano.get(pitch, [])
        n, m = len(score_notes), len(detections)
        predicted = [corrected_time(e['start_beat'], clock, corrections)
                     for e in score_notes]
        dp = np.zeros((n+1,m+1),np.float32)
        back = np.zeros((n+1,m+1),np.int8)
        for i in range(1,n+1):
            for j in range(1,m+1):
                a = dp[i-1,j]
                b = dp[i,j-1]
                delta = abs(predicted[i-1]-detections[j-1]['start'])
                reward = 3.2-(delta/.15)**2 if delta <= .34 else -1000
                c = dp[i-1,j-1]+reward
                if c >= a and c >= b:
                    dp[i,j] = c; back[i,j] = 2
                elif a >= b:
                    dp[i,j] = a; back[i,j] = 0
                else:
                    dp[i,j] = b; back[i,j] = 1
        i,j=n,m
        while i and j:
            step = back[i,j]
            if step == 2:
                if abs(predicted[i-1]-detections[j-1]['start']) <= .34:
                    result[id(score_notes[i-1])] = detections[j-1]
                i-=1;j-=1
            elif step == 0:i-=1
            else:j-=1
    return result


def supplement_piano_stem_attacks(events: list[dict], matches: dict[int,dict],
                                   stem: PianoSustain,
                                   clock: PchipInterpolator,
                                   corrections: np.ndarray) -> dict[int,dict]:
    """Find a pronounced isolated pitch-energy rise missed by Transkun."""
    used=defaultdict(list)
    for event in events:
        detected=matches.get(id(event))
        if detected:used[event['midi_pitch']].append(detected['start'])
    output={}
    for event in sorted(events,key=lambda e:e['start_beat']):
        if id(event) in matches:continue
        predicted=corrected_time(event['start_beat'],clock,corrections)
        if not EARLY<=predicted<END:continue
        grid=np.arange(max(0,predicted-.12),min(END,predicted+.12),.01)
        if len(grid)<15:continue
        energy=stem.sample(event['midi_pitch'],grid)
        wider=stem.sample(event['midi_pitch'],np.arange(
            max(0,predicted-.35),min(END,predicted+.35),.01))
        peak=max(float(np.max(wider)),1e-8)
        rise=np.r_[np.zeros(5),energy[5:]-energy[:-5]]/peak
        choices=sorted(range(5,len(grid)-3),
                       key=lambda i:(abs(grid[i]-predicted),-rise[i]))
        for i in choices:
            time=float(grid[i])
            if rise[i]<.30 or energy[i]<3e-5 or energy[i]/peak<.30:
                continue
            if any(abs(time-old)<.055 for old in used[event['midi_pitch']]):
                continue
            output[id(event)]={'start':time,'rise':float(rise[i])}
            used[event['midi_pitch']].append(time)
            break
    return output


def supplement_piano_attacks(events: list[dict], matches: dict[int,dict],
                             stem_supplements: dict[int,dict],
                             evidence: 'OrchestraEvidence',
                             clock: PchipInterpolator,
                             corrections: np.ndarray) -> dict[int,dict]:
    """Use a strong, unused pitch attack in the original mix when the stem misses.

    This stays within 130 ms of the score clock and is explicitly labelled as
    mixed-audio evidence, because the source instrument remains uncertain.
    """
    accepted=defaultdict(list)
    for event in events:
        detected=matches.get(id(event))
        if detected:
            accepted[event['midi_pitch']].append(detected['start'])
        elif id(event) in stem_supplements:
            accepted[event['midi_pitch']].append(stem_supplements[id(event)]['start'])
    result={}
    for event in sorted(events,key=lambda e:e['start_beat']):
        if (id(event) in matches or id(event) in stem_supplements or
                not PITCH_MIN<=event['midi_pitch']<=PITCH_MAX):
            continue
        predicted=corrected_time(event['start_beat'],clock,corrections)
        if predicted<EARLY or predicted>=END:
            continue
        grid=np.arange(max(0,predicted-.13),min(END,predicted+.13)+DT/2,DT)
        curve=evidence.curve('P14',[event['midi_pitch']],grid)
        peaks,_=find_peaks(curve,prominence=.018,distance=4)
        if not len(peaks):continue
        wider=np.arange(max(0,predicted-.4),min(END,predicted+.4),DT)
        neighborhood=evidence.curve('P14',[event['midi_pitch']],wider)
        strong=max(float(np.percentile(neighborhood,92)),.045)
        options=sorted(peaks,key=lambda k:(abs(grid[k]-predicted),-curve[k]))
        for k in options:
            time=float(grid[k])
            if curve[k]<max(.075,.67*strong):continue
            if any(abs(time-old)<.06 for old in accepted[event['midi_pitch']]):
                continue
            result[id(event)]={'start':time,'strength':float(curve[k]/strong)}
            accepted[event['midi_pitch']].append(time)
            break
    return result


class OrchestraEvidence:
    def __init__(self):
        self.chunks = {}
        manifest = json.loads((HERE/'orchestra-full-features/manifest.json').read_text())
        if (manifest['source_audio_sha256'] != EXPECTED_AUDIO_SHA256 or
                manifest['source_score_sha256'] != EXPECTED_SCORE_SHA256):
            raise ValueError('Orchestra features belong to different sources')
        for start in range(0,580,50):
            stop = min(start+50,580)
            with np.load(HERE/f'orchestra-full-features/features-{start:03}-{stop:03}.npz') as file:
                self.chunks[start] = {name: file[name].astype(np.float32)
                                      for name in file.files}

    def curve(self, part: str, pitches: list[int], times: np.ndarray) -> np.ndarray:
        view = ('first' if part in ('P1','P2','P15') else
                'second' if part=='P16' else 'mid')
        selected = [p for p in pitches if PITCH_MIN<=p<=PITCH_MAX]
        out = np.zeros(len(times),np.float32)
        if not selected:return out
        for start, data in self.chunks.items():
            valid = (times >= start) & (times < min(start+50,580))
            if not np.any(valid):continue
            index = (times[valid]-start)/DT
            curves = data[f'{view}_onset'][np.asarray(selected)-PITCH_MIN]
            sampled = [np.interp(index,np.arange(len(row)),row,left=0,right=0)
                       for row in curves]
            out[valid] = np.max(sampled,axis=0)
        return out


def orchestra_groups(events: list[dict], selected: dict) -> dict[str,list[dict]]:
    by = defaultdict(lambda:defaultdict(list))
    for event in events:
        if event['part_id']=='P14' or event['measure']<=90:
            continue
        if (event['measure'],event['part_id']) in selected:
            by[event['part_id']][event['start_beat']].append(event)
    return {part:[{'part':part,'beat':beat,'events':notes,
                   'pitches':sorted({e['midi_pitch'] for e in notes})}
                  for beat,notes in sorted(beats.items())]
            for part,beats in by.items()}


def promote_audible_orchestra(events: list[dict], selected: dict,
                              role_rows: list[dict],
                              evidence: OrchestraEvidence,
                              clock: PchipInterpolator,
                              corrections: np.ndarray) -> list[dict]:
    """Recover clear written lines missed by score-only dynamic markings.

    Audio evidence can promote a *score part*, never invent a pitch or attack.
    The result remains review-marked, because pitch overlap in a tutti does
    not prove that the particular instrument caused the acoustic peak.
    """
    by_measure=defaultdict(lambda:defaultdict(list))
    for event in events:
        if event['part_id']!='P14' and event['measure']>90:
            by_measure[event['measure']][event['part_id']].append(event)
    promotions=[]
    for row in role_rows[90:]:
        measure=row['measure']
        if row['selected_parts']:
            continue
        piano_attacks=row['piano_attacks']
        candidates=[]
        for score_row in row['candidates']:
            part=score_row['part']
            if score_row['score']<.55 or score_row['attacks']<3:
                continue
            groups=defaultdict(list)
            for event in by_measure[measure][part]:
                groups[event['start_beat']].append(event['midi_pitch'])
            ratios=[]
            for beat,pitches in groups.items():
                time=corrected_time(beat,clock,corrections)
                near=evidence.curve(part,pitches,np.array([time-.02,time,time+.02]))
                wide=evidence.curve(part,pitches,np.arange(time-.27,time+.27,.01))
                normal=max(float(np.percentile(wide,90)),.035)
                ratios.append(float(max(near)/normal))
            if not ratios:continue
            ratio=float(np.median(ratios))
            combined=(score_row['score']+.55*min(ratio,1.5)
                      +.15*min(score_row['attacks']/8,1))
            threshold=1.38 if piano_attacks>=10 else 1.22
            if ratio>=.55 and combined>=threshold:
                candidates.append((combined,part,ratio))
        if not candidates:continue
        combined,part,ratio=max(candidates)
        selected[(measure,part)]={'source':'score part promoted by recorded pitch attacks',
                                  'confidence':'review',
                                  'score':round(combined,3),
                                  'audio_attack_ratio':round(ratio,3)}
        row['selected_parts'].append(part)
        row['acoustic_promotion']={'part':part,'ratio':round(ratio,3),
                                   'combined':round(combined,3)}
        promotions.append({'measure':measure,'part':part,
                           'ratio':round(ratio,3)})
    return promotions


def bridge_role_phrase_gaps(selected: dict, role_rows: list[dict]) -> list[dict]:
    """Keep one masked measure from breaking an otherwise continuous lead."""
    filled=[]
    by_part=defaultdict(list)
    for measure,part in selected:
        if measure>90:by_part[part].append(measure)
    for part,measures in by_part.items():
        for left,right in zip(sorted(measures),sorted(measures)[1:]):
            if right-left not in (2,3):continue
            for measure in range(left+1,right):
                row=role_rows[measure-1]
                candidate=next((x for x in row['candidates'] if x['part']==part),None)
                if not candidate or candidate['attacks']<2 or candidate['score']<.35:
                    continue
                selected[(measure,part)]={
                    'source':'continuous score phrase between acoustically clear bars',
                    'confidence':'review','score':candidate['score']}
                if part not in row['selected_parts']:
                    row['selected_parts'].append(part)
                filled.append({'measure':measure,'part':part})
    return filled


def align_orchestra(groups_by_part: dict[str,list[dict]],
                    evidence: OrchestraEvidence, clock: PchipInterpolator,
                    corrections: np.ndarray) -> dict[tuple[str,float],dict]:
    aligned = {}
    for part, groups in groups_by_part.items():
        # Keep each written phrase independent at long rests and score role
        # handoffs. Within a phrase, Viterbi enforces temporal order.
        phrases=[];current=[];last_measure=None
        for group in groups:
            measure=group['events'][0]['measure']
            if current and (measure-last_measure>1 or
                    corrected_time(group['beat'],clock,corrections)-
                    corrected_time(current[-1]['beat'],clock,corrections)>2.5):
                phrases.append(current);current=[]
            current.append(group);last_measure=measure
        if current:phrases.append(current)
        for phrase in phrases:
            choices=[];utilities=[];strengths=[];predictions=[]
            for group in phrase:
                predicted=corrected_time(group['beat'],clock,corrections)
                predictions.append(predicted)
                grid=np.arange(max(0,predicted-.26),min(END,predicted+.26)+.001,DT)
                curve=evidence.curve(part,group['pitches'],grid)
                peaks,_=find_peaks(curve,distance=3,prominence=.012)
                center=int(np.argmin(abs(grid-predicted)))
                candidate=np.unique(np.r_[peaks,center])
                normal=max(float(np.percentile(curve,92)),.025)
                signal=curve[candidate]/normal
                shift=(grid[candidate]-predicted)/.26
                utility=1.4*np.log1p(2*signal)-.9*shift**2
                utility[candidate==center]+=.08
                choices.append(grid[candidate]);utilities.append(utility)
                strengths.append(signal)
            dp=utilities[0];back=[]
            for k in range(1,len(phrase)):
                expected=max(.03,predictions[k]-predictions[k-1])
                gap=choices[k][:,None]-choices[k-1][None,:]
                allowed=(gap>=max(.025,expected*.30)) & (gap<=expected*2.5+.14)
                transition=-.24*((gap-expected)/max(expected,.13))**2
                lattice=dp[None,:]+transition
                lattice[~allowed]=-1e5
                best=np.argmax(lattice,axis=1)
                dp=utilities[k]+lattice[np.arange(len(best)),best]
                back.append(best)
            indexes=np.empty(len(phrase),int);indexes[-1]=int(np.argmax(dp))
            for k in range(len(phrase)-2,-1,-1):
                indexes[k]=back[k][indexes[k+1]]
            for group,pred,cands,values,index in zip(
                    phrase,predictions,choices,strengths,indexes):
                strength=float(values[index])
                # A masked score note stays at the ensemble clock. A local
                # spectral peak alone does not prove the instrument identity.
                trusted=strength>=.42 and abs(cands[index]-pred)<=.26
                time=float(cands[index]) if trusted else pred
                aligned[(part,group['beat'])]={
                    'time':time,'clock':pred,'strength':strength,
                    'source':'orchestra_pitch_attack' if trusted else 'ensemble_clock'}
    return aligned


def trim_piano_releases(notes: list[dict]) -> dict[str,int]:
    piano=[n for n in notes if n['part_id']=='P14']
    by_key=defaultdict(list)
    for note in piano:by_key[note['midi_pitch']].append(note)
    same_key=0;capacity=0;global_capacity=0
    for key,items in by_key.items():
        items.sort(key=lambda n:n['audio_start'])
        for current,following in zip(items,items[1:]):
            bound=following['audio_start']-.012
            if current['audio_end']>bound and bound>current['audio_start']+.02:
                current['audio_end']=bound
                current['release_source']='same_key_reattack'
                same_key+=1
    # Show physically held keys, not all sympathetic/pedal resonance. Each
    # hand is allowed at most five simultaneously held keys. Crossing voices
    # remain possible at the middle register by choosing the less occupied
    # hand, rather than rigidly cutting at one pitch.
    active=[[],[]]
    for note in sorted(piano,key=lambda n:(n['audio_start'],n['midi_pitch'])):
        now=note['audio_start']
        for hand in active:
            hand[:]=[n for n in hand if n['audio_end']>now+.001]
        pitch=note['midi_pitch']
        which=0 if pitch<57 else 1 if pitch>64 else (0 if len(active[0])<=len(active[1]) else 1)
        hand=active[which]
        if len(hand)>=5:
            for old in sorted(hand,key=lambda n:n['audio_start'])[:len(hand)-4]:
                if old['audio_end']>now-.008 and now>old['audio_start']+.045:
                    old['audio_end']=now-.008
                    old['release_source']='five_key_hand_bound'
                    capacity+=1
            hand[:]=[n for n in hand if n['audio_end']>now+.001]
        hand.append(note)
    for note in piano:
        minimum=.01 if note.get('release_source')=='same_key_reattack' else .05
        note['audio_end']=max(note['audio_start']+minimum,note['audio_end'])
    held=[]
    for note in sorted(piano,key=lambda n:(n['audio_start'],n['midi_pitch'])):
        now=note['audio_start']
        held[:]=[old for old in held if old['audio_end']>now+.001]
        while len(held)>=10:
            old=min(held,key=lambda n:n['audio_start'])
            if now>old['audio_start']+.05:
                old['audio_end']=min(old['audio_end'],now-.005)
                old['release_source']='ten_key_global_bound'
                global_capacity+=1
            held.remove(old)
        held.append(note)
    return {'same_key_trimmed':same_key,'hand_capacity_trimmed':capacity,
            'global_capacity_trimmed':global_capacity}


def main() -> None:
    if digest(AUDIO)!=EXPECTED_AUDIO_SHA256 or digest(MXL)!=EXPECTED_SCORE_SHA256:
        raise ValueError('Source fingerprint changed')
    events=parse_xml(MXL,max_measure=276)
    selected,role_rows=classify(events)
    clock=score_clock()
    piano=piano_transcription()
    piano_events=[e for e in events if e['part_id']=='P14']
    corrections=measured_clock_correction(piano_events,piano,clock)
    matches=match_piano(piano_events,piano,clock,corrections)
    same_key_score=defaultdict(list)
    piano_attack_groups=defaultdict(list)
    for event in piano_events:
        same_key_score[(event['start_beat'],event['midi_pitch'])].append(event)
        piano_attack_groups[event['start_beat']].append(event)
    preferred_score_event={
        key:id(max(group,key=lambda event:(id(event) in matches,
                                          event['end_beat']-event['start_beat'])))
        for key,group in same_key_score.items()}
    evidence=OrchestraEvidence()
    stem=PianoSustain()
    stem_supplements=supplement_piano_stem_attacks(
        piano_events,matches,stem,clock,corrections)
    supplements=supplement_piano_attacks(piano_events,matches,stem_supplements,
                                         evidence,clock,corrections)
    promotions=promote_audible_orchestra(events,selected,role_rows,evidence,
                                         clock,corrections)
    bridged=bridge_role_phrase_gaps(selected,role_rows)
    orchestral=align_orchestra(orchestra_groups(events,selected),evidence,
                              clock,corrections)
    at_attack=defaultdict(list)
    for event in events:
        at_attack[event['start_beat']].append(event)
    approved=json.loads((HERE/'prokofiev3-opening180.timeline.json').read_text())
    notes=[deepcopy(n) for n in approved['notes'] if n['audio_start']<EARLY]
    for note in notes:
        match=re.search(r'-m(\d+)-',note.get('score_id',''))
        if match:
            note['measure']=int(match.group(1))
        note['musical_role']=('piano' if note['part_id']=='P14' else
                              'orchestra_melody' if note['visual_role']=='lead' else
                              'orchestra_support')
        note['onset_source']='reviewed_opening180'
        note['release_source']='reviewed_score_bounded'
    review=[];excluded=[];piano_matched=0;piano_stem=0;piano_supplemented=0;orchestra_matched=0
    for index,event in enumerate(events):
        predicted=corrected_time(event['start_beat'],clock,corrections)
        if predicted<EARLY or predicted>=END:
            continue
        role=role_for(event,selected,at_attack[event['start_beat']])
        if event['part_id']=='P14':
            if id(event)!=preferred_score_event[(event['start_beat'],event['midi_pitch'])]:
                excluded.append({'measure':event['measure'],'pitch':event['midi_pitch'],
                                 'reason':'duplicate written key at same attack'})
                continue
            detected=matches.get(id(event))
            if len({e['midi_pitch'] for e in piano_attack_groups[event['start_beat']]})>10 and not detected:
                excluded.append({'measure':event['measure'],'pitch':event['midi_pitch'],
                                 'reason':'physically impossible XML chord; no separated piano attack'})
                continue
            if detected:
                start=detected['start'];piano_matched+=1
                onset_source='separated_piano_transkun_score_match'
            elif id(event) in stem_supplements:
                start=stem_supplements[id(event)]['start'];piano_stem+=1
                onset_source='separated_piano_spectral_attack_review'
            elif id(event) in supplements:
                start=supplements[id(event)]['start'];piano_supplemented+=1
                onset_source='mixed_pitch_attack_needs_review'
            else:
                start=predicted;onset_source='score_clock_unmatched'
            end=corrected_time(event['end_beat'],clock,corrections)
            release_source='warped_score_estimate'
            # The model produces many implausible 30–80 ms offsets. Only a
            # substantial detected duration may shorten a written sustain;
            # the end still cannot be called a measured key release.
            if detected and detected['end']-detected['start']>=.18:
                end=min(end,max(start+.09,detected['end']))
                release_source='transkun_long_offset_bound'
        else:
            matched=orchestral.get((event['part_id'],event['start_beat']))
            if matched:
                start=matched['time'];onset_source=matched['source']
                orchestra_matched+=onset_source=='orchestra_pitch_attack'
            else:
                start=predicted;onset_source='ensemble_clock'
            end=corrected_time(event['end_beat'],clock,corrections)
            release_source='warped_score_estimate'
        end=min(END,max(start+.06,end))
        note={'score_id':f'p3-full-m{event["measure"]}-{event["part_id"]}-{index}',
              'part_id':event['part_id'],'part_name':event['part_name'],
              'family':event['family'],'measure':event['measure'],
              'score_start_beat':event['start_beat'],
              'score_end_beat':event['end_beat'],
              'midi_pitch':event['midi_pitch'],
              'audio_start':round(float(start),4),
              'audio_end':round(float(end),4),
              'musical_role':role,
              'visual_role':'lead' if role!='orchestra_support' else 'support',
              'onset_source':onset_source,
              'release_source':release_source}
        if event['part_id']!='P14' and matched:
            note['attack_strength_ratio']=round(matched['strength'],3)
            note['clock_shift_seconds']=round(start-matched['clock'],4)
        elif event['part_id']=='P14':
            note['clock_shift_seconds']=round(start-predicted,4)
        if role in ('orchestra_melody','orchestra_chord'):
            note['role_confidence']=selected.get(
                (event['measure'],event['part_id']),{}).get('confidence','review')
        notes.append(note)
        if onset_source=='score_clock_unmatched':
            review.append({'measure':event['measure'],'pitch':event['midi_pitch'],
                           'predicted_seconds':round(predicted,3),
                           'reason':'piano score note without matching separated attack'})
    sustain=bound_releases(notes,stem)
    trim=trim_piano_releases(notes)
    notes.sort(key=lambda n:(n['audio_start'],n['midi_pitch'],n['part_id']))
    data={'format_version':1,'title':'Prokofiev 3/I full-movement alignment',
          'orchestra_pressed_keys':True,
          'sources':{'score':{'path':str(MXL),'sha256':EXPECTED_SCORE_SHA256},
                     'audio':{'path':str(AUDIO),'sha256':EXPECTED_AUDIO_SHA256}},
          'alignment_interval_seconds':[0,END],
          'notes':notes}
    output=HERE/'prokofiev3-full-alignment.json'
    output.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n')
    role_output=HERE/'prokofiev3-full-role-review.json'
    role_output.write_text(json.dumps(role_rows,ensure_ascii=False,indent=2)+'\n')
    qa={'score_notes':len(events),'output_notes':len(notes),
        'piano_score_notes':len(piano_events),
        'piano_transcribed_attacks':sum(map(len,piano.values())),
        'piano_matched_after_180':piano_matched,
        'piano_stem_spectral_after_180':piano_stem,
        'piano_mixed_attack_after_180':piano_supplemented,
        'piano_unmatched_after_180':len(review),
        'score_piano_events_excluded':len(excluded),
        'orchestra_pitch_attacks_after_180':orchestra_matched,
        'orchestra_role_measures':sum(bool(x['selected_parts']) for x in role_rows),
        'orchestra_acoustic_promotions':promotions,
        'orchestra_phrase_bridges':bridged,
        'release_trims':trim,
        'separated_piano_sustain_bounds':sustain,
        'clock_correction_max_ms':round(float(np.max(abs(corrections)))*1000,1),
        'review_piano_notes':review,'excluded_score_events':excluded}
    (HERE/'prokofiev3-full-alignment.qa.json').write_text(
        json.dumps(qa,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in qa.items() if k not in (
        'review_piano_notes','excluded_score_events','orchestra_acoustic_promotions',
        'orchestra_phrase_bridges')},
                     ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
