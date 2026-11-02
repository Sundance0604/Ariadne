"""Score-constrained piano and orchestral note alignment for movement III."""
from __future__ import annotations

from collections import defaultdict
import json

import numpy as np
import pretty_midi
from scipy.interpolate import PchipInterpolator
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks

from parse_score import HERE,AUDIO,digest
from extract_piano import CROPS
from audio_evidence import OrchestraEvidence
from classify_roles import classify,role_for

END=620.0


class PianoEvidence:
    def __init__(self,score):
        directory=HERE/'piano-evidence'
        manifest=json.loads((directory/'manifest.json').read_text())
        if manifest['source_audio_sha256']!=score['source_audio_sha256']:
            raise ValueError('Piano evidence belongs to another recording')
        self.interval=manifest['sample_interval_seconds']
        self.regions=[]
        self.detections=defaultdict(list)
        for i,(start,stop) in enumerate(CROPS):
            left=start if i==0 else (CROPS[i-1][1]+start)/2
            right=stop if i==len(CROPS)-1 else (stop+CROPS[i+1][0])/2
            with np.load(directory/f'energy-{start:03}-{stop:03}.npz') as file:
                energy=file['energy'].astype(np.float32)
            self.regions.append((left,right,start,energy))
            midi=pretty_midi.PrettyMIDI(str(directory/f'piano-{start:03}-{stop:03}.mid'))
            for instrument in midi.instruments:
                for note in instrument.notes:
                    onset=note.start+start
                    if left<=onset<right:
                        self.detections[note.pitch].append({
                            'start':onset,'end':note.end+start,
                            'velocity':note.velocity,'crop':[start,stop]})
        for notes in self.detections.values():notes.sort(key=lambda n:n['start'])

    def energy(self,pitch,times):
        times=np.asarray(times,dtype=float)
        output=np.zeros(len(times),np.float32)
        if not 21<=pitch<=108:return output
        for left,right,start,energy in self.regions:
            valid=(times>=left)&(times<right)
            if not np.any(valid):continue
            row=energy[pitch-21]
            output[valid]=np.interp((times[valid]-start)/self.interval,
                                     np.arange(len(row)),row,left=0,right=0)
        return output


def robust_clock_correction(events,piano,clock,bar_starts,bar_lengths):
    residual=defaultdict(list)
    for event in events:
        prediction=float(clock(event['start_beat']))
        times=[n['start'] for n in piano.detections.get(event['midi_pitch'],[])]
        if not times:continue
        index=int(np.searchsorted(times,prediction))
        nearby=times[max(0,index-2):index+2]
        delta=min((time-prediction for time in nearby),key=abs,default=10)
        if abs(delta)<=.42:residual[event['measure']].append(delta)
    raw=np.zeros(len(bar_starts));weight=np.zeros(len(bar_starts))
    for measure,values in residual.items():
        if len(values)<3:continue
        arr=np.asarray(values)
        med=float(np.median(arr));mad=float(np.median(abs(arr-med)))
        if mad>.13:continue
        raw[measure-1]=np.clip(med,-.28,.28)
        weight[measure-1]=min(len(values),14)
    numerator=gaussian_filter1d(raw*weight,1.0)
    denominator=gaussian_filter1d(weight,1.0)
    correction=np.divide(numerator,denominator,
                         out=np.zeros_like(raw),where=denominator>1.0)
    centers=np.asarray(bar_starts)+np.asarray(bar_lengths)/2
    return PchipInterpolator(centers,correction,extrapolate=True),correction


def match_piano(events,piano,predict):
    """Use each separated-piano attack once, respecting score note order."""
    by_pitch=defaultdict(list)
    for event in events:by_pitch[event['midi_pitch']].append(event)
    result={}
    for pitch,score_notes in by_pitch.items():
        score_notes.sort(key=lambda e:e['start_beat'])
        detected=piano.detections.get(pitch,[])
        n,m=len(score_notes),len(detected)
        if not n or not m:continue
        predicted=[predict(e['start_beat']) for e in score_notes]
        dp=np.zeros((n+1,m+1),np.float32)
        back=np.zeros((n+1,m+1),np.int8)
        for i in range(1,n+1):
            for j in range(1,m+1):
                delta=abs(predicted[i-1]-detected[j-1]['start'])
                reward=3.35-(delta/.21)**2 if delta<=.52 else -1000
                diagonal=dp[i-1,j-1]+reward
                if diagonal>=dp[i-1,j] and diagonal>=dp[i,j-1]:
                    dp[i,j]=diagonal;back[i,j]=2
                elif dp[i-1,j]>=dp[i,j-1]:
                    dp[i,j]=dp[i-1,j];back[i,j]=0
                else:dp[i,j]=dp[i,j-1];back[i,j]=1
        i,j=n,m
        while i and j:
            move=back[i,j]
            if move==2:
                if abs(predicted[i-1]-detected[j-1]['start'])<=.52:
                    result[id(score_notes[i-1])]=detected[j-1]
                i-=1;j-=1
            elif move==0:i-=1
            else:j-=1
    return result


