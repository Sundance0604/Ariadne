"""Score-conditioned orchestral phrase timing for Prokofiev 3/I, 0–120 s.

The global Sync Toolbox clock is a tempo guide. For each score measure, a
pitch-and-rhythm onset pattern from its audible orchestral line is compared
with the recorded spectrum over a bounded offset range. A dynamic program
chooses a smooth sequence of measure offsets. This avoids pulling every
masked background note to an unrelated spectral peak.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path

import numpy as np
from scipy.interpolate import PchipInterpolator

from align_opening import DT, PITCH_MAX, PITCH_MIN, extract_features, load_stereo
from prepare_preview import AUDIO, EXPECTED_AUDIO_SHA256, EXPECTED_SCORE_SHA256, FFMPEG, HERE, MXL, digest, parse_xml

SECONDS = 125
LAST_MEASURE = 62
SHIFTS = np.arange(-.7, .701, .02)


def primary_parts(measure: int) -> tuple[str, ...]:
    if measure <= 6: return ("P4",)
    if measure <= 11: return ("P15",)
    if measure == 12: return ("P16",)
    if measure <= 14: return ("P15",)
    if measure <= 18: return ("P4",)
    if measure == 19: return ("P15",)
    if measure <= 24: return ("P4",)
    if measure <= 26: return ("P15",)
    if measure <= 28: return ()
    if measure <= 34: return ("P2",)
    if measure == 35: return ()
    if measure <= 39: return ("P2",)
    if measure <= 45: return ()
    if measure <= 49: return ("P15",)
    if measure <= 53: return ("P2",)
    if measure <= 55: return ("P15",)
    if measure <= 60: return ("P2", "P15")
    if 68 <= measure <= 72: return ("P15",)
    if 73 <= measure <= 75: return ("P4",)
    return ()


def view_for(part: str) -> str:
    return "first" if part in ("P2", "P15") else "second" if part == "P16" else "mid"


def selected_events(events: list[dict], measure: int) -> list[dict]:
    parts = primary_parts(measure)
    if not parts: return []
    relevant = [e for e in events if e["measure"] == measure and e["part_id"] in parts]
    # The upper octave of a doubled melody is normally more audible. Keep
    # only one observation at a written beat/pitch, without altering the score.
    if measure in range(7, 12): relevant = [e for e in relevant if e["midi_pitch"] >= 83]
    if measure in range(29, 40): relevant = [e for e in relevant if e["midi_pitch"] >= 80]
    if 46 <= measure <= 60: relevant = [e for e in relevant if e["midi_pitch"] >= 75]
    if measure >= 61: relevant = [e for e in relevant if e["midi_pitch"] >= 68]
    unique = {(e["part_id"], e["start_beat"], e["midi_pitch"]):e for e in relevant}
    relevant = sorted(unique.values(), key=lambda e:(e["start_beat"],e["midi_pitch"]))
    if len(relevant) > 20:
        indices = np.linspace(0, len(relevant)-1, 20).round().astype(int)
        relevant = [relevant[i] for i in indices]
    return relevant


def measure_evidence(events: list[dict], measure: int, clock: PchipInterpolator,
                     features: dict[str,np.ndarray]) -> tuple[np.ndarray, int]:
    chosen = selected_events(events, measure)
    scores = np.zeros(SHIFTS.size, np.float64)
    good = 0
    for event in chosen:
        pitch = event["midi_pitch"]
        if not PITCH_MIN <= pitch <= PITCH_MAX: continue
        onset = features[view_for(event["part_id"])+"_onset"][pitch-PITCH_MIN]
        time = float(clock(event["start_beat"]))
        lo = max(0,round((time-1.4)/DT))
        hi = min(len(onset),round((time+1.4)/DT))
        local = onset[lo:hi]
        if not len(local): continue
        # Ignore pitches with no meaningful attack in the broad phrase area.
        scale = max(float(np.percentile(local, 93)), .025)
        if float(np.max(local)) < .04: continue
        samples = np.interp((time+SHIFTS)/DT, np.arange(len(onset)), onset,
                            left=0,right=0)
        scores += np.minimum(samples / scale, 2.5)
        good += 1
    if good:
        scores /= np.sqrt(good)
    return scores, good


def choose_offsets(evidence: np.ndarray, counts: np.ndarray) -> np.ndarray:
    # A flat/invisible bar inherits nearby measured tempo rather than making
    # up an offset. At a real orchestral handoff, allow a sharper correction.
    width = .22
    base = -.20*(SHIFTS/width)**2
    dp = evidence[0] + base
    back = []
    for i in range(1, evidence.shape[0]):
        boundary = i+1 in (7, 12, 15, 29, 36, 46, 50, 54)
        smooth = .26 if boundary else .48
        delta = SHIFTS[:,None]-SHIFTS[None,:]
        transition = -smooth*(delta/.2)**2
        prior = -.09*(SHIFTS/.45)**2
        matrix = dp[None,:]+transition
        arg = np.argmax(matrix,axis=1)
        dp = evidence[i] + prior + matrix[np.arange(len(arg)),arg]
        back.append(arg)
    chosen = np.empty(evidence.shape[0],int)
    chosen[-1] = int(np.argmax(dp))
    for i in range(len(chosen)-2,-1,-1): chosen[i]=back[i][chosen[i+1]]
    offsets = SHIFTS[chosen]
    # No evidence for a note should never produce a large extrapolation.
    for i in range(len(offsets)):
        if counts[i] == 0: offsets[i] *= .45
    return offsets


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds",type=int,default=SECONDS)
    parser.add_argument("--last-measure",type=int,default=LAST_MEASURE)
    parser.add_argument("--clock",type=Path,default=HERE/"prokofiev3-orchestra-clock.json")
    parser.add_argument("--output",type=Path,default=HERE/"prokofiev3-orchestra-phrase-offsets.json")
    args=parser.parse_args()
    if digest(AUDIO)!=EXPECTED_AUDIO_SHA256 or digest(MXL)!=EXPECTED_SCORE_SHA256:
        raise ValueError("Source fingerprint changed")
    record = json.loads(args.clock.read_text())
    clock = PchipInterpolator(*zip(*record["beat_time"]))
    events = parse_xml(MXL,max_measure=args.last_measure)
    features = extract_features(load_stereo(AUDIO, FFMPEG,
                                            args.seconds), tuning_cents=record["tuning_cents"])
    rows=[]; counts=[]; raw=[]
    for measure in range(1,args.last_measure+1):
        score,count=measure_evidence(events,measure,clock,features)
        rows.append(score);counts.append(count)
        raw.append(float(SHIFTS[np.argmax(score)]) if count else 0)
    evidence=np.array(rows); counts=np.array(counts)
    offsets=choose_offsets(evidence,counts)
    output={"source_audio_sha256":digest(AUDIO),"source_score_sha256":digest(MXL),
            "method":"global multiscale score/audio DTW + measure-level pitch/rhythm onset evidence",
            "tuning_cents":record["tuning_cents"],"measure_offsets":[
                {"measure":m,"offset_seconds":round(float(offsets[m-1]),3),
                 "unregularized_best_seconds":round(raw[m-1],3),
                 "evidence_notes":int(counts[m-1]),
                 "evidence_gain":round(float(np.max(evidence[m-1])-evidence[m-1,np.argmin(abs(SHIFTS))]),3)}
                for m in range(1,args.last_measure+1)]}
    path=args.output
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n")
    for item in output["measure_offsets"]:
        print(f"m{item['measure']:02d} offset {item['offset_seconds']:+.2f} "
              f"raw {item['unregularized_best_seconds']:+.2f} "
              f"evidence {item['evidence_notes']:2d} gain {item['evidence_gain']:.2f}")


if __name__ == "__main__": main()
