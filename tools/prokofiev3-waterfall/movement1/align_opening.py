"""Score-informed, per-attack alignment of Prokofiev 3/I's opening minute.

This deliberately treats the MusicXML as an ordered list of candidate pitches,
not as the performed timing. It extracts stereo pitch envelopes from the supplied
recording, matches foreground attacks with a monotone dynamic program, then
derives note releases from the measured envelopes. Unsupported duplicate unisons
are combined so two desks cannot draw contradictory bars on the same key.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks, stft

from prepare_preview import (AUDIO, EXPECTED_AUDIO_SHA256, EXPECTED_SCORE_SHA256,
                             FFMPEG, HERE, MXL, compile_look, digest, parse_xml)

RATE = 22050
HOP = 220
DT = HOP / RATE
FFT = 4096
MAX_TIME = 65.0
PITCH_MIN, PITCH_MAX = 42, 100

# Phrase locations are recording-specific coarse guards. Every attack within
# them is optimized from the actual stereo recording, including fast runs.
BEAT_TIME_GUARDS = [
    (0, 0), (1, .30), (1.5, .82), (2, 1.39), (3, 2.20), (4, 3.23),
    (5, 4.08), (6, 5.08), (6.5, 5.47), (7, 5.93), (7.5, 6.47),
    (8, 6.95), (9, 7.86), (13.5, 12.17), (14, 12.91),
    (15.5, 14.22), (16, 14.776), (17, 15.654), (17.5, 16.103),
    (18, 16.502), (18.5, 17.091), (19, 17.610), (19.5, 18.009),
    (20, 18.160), (21, 19.127), (22, 20.194), (23, 21.471),
    (24, 22.978), (25, 24.913), (25.5, 25.382), (26, 25.881),
    (27, 26.629), (28, 27.667), (29, 28.884), (30, 30.102),
    (30.5, 30.900), (31, 31.459), (31.5, 31.738), (32, 32.257),
    (33, 33.504), (33.5, 33.923), (34, 34.482), (35, 35.928),
    (36, 37.160), (37.5, 38.550), (38, 39.160), (39.5, 41.110),
    (40, 41.635), (44, 42.912), (48, 44.798), (56, 48.08),
    (72, 54.66), (88, 61.25),
]


def load_stereo(audio: Path, ffmpeg: Path, seconds: float = MAX_TIME) -> np.ndarray:
    proc = subprocess.run([str(ffmpeg), "-hide_banner", "-loglevel", "error",
                           "-i", str(audio), "-t", str(seconds), "-ac", "2",
                           "-ar", str(RATE), "-f", "f32le", "pipe:1"],
                          capture_output=True, check=True)
    return np.frombuffer(proc.stdout, "<f4").reshape(-1, 2).T.copy()


def extract_features(stereo: np.ndarray, tuning_cents: float = 0) -> dict[str, np.ndarray]:
    """Three spatial views and two time resolutions at the actual pitch."""
    channels = {"left": stereo[0], "right": stereo[1],
                "mid": (stereo[0] + stereo[1]) * .5}
    spectra = {}
    for name, signal in channels.items():
        _, _, z = stft(signal, fs=RATE, nperseg=FFT,
                       noverlap=FFT-HOP, boundary="zeros")
        spectra[name] = np.abs(z).astype(np.float32)
    # Channel residuals help separate left-biased first violins from the
    # right-biased second violin figure in bars 12–14.
    spectra["first"] = np.maximum(0, spectra["left"] - .55 * spectra["right"])
    spectra["second"] = np.maximum(0, spectra["right"] - .55 * spectra["left"])
    pitches = np.arange(PITCH_MIN, PITCH_MAX + 1)
    out = {}
    for name, mag in spectra.items():
        rows = []
        for p in pitches:
            hz = 440.0 * 2 ** ((int(p) - 69) / 12 + tuning_cents / 1200)
            components = []
            for harmonic in (1, 2, 3):
                index = round(hz * harmonic * FFT / RATE)
                if index + 2 >= len(mag):
                    break
                peak = np.max(mag[max(0, index-1):index+2], axis=0)
                # The fundamental dominates; upper harmonics help the weaker
                # bass notes but do not fabricate an octave note on their own.
                components.append(peak / (harmonic ** 1.45))
            rows.append(np.sum(components, axis=0))
        raw = np.stack(rows).astype(np.float32)
        raw = gaussian_filter1d(raw, .7, axis=1)
        # A half-semitone spectral floor removes broad-band noise/transients.
        local_floor = gaussian_filter1d(raw, 1.25, axis=0)
        salience = np.maximum(0, raw - .34 * local_floor)
        out[f"{name}_energy"] = salience
        # Attack contrast over 45 ms, with a 20 ms smoothing window. The
        # dynamic program decides which pitch-correlated peak is the score note.
        log = np.log1p(salience * 220)
        onset = np.maximum(0, log - np.roll(log, 5, axis=1))
        onset[:, :5] = 0
        out[f"{name}_onset"] = gaussian_filter1d(onset, 1.0, axis=1)
    return out


def coarse_time(beat: float) -> float:
    b, t = np.asarray(BEAT_TIME_GUARDS).T
    if beat <= b[-1]:
        return float(np.interp(beat, b, t))
    return float(t[-1] + (beat-b[-1]) * (t[-1]-t[-2])/(b[-1]-b[-2]))


def part_view(part: str) -> str:
    return "first" if part == "P15" else "second" if part == "P16" else "mid"


def foreground(event: dict) -> bool:
    m, p = event["measure"], event["part_id"]
    return ((m <= 7 and p == "P4") or
            (7 <= m <= 11 and p in ("P15", "P16")) or
            (m == 12 and p in ("P16", "P17")) or
            (13 <= m <= 14 and p == "P15") or
            (m >= 15 and p == "P14"))


def group_attacks(events: list[dict]) -> dict[str, list[dict]]:
    by_part = defaultdict(lambda: defaultdict(list))
    for event in events:
        if foreground(event) and event["start_beat"] < 88:
            by_part[event["part_id"]][event["start_beat"]].append(event)
    groups = {}
    for part, beats in by_part.items():
        groups[part] = [{"part": part, "beat": beat,
                         "events": onsets, "pitches": sorted({e["midi_pitch"] for e in onsets})}
                        for beat, onsets in sorted(beats.items())]
    return groups


def attack_curve(group: dict, features: dict) -> np.ndarray:
    name = part_view(group["part"])
    attacks = features[f"{name}_onset"]
    energy = features[f"{name}_energy"]
    rows = [p-PITCH_MIN for p in group["pitches"] if PITCH_MIN <= p <= PITCH_MAX]
    if not rows:
        return np.zeros(attacks.shape[1], np.float32)
    curves = attacks[rows]
    # For a chord, two strong notes should suffice. A weak/countermelody pitch
    # must not overwhelm the attack time of the audible main notes.
    if len(rows) > 2:
        curve = np.mean(np.sort(curves, axis=0)[-2:], axis=0)
    else:
        curve = np.mean(curves, axis=0)
    # Reject attacks that have virtually no pitch energy immediately after.
    post = np.mean(energy[rows], axis=0)
    scale = np.percentile(post, 98) + 1e-6
    return curve * np.minimum(1, post / (.17 * scale))


def align_part(groups: list[dict], features: dict) -> list[dict]:
    """Viterbi matching of ordered score attacks to pitch-specific audio peaks."""
    if not groups:
        return groups
    candidates = []
    scores = []
    for group in groups:
        predicted = coarse_time(group["beat"])
        # First 16 beats are sparse/rubato; the later scale run needs a tighter
        # guard so the same bright onset cannot be assigned to adjacent notes.
        window = .38 if group["beat"] < 40 else .29
        if group["beat"] >= 48:
            window = .33
        lo = max(0, int((predicted-window)/DT))
        hi = min(features["mid_onset"].shape[1]-1, int((predicted+window)/DT))
        curve = attack_curve(group, features)
        local = curve[lo:hi+1]
        peaks, _ = find_peaks(local, distance=4, prominence=max(float(np.max(local))*.045, .006))
        possible = np.unique(np.r_[lo+peaks, np.arange(lo, hi+1, 3),
                                    np.clip(round(predicted/DT),lo,hi)]).astype(int)
        strength = curve[possible]
        normal = max(float(np.percentile(curve[max(0, lo-50):min(len(curve), hi+51)], 97)), .015)
        deviation = np.abs(possible*DT-predicted)
        # Onset evidence can move an event within the phrase guard, but cannot
        # arbitrarily rearrange the score sequence.
        utility = 1.25*np.log1p(4*strength/normal) - 1.4*(deviation/window)**2
        candidates.append(possible)
        scores.append(utility)
    paths = []
    previous = scores[0]
    paths.append(np.full(len(candidates[0]),-1,int))
    for i in range(1,len(groups)):
        prior_interval = max(.04, coarse_time(groups[i]["beat"])-coarse_time(groups[i-1]["beat"]))
        gap = (candidates[i][:,None]-candidates[i-1][None,:])*DT
        allowed = gap >= (.055 if prior_interval < .17 else .07)
        # Restrict local accelerando/rallentando rather than taking unrelated
        # attacks in the accompaniment.
        allowed &= gap >= max(.045, prior_interval*.37)
        allowed &= gap <= prior_interval*2.3 + .18
        transition = -.48*((gap-prior_interval)/max(prior_interval,.12))**2
        lattice = previous[None,:] + transition
        lattice[~allowed] = -1e6
        best = np.argmax(lattice,axis=1)
        previous = scores[i] + lattice[np.arange(len(best)),best]
        paths.append(best)
    selected = np.empty(len(groups),int)
    selected[-1] = int(np.argmax(previous))
    for i in range(len(groups)-1,0,-1):
        selected[i-1] = paths[i][selected[i]]
    for group, indexes, choice in zip(groups,candidates,selected):
        moment = float(indexes[choice]*DT)
        group["time"] = moment
        group["drift"] = moment-coarse_time(group["beat"])
        curve = attack_curve(group,features)
        group["attack_strength"] = float(curve[indexes[choice]])
    return groups


def make_time_map(groups: dict[str,list[dict]]) -> PchipInterpolator:
    # Use the audible foreground line to update the beat-to-second map. Other
    # parts are subsequently free to make a small, independently evidenced move.
    picks = []
    for part, gs in groups.items():
        for g in gs:
            if (g["attack_strength"] >= .045 and
                    (part == "P14" or (part == "P4" and g["beat"] < 28) or
                     (part == "P15" and 28 <= g["beat"] < 40) or
                     (part == "P16" and 44 <= g["beat"] < 48) or
                     (part == "P15" and 48 <= g["beat"] < 56))):
                picks.append(g)
    picks.sort(key=lambda g:g["beat"])
    # A weak pitch peak cannot bend the whole clock. Clip against coarse time,
    # then enforce increasing time before monotone interpolation.
    beats = [0.0]
    times = [0.0]
    for g in picks:
        if g["beat"] <= beats[-1] or g["beat"] >= 90:
            continue
        t = float(np.clip(g["time"],coarse_time(g["beat"])-.28,coarse_time(g["beat"])+.28))
        if t <= times[-1]+.045:
            continue
        beats.append(g["beat"]); times.append(t)
    beats.append(92.0); times.append(coarse_time(92))
    return PchipInterpolator(beats,times)


def refine_support_onset(event: dict, estimated: float, features: dict) -> tuple[float,float]:
    p=event["midi_pitch"]
    if not PITCH_MIN <= p <= PITCH_MAX:
        return estimated,0.0
    name=part_view(event["part_id"])
    curve=features[f"{name}_onset"][p-PITCH_MIN]
    center=round(estimated/DT)
    radius=round((.10 if event["measure"] < 15 else .075)/DT)
    lo=max(0,center-radius); hi=min(len(curve),center+radius+1)
    index=lo+int(np.argmax(curve[lo:hi]))
    local_peak=float(curve[index])
    context=float(np.percentile(curve[max(0,center-50):min(len(curve),center+51)],90))+.001
    if local_peak < max(.035,context*.45):
        return estimated,0.0
    return float(index*DT),min(1.0,local_peak/(context*1.4))


def refine_chord_member_onset(event: dict, group: dict, features: dict) -> tuple[float,float]:
    """Resolve a played roll without moving an entire score chord together."""
    start=group["time"]
    p=event["midi_pitch"]
    if event["part_id"]!="P14" or len(group["pitches"])<2 or not PITCH_MIN<=p<=PITCH_MAX:
        return start,min(1.0,group["attack_strength"]/.14)
    curve=features["mid_onset"][p-PITCH_MIN]
    center=round(start/DT)
    radius=round(.065/DT)
    lo=max(0,center-radius);hi=min(len(curve),center+radius+1)
    if hi<=lo:return start,0.0
    peaks,_=find_peaks(curve[lo:hi],distance=3)
    possible=np.unique(np.r_[lo+peaks,np.clip(center,lo,hi-1)]).astype(int)
    local=curve[possible]
    utility=local-.45*np.abs(possible-center)*DT
    best=int(np.argmax(utility))
    strength=float(local[best])
    if strength<.13 or strength<.65*float(np.max(curve[lo:hi])):
        return start,min(1.0,strength/.14)
    return float(possible[best]*DT),min(1.0,strength/.14)


def measured_release(event:dict,start:float,score_end:float,features:dict)->float:
    p=event["midi_pitch"]
    if not PITCH_MIN <= p <= PITCH_MAX:
        return score_end
    view=part_view(event["part_id"])
    energy=features[f"{view}_energy"][p-PITCH_MIN]
    lo=max(0,round((start+.045)/DT)); hi=min(len(energy),round((min(start+4.0,score_end+.65))/DT))
    if hi <= lo+3:
        return max(start+.08,score_end)
    smooth=gaussian_filter1d(energy[lo:hi],2)
    # For an acoustically audible release, stop after the envelope drops below
    # 27% of its early robust level. Reverb is not a held key.
    early=smooth[:min(len(smooth),max(10,round(.35/DT)))]
    reference=float(np.percentile(early,75))
    if reference <= 1e-6:
        return max(start+.10,score_end)
    threshold=max(reference*.27,float(np.percentile(smooth,15))*1.10)
    search=max(0,round((score_end-start-.55)/DT))
    for i in range(search,len(smooth)-4):
        if np.all(smooth[i:i+5]<threshold):
            return max(start+.10,float((lo+i)*DT))
    return max(start+.10,score_end)


def simplify_unisons(notes:list[dict])->list[dict]:
    """One bar per physical key; merge audible legato and drop shadow duplicates."""
    by_pitch=defaultdict(list)
    for note in notes: by_pitch[note["midi_pitch"]].append(note)
    result=[]
    for pitch, items in by_pitch.items():
        ordered=sorted(items,key=lambda n:(n["audio_start"],n["visual_role"]!="lead"))
        kept=[]
        for note in ordered:
            if kept and note["audio_start"] < kept[-1]["audio_end"]-.025:
                previous=kept[-1]
                # Never let an earlier background desk acquire the colour or
                # attack of a later solo/piano note on the same key.
                if (note["visual_role"]=="lead" and previous["visual_role"]!="lead"
                        and note["audio_start"]-previous["audio_start"]>=.05):
                    previous["audio_end"]=note["audio_start"]-.012
                    kept.append(note)
                    continue
                if previous["visual_role"]=="lead" and note["visual_role"]!="lead":
                    continue
                # A proven re-attack opens a new bar; otherwise maintain the
                # more prominent layer over overlapping unison desks.
                if (note.get("onset_confidence",0)<.50 or
                        note["audio_start"]-previous["audio_start"]<.12):
                    if previous["part_id"]==note["part_id"]:
                        previous["audio_end"]=max(previous["audio_end"],note["audio_end"])
                    if note["visual_role"]=="lead" and previous["visual_role"]!="lead":
                        for key in ("visual_role","accent_color","accent_emitter_scale",
                                    "accent_filament_attack_count","accent_filament_per_second",
                                    "accent_light_per_second"):
                            if key in note: previous[key]=note[key]
                    continue
                previous["audio_end"]=min(previous["audio_end"],note["audio_start"]-.012)
            kept.append(note)
        result.extend(kept)
    return sorted(result,key=lambda n:(n["audio_start"],n["midi_pitch"]))


def build_timeline(events:list[dict],groups:dict,features:dict,score_path:Path,audio_path:Path)->tuple[dict,dict]:
    clock=make_time_map(groups)
    exact={(g["part"],g["beat"]):g for gs in groups.values() for g in gs}
    notes=[]; drifts=[]; weak=[]; chord_shifts=[]
    for index,event in enumerate(events):
        beat=event["start_beat"]
        if beat > 91:continue
        estimated=float(clock(beat))
        matched=exact.get((event["part_id"],beat))
        if matched is not None:
            start,confidence=refine_chord_member_onset(event,matched,features)
            if start!=matched["time"]:
                chord_shifts.append(round((start-matched["time"])*1000))
        else:
            start,confidence=refine_support_onset(event,estimated,features)
        # Background notes are only allowed modest individual shifts; the
        # performance clock remains the reference when their audio is masked.
        if matched is None and abs(start-estimated)>.11:
            start=estimated
        score_end=float(clock(event["end_beat"]))
        end=measured_release(event,start,score_end,features)
        if end<0 or start>64 or end-start<.065:continue
        lead=foreground(event)
        role="lead" if lead else "support"
        color=("#f5d883" if event["part_id"]=="P4" and lead else
               "#8ce5e0" if event["part_id"]=="P15" and lead else
               "#a9b8ff" if event["part_id"] in ("P16","P17") and lead else None)
        note={"score_id":f"p3-m{event['measure']}-{event['part_id']}-{index}",
              "event_id":f"p3-{event['part_id']}-{index}",
              "part_id":event["part_id"],"part_name":event["part_name"],
              "family":event["family"],"midi_pitch":event["midi_pitch"],
              "audio_start":round(start,4),"audio_end":round(end,4),
              "visual_role":role,"onset_confidence":round(confidence,3)}
        if color:
            note.update(accent_color=color,accent_emitter_scale=.72,
                        accent_filament_attack_count=2,
                        accent_filament_per_second=1.3,
                        accent_light_per_second=1.6)
        notes.append(note)
        if matched is not None:
            drifts.append(matched["drift"])
            if matched["attack_strength"]<.042:weak.append(note["score_id"])
    raw_count=len(notes)
    notes=simplify_unisons(notes)
    for note in notes:note.pop("onset_confidence",None)
    section=compile_look({"look":"glass","density":.28,"speed":.62,
                          "piano_low":"#ead39f","piano_high":"#b4dada",
                          "keyboard":"#b5afb0","horizon":"#d3ccbf",
                          "appearance_overrides":{"background_motif_opacity":0.0,
                                                  "orchestra_base_alpha":.34,
                                                  "orchestra_lead_alpha":.92,
                                                  "orchestra_emitter_scale":.30,
                                                  "orchestra_neutral_color":"#aeb6bb"}})
    timeline={"format_version":1,"title":"Prokofiev 3/I — opening 60 seconds",
              "orchestra_pressed_keys":True,
              "sources":{"audio":{"path":str(audio_path.resolve()),"sha256":digest(audio_path)},
                         "score":{"path":str(score_path.resolve()),"sha256":digest(score_path)}},
              "render_interval":{"start_seconds":0,"duration_seconds":60,"lookahead_seconds":5},
              "visual_sections":[{"name":"Opening: clarinet, strings, then piano",
                                  "start_seconds":0,"end_seconds":65,"transition_seconds":0,
                                  "preset":section}],"notes":notes}
    qa={"score_notes":len(events),"raw_render_notes":raw_count,
        "after_unison_merging":len(notes),"matched_foreground_groups":sum(map(len,groups.values())),
        "weak_foreground_groups":weak,"individual_chord_shifts_ms":chord_shifts,
        "median_foreground_drift_ms":round(float(np.median(np.abs(drifts)))*1000,1),
        "alignment_map":[[int(b),round(float(clock(b)),3)] for b in range(0,89,4)],
        "foreground_by_part":{part:[{"beat":g["beat"],"time":round(g["time"],3),
                                     "drift_ms":round(g["drift"]*1000),
                                     "attack":round(g["attack_strength"],4)}
                                    for g in gs] for part,gs in groups.items()}}
    return timeline,qa


def main()->None:
    ap=argparse.ArgumentParser()
    ap.add_argument("--audio",type=Path,default=AUDIO)
    ap.add_argument("--mxl",type=Path,default=MXL)
    ap.add_argument("--ffmpeg",type=Path,default=FFMPEG)
    ap.add_argument("--output",type=Path,default=HERE/"prokofiev3-opening60.timeline.json")
    args=ap.parse_args()
    if digest(args.audio)!=EXPECTED_AUDIO_SHA256 or digest(args.mxl)!=EXPECTED_SCORE_SHA256:
        raise ValueError("The phrase guards are specific to the supplied recording and score")
    events=parse_xml(args.mxl,max_measure=24)
    stereo=load_stereo(args.audio,args.ffmpeg)
    features=extract_features(stereo)
    groups=group_attacks(events)
    for gs in groups.values():align_part(gs,features)
    timeline,qa=build_timeline(events,groups,features,args.mxl,args.audio)
    args.output.write_text(json.dumps(timeline,ensure_ascii=False,separators=(",",":"))+"\n")
    args.output.with_suffix(".qa.json").write_text(json.dumps(qa,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({k:v for k,v in qa.items() if k!="foreground_by_part"},ensure_ascii=False,indent=2))


if __name__=="__main__":main()