def supplement_stem(events,matches,piano,predict):
    used=defaultdict(list)
    for event in events:
        found=matches.get(id(event))
        if found:used[event['midi_pitch']].append(found['start'])
    result={}
    for event in sorted(events,key=lambda e:e['start_beat']):
        if id(event) in matches:continue
        t=predict(event['start_beat'])
        if not 0<=t<END:continue
        grid=np.arange(max(0,t-.20),min(END,t+.20),.01)
        if len(grid)<15:continue
        energy=piano.energy(event['midi_pitch'],grid)
        surround=piano.energy(event['midi_pitch'],np.arange(max(0,t-.45),min(END,t+.45),.01))
        peak=max(float(np.max(surround)),1e-8)
        rise=np.r_[np.zeros(5),energy[5:]-energy[:-5]]/peak
        options=sorted(range(5,len(grid)-3),key=lambda i:(abs(grid[i]-t),-rise[i]))
        for i in options:
            time=float(grid[i])
            if rise[i]<.28 or energy[i]<3e-5 or energy[i]/peak<.28:continue
            if any(abs(time-old)<.055 for old in used[event['midi_pitch']]):continue
            result[id(event)]={'start':time,'rise':float(rise[i])}
            used[event['midi_pitch']].append(time)
            break
    return result


def supplement_mix(events,matches,stem_matches,orchestra,predict):
    used=defaultdict(list)
    for event in events:
        found=matches.get(id(event)) or stem_matches.get(id(event))
        if found:used[event['midi_pitch']].append(found['start'])
    result={}
    for event in sorted(events,key=lambda e:e['start_beat']):
        if id(event) in matches or id(event) in stem_matches:continue
        t=predict(event['start_beat']);p=event['midi_pitch']
        if not orchestra.pitch_min<=p<=orchestra.pitch_max:continue
        grid=np.arange(max(0,t-.18),min(END,t+.18),.01)
        if len(grid)<10:continue
        curve=orchestra.sample('P14',[p],grid)
        peaks,_=find_peaks(curve,prominence=.018,distance=4)
        if not len(peaks):continue
        reference=max(float(np.percentile(curve,90)),.04)
        for i in sorted(peaks,key=lambda i:(abs(grid[i]-t),-curve[i])):
            time=float(grid[i])
            if curve[i]<max(.07,.65*reference):continue
            if any(abs(time-old)<.06 for old in used[p]):continue
            result[id(event)]={'start':time,'strength':float(curve[i]/reference)}
            used[p].append(time)
            break
    return result


def orchestra_groups(events,selected):
    by=defaultdict(lambda:defaultdict(list))
    for event in events:
        if (event['measure'],event['part_id']) in selected:
            by[event['part_id']][event['start_beat']].append(event)
    return {part:[{'part':part,'beat':beat,'events':items,
                   'pitches':sorted({e['midi_pitch'] for e in items})}
                  for beat,items in sorted(groups.items())]
            for part,groups in by.items()}


def match_orchestra(groups_by_part,evidence,predict):
    """Viterbi phrase match with a broad search and smooth local tempo."""
    aligned={}
    for part,groups in groups_by_part.items():
        phrases=[];current=[];prior_measure=None
        for group in groups:
            measure=group['events'][0]['measure']
            if current and (measure-prior_measure>1 or
                    predict(group['beat'])-predict(current[-1]['beat'])>2.8):
                phrases.append(current);current=[]
            current.append(group);prior_measure=measure
        if current:phrases.append(current)
        for phrase in phrases:
            choices=[];utility=[];strengths=[];predictions=[]
            for group in phrase:
                predicted=predict(group['beat']);predictions.append(predicted)
                window=.70 if part in ('P1','P2','P3','P4','P15','P16') else .46
                grid=np.arange(max(0,predicted-window),min(END,predicted+window)+.001,.01)
                curve=evidence.sample(part,group['pitches'],grid)
                peaks,_=find_peaks(curve,distance=4,prominence=.013)
                center=int(np.argmin(abs(grid-predicted)))
                candidate=np.unique(np.r_[peaks,center])
                normal=max(float(np.percentile(curve,90)),.03)
                signal=curve[candidate]/normal
                shift=(grid[candidate]-predicted)/window
                score=1.45*np.log1p(2*signal)-.68*shift**2
                score[candidate==center]+=.04
                choices.append(grid[candidate]);utility.append(score)
                strengths.append(signal)
            dp=utility[0];backs=[]
            for k in range(1,len(phrase)):
                expected=max(.035,predictions[k]-predictions[k-1])
                gaps=choices[k][:,None]-choices[k-1][None,:]
                allowed=(gaps>=max(.023,expected*.22))&(gaps<=expected*2.6+.2)
                transition=-.65*((gaps-expected)/max(expected,.19))**2
                lattice=dp[None,:]+transition
                lattice[~allowed]=-1e6
                best=np.argmax(lattice,axis=1)
                dp=utility[k]+lattice[np.arange(len(best)),best]
                backs.append(best)
            picks=np.empty(len(phrase),int);picks[-1]=int(np.argmax(dp))
            for k in range(len(phrase)-2,-1,-1):picks[k]=backs[k][picks[k+1]]
            for group,pred,candidates,signals,pick in zip(phrase,predictions,choices,strengths,picks):
                strength=float(signals[pick]);chosen=float(candidates[pick])
                trusted=strength>=.48 and abs(chosen-pred)<=.7
                aligned[(part,group['beat'])]={
                    'time':chosen if trusted else pred,
                    'clock':pred,'strength':strength,
                    'source':'orchestra_pitch_attack' if trusted else 'ensemble_clock'}
    return aligned


