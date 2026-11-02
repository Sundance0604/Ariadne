"""Build the Prokofiev 3/I first-three-minute waterfall timeline.

Orchestral alignment uses a three-level hierarchy: multiscale score/audio
clock, measure-level pitch/rhythm evidence, then bounded per-line attack
matching. Masked accompaniment inherits the measured clock and is never
snapped to an arbitrary peak. Piano notes may use score-consistent Transkun
onsets, while note releases remain constrained by the score and next attack.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import json
import re

import mido
import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.signal import find_peaks

from align_opening import (DT, PITCH_MAX, PITCH_MIN, extract_features,
                           load_stereo, simplify_unisons)
from orchestra_phrase_sync import view_for
from prepare_preview import (AUDIO, EXPECTED_AUDIO_SHA256, EXPECTED_SCORE_SHA256,
                             FFMPEG, HERE, MXL, compile_look, digest, parse_xml)

RENDER_SECONDS = 180
LOOKAHEAD = 5
LAST_MEASURE = 90
MIDI = HERE / "piano-audio125-transkun.mid"
TAIL_MIDI = HERE / "piano-audio115-185-transkun.mid"


def orchestra_role(event: dict) -> tuple[str, str | None, str]:
    m, p = event["measure"], event["part_id"]
    if p == "P14": return "lead", None, "piano"
    if m <= 7 and p == "P4": return "lead", "#f5d883", "clarinet"
    if 7 <= m <= 11:
        if p == "P15": return "lead", "#8ce5e0", "strings melody"
        if p == "P16": return "lead", "#a9b8ff", "strings harmony"
        if m == 11 and p == "P17" and event["start_beat"] >= 40.25:
            return "lead", "#8ce5e0", "viola run"
    if m == 12:
        if p == "P16": return "lead", "#8ce5e0", "strings run"
        if p == "P17": return "lead", "#a9b8ff", "strings harmony"
    if 13 <= m <= 14:
        if p == "P15": return "lead", "#8ce5e0", "strings melody"
        if p == "P16": return "lead", "#a9b8ff", "strings harmony"
    if 29 <= m <= 33 or 36 <= m <= 38:
        if p in ("P2", "P4"): return "lead", "#93e4da", "woodwind melody"
        if p in ("P3", "P5", "P16"): return "lead", "#bcb5f6", "orchestra harmony"
    if 50 <= m <= 53 and p == "P2":
        return "lead", "#93e4da", "woodwind melody"
    if 54 <= m <= 56 and p == "P15":
        return "lead", "#93e4da", "strings melody"
    if 57 <= m <= 60 and p == "P2":
        return "lead", "#93e4da", "woodwind melody"
    if 68 <= m <= 72:
        if p == "P15": return "lead", "#9addd2", "violin melody"
        if p == "P3" and m <= 71: return "lead", "#d3bd84", "oboe doubling"
    if 72 <= m <= 75 and p == "P4" and event["midi_pitch"] >= 69:
        return "lead", "#e2c78e", "clarinet melody"
    if m == 75 and p == "P2":
        return "lead", "#9addd2", "flute flourish"
    return "support", None, "orchestra support"


def clock_for_orchestra(beat: float, clock: PchipInterpolator,
                        offsets: np.ndarray) -> float:
    # Interpolate between neighbouring bars, preserving continuity around
    # orchestral handoffs instead of changing all falling notes at a boundary.
    centers = np.arange(len(offsets))*4+2
    correction = np.interp(beat, centers, offsets, left=offsets[0],right=offsets[-1])
    return float(clock(beat)+correction)


def read_midi_onsets(path, offset=0.) -> dict[int,list[float]]:
    midi = mido.MidiFile(path)
    output=defaultdict(list)
    for track in midi.tracks:
        seconds=0.0; tempo=500000
        for msg in track:
            seconds += mido.tick2second(msg.time,midi.ticks_per_beat,tempo)
            if msg.type=="set_tempo": tempo=msg.tempo
            elif msg.type=="note_on" and msg.velocity and seconds+offset>=47.7:
                output[msg.note].append(seconds+offset)
    return dict(output)


def audio_piano_onsets() -> dict[int,list[float]]:
    first=read_midi_onsets(MIDI)
    tail=read_midi_onsets(TAIL_MIDI,115.)
    result=defaultdict(list)
    for pitch in set(first)|set(tail):
        # Preserve the approved two-minute model output and use the fresh
        # cropped model only after the handoff. A 115 s crop provides context.
        result[pitch]=sorted([t for t in first.get(pitch,[]) if t<120.]
                             +[t for t in tail.get(pitch,[]) if t>=120.])
    return dict(result)


def foreground_groups(events: list[dict]) -> dict[tuple[str,str],list[dict]]:
    by=defaultdict(lambda:defaultdict(list))
    for event in events:
        role,_,label=orchestra_role(event)
        if role!="lead" or event["part_id"]=="P14":continue
        by[(event["part_id"],label)][event["start_beat"]].append(event)
    result={}
    for key,beats in by.items():
        result[key]=[{"part":key[0],"beat":beat,"events":items,
                      "pitches":sorted({e["midi_pitch"] for e in items})}
                     for beat,items in sorted(beats.items())]
    return result


def candidate_curve(group: dict, features: dict) -> np.ndarray:
    pitches=[p for p in group["pitches"] if PITCH_MIN<=p<=PITCH_MAX]
    if not pitches:return np.zeros(features["mid_onset"].shape[1],np.float32)
    if group["part"]=="P15" and 24<=group["beat"]<44:
        high=[p for p in pitches if p>=83]
        if high:pitches=high
    view=view_for(group["part"])
    rows=np.array(pitches)-PITCH_MIN
    curves=features[view+"_onset"][rows]
    return np.max(curves,axis=0)


def align_line(groups: list[dict], features: dict,
               clock: PchipInterpolator, offsets: np.ndarray,
               onset_peaks: dict) -> None:
    if not groups:return
    candidates=[];utility=[];confidence=[]
    for group in groups:
        predicted=clock_for_orchestra(group["beat"],clock,offsets)
        curve=candidate_curve(group,features)
        if group["beat"]<24: window=.19
        elif group["part"]=="P15" and group["beat"]<44:
            broad=curve[max(0,round((predicted-.56)/DT)):
                        min(len(curve),round((predicted+.56)/DT)+1)]
            near=curve[max(0,round((predicted-.19)/DT)):
                       min(len(curve),round((predicted+.19)/DT)+1)]
            window=.56 if len(broad) and len(near) and float(np.max(near))<.55*float(np.max(broad)) else .20
        elif group["beat"]<44: window=.17
        elif group["beat"]<56: window=.14
        else: window=.12
        if group["beat"]>=112: window=.11
        center=round(predicted/DT)
        lo=max(0,round((predicted-window)/DT));hi=min(len(curve),round((predicted+window)/DT)+1)
        context=curve[max(0,lo-100):min(len(curve),hi+100)]
        scale=max(float(np.percentile(context,92)),.04)
        peaks,_=find_peaks(curve[lo:hi],distance=4,prominence=.025)
        indexes=np.unique(np.r_[np.clip(center,lo,hi-1),lo+peaks]).astype(int)
        strength=curve[indexes]
        shift=indexes*DT-predicted
        penalty=(shift/max(window,.1))**2
        if window>.3:
            # A distant, prominent attack must beat a nearby harmonic. Do
            # not cap the two to the same utility merely because both exceed
            # a local percentile.
            score=1.7*np.log1p(2*strength/scale)-.85*penalty
        else:
            weight=1.65 if group["part"]=="P15" and 24<=group["beat"]<44 else 1.1
            score=weight*np.minimum(strength/scale,2.5)-.85*penalty
        # Independent filterbank peaks corroborate a string attack and help
        # reject stronger but unrelated harmonics in the STFT curve.
        if group["part"] in ("P2","P15") and max(group["pitches"])>=83:
            high=max(group["pitches"])
            key=f"mono_{high}_time"
            if key in onset_peaks:
                times=onset_peaks[key]
                strengths=onset_peaks[f"mono_{high}_strength"]
                zone=(times>=predicted-.65)&(times<=predicted+.65)
                if np.any(zone):
                    neighborhood=times[zone];levels=strengths[zone]
                    baseline=max(float(np.percentile(levels,70)),1e-7)
                    for j,index in enumerate(indexes):
                        match=np.where(abs(neighborhood-index*DT)<.05)[0]
                        if len(match):
                            score[j]+=.40*min(float(np.max(levels[match])/baseline),2)
        # The score clock is an explicit fallback for an acoustically masked
        # note. The peak matcher is not allowed to invent an attack there.
        if float(np.max(context))<.055: score[indexes==np.clip(center,lo,hi-1)]+=1.5
        candidates.append(indexes);utility.append(score)
        confidence.append(strength/scale)
    dp=utility[0].copy();back=[]
    for i in range(1,len(groups)):
        prev_pred=clock_for_orchestra(groups[i-1]["beat"],clock,offsets)
        next_pred=clock_for_orchestra(groups[i]["beat"],clock,offsets)
        expected=max(.04,next_pred-prev_pred)
        gap=(candidates[i][:,None]-candidates[i-1][None,:])*DT
        # The orchestra may accelerate inside a phrase, but successive
        # distinct attacks cannot reverse order or collapse onto one peak.
        minimum=max(.034,expected*.35)
        allowed=(gap>=minimum)&(gap<=expected*2.4+.17)
        transition=-.18*((gap-expected)/max(expected,.14))**2
        lattice=dp[None,:]+transition
        lattice[~allowed]=-1e6
        best=np.argmax(lattice,axis=1)
        dp=utility[i]+lattice[np.arange(len(best)),best]
        back.append(best)
    indexes=np.empty(len(groups),int);indexes[-1]=int(np.argmax(dp))
    for i in range(len(groups)-2,-1,-1):indexes[i]=back[i][indexes[i+1]]
    for group,poss,k,conf in zip(groups,candidates,indexes,confidence):
        group["time"]=float(poss[k]*DT)
        group["confidence"]=float(conf[k])
        group["clock_time"]=clock_for_orchestra(group["beat"],clock,offsets)


def piano_attack(event: dict, predicted: float,
                 onsets: dict[int,list[float]], used: dict[int,set[int]]) -> tuple[float,bool]:
    pitch=event["midi_pitch"]
    candidates=onsets.get(pitch,[])
    if not candidates:return predicted,False
    available=[(abs(t-predicted),i,t) for i,t in enumerate(candidates)
               if i not in used[pitch] and abs(t-predicted)<=.13]
    if not available:return predicted,False
    error,index,time=min(available)
    used[pitch].add(index)
    return time,True


def finalize_releases(notes: list[dict]) -> None:
    by_key=defaultdict(list)
    for note in notes:by_key[note["midi_pitch"]].append(note)
    for items in by_key.values():
        items.sort(key=lambda n:n["audio_start"])
        for i,note in enumerate(items[:-1]):
            following=items[i+1]
            if following["audio_start"]>note["audio_start"]+.045:
                note["audio_end"]=min(note["audio_end"],following["audio_start"]-.012)
            note["audio_end"]=max(note["audio_start"]+.055,note["audio_end"])


def visual_sections(base: dict) -> list[dict]:
    """Movement-specific lighting cues; geometry and key textures stay fixed."""
    cues = [
        # time, transition, piano low/high, air/veil, glint density, glow
        (0, 0, "#e5cf9d", "#b6ddd9", "#273f57", "#739cbd", .055, .11, .60, 1.05),
        (40, 6, "#e5cf9d", "#8ce5e0", "#174c57", "#70cec9", .10, .16, 1.00, 1.13),
        (49, 8, "#f0d49d", "#aed8d0", "#46445a", "#b6a2ce", .10, .18, 1.15, 1.16),
        (90, 16, "#e7c89b", "#a8d1da", "#3d435b", "#a5b1d0", .085, .16, 1.05, 1.12),
        (122, 12, "#dbc3be", "#a7c7db", "#363b60", "#9298db", .075, .12, .72, 1.09),
        (139, 9, "#e0c79e", "#99d7ce", "#284655", "#88bbb7", .13, .21, 1.17, 1.18),
        (156, 10, "#edd39f", "#a8d5e2", "#2c4860", "#9cc8e2", .115, .18, 1.20, 1.19),
        (173, 7, "#f0d39c", "#b7d4e5", "#3c4254", "#b7bdd8", .10, .16, 1.28, 1.20),
    ]
    result=[]
    for index,(start,transition,low,high,air,veil,veil_amount,dust,density,glow) in enumerate(cues):
        look=deepcopy(base)
        look["colors"].update(piano_low=low,piano_high=high,strike=high)
        look["appearance"].update(background_tint=air,veil_tint=veil,
            refracted_veil=veil_amount,background_dust=dust,
            background_atmosphere=.20 if start<120 else .23,
            horizon_tint=high,keyboard_tint="#b5afb0",
            material_amount=1.06 if start<120 else 1.20)
        look["brightness"]["note_glow"]=glow
        look["brightness"]["note_material"]=1.04 if start<120 else 1.09
        for key in ("ember_attack_count","streak_attack_count","filament_attack_count"):
            look["density"][key]=max(0,round(look["density"][key]*density))
        for key in ("ember_per_second","streak_per_second","smoke_per_second",
                    "light_per_second","glint_per_second","filament_per_second"):
            look["density"][key]=round(look["density"][key]*density,4)
        # A few crystalline flashes above attacks add texture without drawing
        # a second opaque particle sheet over the orchestra.
        look["density"]["glint_per_second"]=round(look["density"]["glint_per_second"]*1.65,4)
        result.append({"name":["Clarinet twilight","String quickening","Piano entrance",
                              "Piano and winds","Piano interlude","Violin and oboe reply",
                              "Piano return","Building run"][index],
                       "start_seconds":start,"end_seconds":185,
                       "transition_seconds":transition,"preset":look})
    return result


def main() -> None:
    if digest(AUDIO)!=EXPECTED_AUDIO_SHA256 or digest(MXL)!=EXPECTED_SCORE_SHA256:
        raise ValueError("Source fingerprint changed")
    events=parse_xml(MXL,max_measure=LAST_MEASURE)
    clock_data=json.loads((HERE/"prokofiev3-orchestra-clock190.json").read_text())
    phrase_data=json.loads((HERE/"prokofiev3-orchestra-phrase-offsets190.json").read_text())
    clock=PchipInterpolator(*zip(*clock_data["beat_time"]))
    offsets=np.array([r["offset_seconds"] for r in phrase_data["measure_offsets"]])
    features=extract_features(load_stereo(AUDIO,FFMPEG,185),clock_data["tuning_cents"])
    onset_peaks=np.load(HERE/"orchestra-onset-peaks.npz")
    groups=foreground_groups(events)
    for group_list in groups.values():align_line(group_list,features,clock,offsets,onset_peaks)
    # The high violin octave at beat 28 has a quiet first attack immediately
    # at the ensemble clock, then a louder repeated harmonic ~0.36 s later.
    # The line matcher favors the latter. The independent pitch filterbank and
    # second-violin attack both corroborate the earlier time, so use that
    # measured peak for this audited passage rather than snapping to the loudest.
    for group_list in groups.values():
        for group in group_list:
            if group["part"] == "P15" and group["beat"] == 28.0 and \
                    group["time"] - group["clock_time"] > .25:
                times=onset_peaks["mono_91_time"]
                nearby=times[abs(times-group["clock_time"])<.08]
                if len(nearby):
                    group["time"]=float(nearby[np.argmin(abs(nearby-group["clock_time"]))])
                    group["attack_resolution"]="first corroborated pitch attack"
    exact={(g["part"],g["beat"]):g for gs in groups.values() for g in gs}
    piano=audio_piano_onsets();used=defaultdict(set)
    notes=[];stats=defaultdict(list);piano_matched=0
    for index,event in enumerate(events):
        beat=event["start_beat"]
        role,color,label=orchestra_role(event)
        if event["part_id"]=="P14":
            predicted=float(clock(beat))
            start,matched=piano_attack(event,predicted,piano,used)
            piano_matched+=matched
            end=float(clock(event["end_beat"]))
        else:
            predicted=clock_for_orchestra(beat,clock,offsets)
            matched_group=exact.get((event["part_id"],beat))
            if matched_group is not None:
                start=matched_group["time"]
                stats[label].append(start-predicted)
            else:start=predicted
            end=clock_for_orchestra(event["end_beat"],clock,offsets)
        if start>RENDER_SECONDS+LOOKAHEAD or end<0:continue
        end=max(start+.07,end)
        note={"score_id":f"p3-m{event['measure']}-{event['part_id']}-{index}",
              "event_id":f"p3-{event['part_id']}-{index}",
              "part_id":event["part_id"],"part_name":event["part_name"],
              "family":event["family"],"midi_pitch":event["midi_pitch"],
              "audio_start":round(start,4),"audio_end":round(end,4),
              "visual_role":role}
        if color:
            note.update(accent_color=color,accent_emitter_scale=.72,
                        accent_filament_attack_count=2,
                        accent_filament_per_second=1.3,
                        accent_light_per_second=1.6)
        notes.append(note)
    before=len(notes)
    notes=simplify_unisons(notes)
    finalize_releases(notes)
    # The user approved the earlier two-minute synchronization apart from the
    # high octave passage and the missed viola role. Reuse those exact event
    # times instead of allowing a longer DTW run to shift unrelated notes.
    approved=json.loads((HERE/"prokofiev3-opening120.timeline.json").read_text())
    original=[deepcopy(n) for n in approved["notes"] if n["audio_start"]<120
              and not (24.25<=n["audio_start"]<30.2)]
    for note in original:
        measure=int(re.search(r"-m(\d+)-",note["score_id"]).group(1))
        if measure==11 and note["part_id"]=="P17" and note["audio_start"]>=41.55:
            note.update(visual_role="lead",accent_color="#8ce5e0",
                        accent_emitter_scale=.72,
                        accent_filament_attack_count=2,
                        accent_filament_per_second=1.3,
                        accent_light_per_second=1.6)
    correction=[n for n in notes if 24.25<=n["audio_start"]<30.2]
    extension=[n for n in notes if n["audio_start"]>=120]
    notes=sorted(original+correction+extension,
                 key=lambda n:(n["audio_start"],n["midi_pitch"]))
    scene=compile_look({"look":"glass","density":.28,"speed":.62,
                        "piano_low":"#ead39f","piano_high":"#b4dada",
                        "keyboard":"#b5afb0","horizon":"#d3ccbf",
                        "appearance_overrides":{"background_motif_opacity":0.,
                            "orchestra_base_alpha":.34,
                            "orchestra_lead_alpha":.92,
                            "orchestra_emitter_scale":.30,
                            "orchestra_neutral_color":"#aeb6bb"}})
    timeline={"format_version":1,"title":"Prokofiev 3/I — first 3 minutes",
              "orchestra_pressed_keys":True,
              "sources":{"audio":{"path":str(AUDIO),"sha256":digest(AUDIO)},
                         "score":{"path":str(MXL),"sha256":digest(MXL)}},
              "render_interval":{"start_seconds":0,"duration_seconds":RENDER_SECONDS,
                                 "lookahead_seconds":LOOKAHEAD},
              "visual_sections":visual_sections(scene),"notes":notes}
    output=HERE/"prokofiev3-opening180.timeline.json"
    output.write_text(json.dumps(timeline,ensure_ascii=False,separators=(",",":"))+"\n")
    qa={"score_events":len(events),"render_notes_before_unisons":before,
        "render_notes_after_unisons":len(notes),"piano_score_notes":sum(e['part_id']=='P14' for e in events),
        "piano_onsets_matched":piano_matched,
        "approved_first120_frozen_except_seconds":[24.25,30.2],
        "high_octave_replacement_notes":len(correction),
        "new_notes_at_or_after_120":len(extension),
        "orchestra_lead_groups":{label:{"count":len(shifts),
            "median_absolute_local_shift_ms":round(float(np.median(abs(np.array(shifts))))*1000,1),
            "largest_local_shift_ms":round(float(np.max(abs(np.array(shifts))))*1000,1)}
            for label,shifts in stats.items() if shifts},
        "orchestra_lead_events":[{"part":g['part'],"beat":g['beat'],
          "clock":round(g['clock_time'],3),"time":round(g['time'],3),
          "confidence":round(g['confidence'],2),
          "attack_resolution":g.get('attack_resolution','line matcher')}
          for gs in groups.values() for g in gs],
        "alignment_method":"global multiscale DTW + measure ensemble onset pattern + bounded line Viterbi"}
    (HERE/"prokofiev3-opening180.timeline.qa.json").write_text(
        json.dumps(qa,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({k:v for k,v in qa.items() if k!="orchestra_lead_events"},
                     ensure_ascii=False,indent=2))


if __name__=="__main__":main()