def bound_piano_energy(notes,piano):
    count=0
    for note in notes:
        if note['part_id']!='P14':continue
        start,end=note['audio_start'],note['audio_end']
        if end-start<.32:continue
        grid=np.arange(start,min(end,END),.02)
        if len(grid)<16:continue
        energy=piano.energy(note['midi_pitch'],grid)
        peak=float(np.max(energy[:min(10,len(energy))]))
        if peak<.000045:continue
        below=energy<.115*peak
        for i in range(10,len(grid)-5):
            if np.all(below[i:i+6]):
                bound=float(grid[i]+.04)
                if bound<end-.08:
                    note['audio_end']=round(max(start+.22,bound),4)
                    note['release_source']='separated_piano_decay_bound'
                    count+=1
                break
    return count


def trim_piano_releases(notes):
    piano=[n for n in notes if n['part_id']=='P14']
    by_key=defaultdict(list)
    for note in piano:by_key[note['midi_pitch']].append(note)
    same=hand_cuts=global_cuts=0
    for items in by_key.values():
        items.sort(key=lambda n:n['audio_start'])
        for first,second in zip(items,items[1:]):
            bound=second['audio_start']-.012
            if first['audio_end']>bound and bound>first['audio_start']+.02:
                first['audio_end']=bound;first['release_source']='same_key_reattack';same+=1
    hands=[[],[]]
    for note in sorted(piano,key=lambda n:(n['audio_start'],n['midi_pitch'])):
        now=note['audio_start']
        for hand in hands:hand[:]=[x for x in hand if x['audio_end']>now+.001]
        pitch=note['midi_pitch']
        chosen=0 if pitch<57 else 1 if pitch>64 else (0 if len(hands[0])<=len(hands[1]) else 1)
        hand=hands[chosen]
        if len(hand)>=5:
            for old in sorted(hand,key=lambda n:n['audio_start'])[:len(hand)-4]:
                if now>old['audio_start']+.045:
                    old['audio_end']=min(old['audio_end'],now-.008)
                    old['release_source']='five_key_hand_bound';hand_cuts+=1
            hand[:]=[x for x in hand if x['audio_end']>now+.001]
        hand.append(note)
    held=[]
    for note in sorted(piano,key=lambda n:(n['audio_start'],n['midi_pitch'])):
        now=note['audio_start'];held[:]=[x for x in held if x['audio_end']>now+.001]
        while len(held)>=10:
            old=min(held,key=lambda n:n['audio_start'])
            if now>old['audio_start']+.05:
                old['audio_end']=min(old['audio_end'],now-.005)
                old['release_source']='ten_key_global_bound';global_cuts+=1
            held.remove(old)
        held.append(note)
    for note in piano:
        minimum=.01 if note['release_source']=='same_key_reattack' else .05
        note['audio_end']=round(max(note['audio_start']+minimum,note['audio_end']),4)
    return {'same_key':same,'hand_capacity':hand_cuts,'global_capacity':global_cuts}


def main():
    score=json.loads((HERE/'score-events.json').read_text())
    if digest(AUDIO)!=score['source_audio_sha256']:raise ValueError('Recording changed')
    record=json.loads((HERE/'score-audio-clock.json').read_text())
    clock=PchipInterpolator(*zip(*record['beat_time']))
    piano=PianoEvidence(score);orchestra=OrchestraEvidence(score)
    events=score['notes'];piano_events=[e for e in events if e['part_id']=='P14']
    correction,values=robust_clock_correction(
        piano_events,piano,clock,score['bar_starts'],score['bar_lengths'])
    def predict(beat):
        return float(clock(beat)+correction(beat))
    matches=match_piano(piano_events,piano,predict)
    stem=supplement_stem(piano_events,matches,piano,predict)
    mixed=supplement_mix(piano_events,matches,stem,orchestra,predict)
    selected,rows=classify(events,clock,orchestra)
    groups=orchestra_groups(events,selected)
    orchestra_matches=match_orchestra(groups,orchestra,predict)
    by_attack=defaultdict(list);by_piano_attack=defaultdict(list)
    for event in events:
        by_attack[event['start_beat']].append(event)
        if event['part_id']=='P14':by_piano_attack[(event['start_beat'],event['midi_pitch'])].append(event)
    preferred={key:id(max(items,key=lambda e:(id(e) in matches,e['end_beat']-e['start_beat'])))
               for key,items in by_piano_attack.items()}
    notes=[];excluded=[];review=[];counts=defaultdict(int)
    for event in events:
        predicted=predict(event['start_beat'])
        if not 0<=predicted<END:continue
        part=event['part_id'];role=role_for(event,selected,by_attack[event['start_beat']])
        if part=='P14':
            if id(event)!=preferred[(event['start_beat'],event['midi_pitch'])]:
                excluded.append([event['score_id'],'duplicate written key']);continue
            if len({e['midi_pitch'] for e in by_attack[event['start_beat']] if e['part_id']=='P14'})>10 and id(event) not in matches:
                excluded.append([event['score_id'],'unconfirmed impossible piano chord']);continue
            detection=matches.get(id(event))
            if detection:
                start=detection['start'];onset_source='separated_piano_transkun';counts['piano_transkun']+=1
            elif id(event) in stem:
                start=stem[id(event)]['start'];onset_source='separated_piano_spectral';counts['piano_stem']+=1
            elif id(event) in mixed:
                start=mixed[id(event)]['start'];onset_source='mixed_pitch_attack_review';counts['piano_mixed']+=1
            else:
                start=predicted;onset_source='score_clock_unmatched';counts['piano_unmatched']+=1
                review.append({'score_id':event['score_id'],'time':round(predicted,3)})
            end=predict(event['end_beat'])
            release='warped_score_estimate'
            if detection and detection['end']-detection['start']>=.18:
                end=min(end,max(start+.09,detection['end']))
                release='transkun_long_offset_bound'
        else:
            match=orchestra_matches.get((part,event['start_beat']))
            if match:
                start=match['time'];onset_source=match['source']
                counts[onset_source]+=1
            else:
                start=predicted;onset_source='ensemble_clock'
            end=predict(event['end_beat']);release='warped_score_estimate'
        end=min(END,max(start+.06,end))
        note={'score_id':event['score_id'],'event_id':event['score_id'],
              'part_id':part,'part_name':event['part_name'],'family':event['family'],
              'measure':event['measure'],'score_start_beat':event['start_beat'],
              'score_end_beat':event['end_beat'],'midi_pitch':event['midi_pitch'],
              'audio_start':round(float(start),4),'audio_end':round(float(end),4),
              'musical_role':role,
              'visual_role':'support' if role=='orchestra_support' else 'lead',
              'onset_source':onset_source,'release_source':release,
              'clock_shift_seconds':round(float(start-predicted),4)}
        if role in ('orchestra_melody','orchestra_chord'):
            note['role_confidence']=selected[(event['measure'],part)]['confidence']
        notes.append(note)
    counts['piano_sustain_bounded']=bound_piano_energy(notes,piano)
    trims=trim_piano_releases(notes)
    notes.sort(key=lambda n:(n['audio_start'],n['midi_pitch'],n['part_id']))
    output={'format_version':1,'title':'Prokofiev 3/III full-movement alignment',
            'orchestra_pressed_keys':True,
            'sources':{'score':{'path':score['source_score'],'sha256':score['source_score_sha256']},
                       'audio':{'path':score['source_audio'],'sha256':score['source_audio_sha256']}},
            'alignment_interval_seconds':[0,END],'notes':notes}
    (HERE/'alignment.json').write_text(json.dumps(output,ensure_ascii=False,separators=(',',':')))
    (HERE/'role-review.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
    qa={'score_notes':len(events),'render_notes':len(notes),'piano_score_notes':len(piano_events),
        'piano_detected_attacks':sum(map(len,piano.detections.values())),
        'role_measures':sum(bool(x['selected_parts']) for x in rows),
        'correction_max_ms':round(float(np.max(abs(values)))*1000,1),
        'onset_counts':dict(counts),'release_trim':trims,
        'excluded_score_events':excluded,'review_piano':review}
    (HERE/'alignment-qa.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in qa.items() if k not in ('excluded_score_events','review_piano')},
                     ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()
