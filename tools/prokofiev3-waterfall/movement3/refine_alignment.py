"""Apply evidence-backed corrections without changing the original alignment.

All times below are recording seconds.  The finished video has a five-second
title lead, so video timestamps in the review brief are converted here.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import json

import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks

from align_notes import HERE, PianoEvidence, trim_piano_releases
from audio_evidence import OrchestraEvidence


BASE = HERE / "alignment.json"
OUTPUT = HERE / "alignment-reviewed.json"
REPORT = HERE / "alignment-reviewed-qa.json"


def move(note, when, source):
    old = note["audio_start"]
    delta = float(when - old)
    note["audio_start"] = round(float(when), 4)
    note["audio_end"] = round(max(when + .05, note["audio_end"] + delta), 4)
    note["clock_shift_seconds"] = round(note["clock_shift_seconds"] + delta, 4)
    note["onset_source"] = source
    return delta


def roles(notes):
    muted = defaultdict(int)
    promoted = []
    bassoon = {
        "p3iii-m20-P5-2995", "p3iii-m20-P5-2996", "p3iii-m20-P5-2997",
        "p3iii-m20-P5-2998", "p3iii-m21-P5-2999", "p3iii-m21-P5-3000",
        "p3iii-m21-P5-3001",
    }
    for note in notes:
        if note["family"] == "piano":
            continue
        video_time = note["audio_start"] + 5
        video_end = note["audio_end"] + 5
        first_quiet = video_time < 26 and video_end > 19
        second_quiet = video_time < 54 and video_end > 45
        if first_quiet or second_quiet:
            if note["visual_role"] == "lead":
                muted["19-26" if first_quiet else "45-54"] += 1
            note["visual_role"] = "support"
            note["musical_role"] = "orchestra_support"
            note.pop("role_confidence", None)
        if note["score_id"] in bassoon:
            note["visual_role"] = "lead"
            note["musical_role"] = "orchestra_melody"
            note["role_confidence"] = 1.0
            promoted.append(note["score_id"])
    assert set(promoted) == bassoon
    return dict(muted), promoted


def orchestra_consensus(notes, evidence):
    """Resolve contradictory independent part attacks at one written beat.

    The old aligner gave each instrument a broad independent search window.
    For simultaneous score events we instead ask the multi-part recording for
    the strongest common attack.  This corrects late false peaks without
    flattening single-instrument phrasing or applying a guessed fixed offset.
    """
    groups = defaultdict(list)
    for note in notes:
        if (159 <= note["audio_start"] < 214 and
                note["part_id"] != "P14" and note["visual_role"] == "lead"):
            groups[note["score_start_beat"]].append(note)
    changed = []
    anchors = []
    for beat, members in sorted(groups.items()):
        by_part = defaultdict(list)
        for note in members:
            by_part[note["part_id"]].append(note)
        if len(by_part) < 2:
            continue
        attacks = [float(np.median([n["audio_start"] for n in part_notes]))
                   for part_notes in by_part.values()]
        spread = max(attacks) - min(attacks)
        if spread < (.16 if len(by_part) == 2 else .18) or spread > .95:
            continue
        grid = np.arange(min(attacks) - .05, max(attacks) + .051, .01)
        curves = []
        for part, part_notes in by_part.items():
            curve = evidence.sample(part, [n["midi_pitch"] for n in part_notes], grid)
            reference = max(float(np.percentile(curve, 90)), .03)
            curves.append(np.clip(curve / reference, 0, 2.0))
        combined = gaussian_filter1d(np.sum(curves, axis=0), 1)
        best = int(np.argmax(combined))
        target = float(grid[best])
        if combined[best] < 1.65:
            continue
        if len(by_part) == 2 and min(float(curve[best]) for curve in curves) < .55:
            continue
        moved = 0
        for part_notes in by_part.values():
            old = float(np.median([n["audio_start"] for n in part_notes]))
            if abs(old - target) <= .09:
                continue
            for note in part_notes:
                move(note, target + note["audio_start"] - old,
                     "ensemble_multi_part_attack")
                moved += 1
        if moved:
            anchors.append((beat, target))
            changed.append({"score_beat": beat, "video_time": round(target + 5, 3),
                            "old_spread_ms": round(spread * 1000), "notes": moved})

    # A local reference from verified ensemble attacks can also identify late
    # solo notes, but move those only when their own pitch has an attack nearby.
    solo = []
    if len(anchors) >= 4:
        beats, times = map(np.asarray, zip(*anchors))
        if np.all(np.diff(times) > 0):
            clock = PchipInterpolator(beats, times, extrapolate=False)
            for beat, members in sorted(groups.items()):
                if beat <= beats[0] or beat >= beats[-1]:
                    continue
                if any(abs(beat - a) < 1e-5 for a in beats):
                    continue
                target = float(clock(beat))
                if not np.isfinite(target):
                    continue
                for note in members:
                    old = note["audio_start"]
                    if not .22 < old - target < .72:
                        continue
                    grid = np.arange(target - .14, target + .141, .01)
                    curve = evidence.sample(note["part_id"],
                                            [note["midi_pitch"]], grid)
                    signal = float(np.max(curve))
                    if signal < .12:
                        continue
                    onset = float(grid[int(np.argmax(curve))])
                    move(note, onset, "local_ensemble_clock_pitch_attack")
                    solo.append(note["score_id"])
    return changed, solo


def orchestra_part_residuals(notes, evidence):
    """Restore clearly staggered attacks after multi-part consensus.

    A shared orchestral beat is a useful timing anchor, but it must not erase
    a separate instrument's audible entrance. Only move a part when its own
    pitch attack is strong, the current time has little matching evidence,
    and the candidate remains between adjacent written attacks in that part.
    """
    groups = defaultdict(list)
    for note in notes:
        if (159 <= note["audio_start"] < 214 and
                note["visual_role"] == "lead" and
                note.get("onset_source") == "ensemble_multi_part_attack"):
            groups[(note["part_id"], note["score_start_beat"])].append(note)
    part_order = defaultdict(list)
    for (part, beat), members in groups.items():
        part_order[part].append((beat, float(np.median(
            [n["audio_start"] for n in members]))))
    for ordered in part_order.values():
        ordered.sort()
    changed = []
    for (part, beat), members in sorted(groups.items(), key=lambda item: item[0][1]):
        old = float(np.median([n["audio_start"] for n in members]))
        grid = np.arange(old - .35, old + .351, .01)
        curve = evidence.sample(part, [n["midi_pitch"] for n in members], grid)
        current = float(np.max(curve[np.abs(grid - old) <= .045]))
        peaks, _ = find_peaks(curve, prominence=.02, distance=5)
        candidates = [i for i in peaks
                      if .085 < abs(grid[i] - old) < .31 and
                      curve[i] >= .18 and
                      curve[i] > max(.12, 2.0 * current)]
        if not candidates:
            continue
        picked = max(candidates, key=lambda i:
                     float(curve[i]) - .15 * abs(grid[i] - old) / .35)
        target = float(grid[picked])
        ordered = part_order[part]
        index = next(i for i, (b, _) in enumerate(ordered) if b == beat)
        if ((index and target <= ordered[index - 1][1] + .03) or
                (index + 1 < len(ordered) and
                 target >= ordered[index + 1][1] - .03)):
            continue
        for note in members:
            move(note, target + note["audio_start"] - old,
                 "reviewed_part_pitch_attack")
        changed.append({"score_beat": beat, "part": part,
                        "old_video_time": round(old + 5, 3),
                        "new_video_time": round(target + 5, 3),
                        "onset_strength": round(float(curve[picked]), 3)})
    return changed


def piano_left_hand(notes, score, piano):
    """Repair overfilled XML bars using separated-piano attacks.

    In bars 200-221 the XML places many left-hand basses after right-hand
    chords, although the recording plays them before.  First find each bass
    by *matching pitch* in the separated piano, then align the associated
    written left-hand run to detected attacks in that same bar.  Unknown
    attacks are interpolated only between verified detections.
    """
    source = {event["score_id"]: event for event in score["notes"]}
    by_bar_voice = defaultdict(list)
    right_by_bar = defaultdict(list)
    for note in notes:
        if note["part_id"] != "P14":
            continue
        event = source[note["score_id"]]
        if event["staff"] == "2" and event["voice"] in ("5", "6"):
            by_bar_voice[(note["measure"], event["voice"])].append(note)
        if event["staff"] == "1":
            right_by_bar[note["measure"]].append(note)
    used = set()
    reserved = defaultdict(list)
    for note in notes:
        if note["part_id"] == "P14" and note["onset_source"] == "separated_piano_transkun":
            reserved[note["midi_pitch"]].append((
                note["audio_start"], note["score_id"], note["score_start_beat"]))
    direct = []
    warped = []
    for bar, voice in ((bar, voice) for bar in range(200, 222) for voice in ("5", "6")):
        series = sorted(by_bar_voice[(bar, voice)],
                        key=lambda n:(n["score_start_beat"], n["midi_pitch"]))
        low = [n for n in series if n["midi_pitch"] <= 43 and
               303 <= n["audio_start"] <= 368]
        if not low:
            continue
        bass = low[0]
        old = bass["audio_start"]
        choices = [d for d in piano.detections[bass["midi_pitch"]]
                   if old - 2.25 <= d["start"] <= old - .42 and
                   d["velocity"] >= 45 and d["end"] - d["start"] >= .035]
        if not choices:
            continue
        detected = min(choices, key=lambda d: abs(d["start"] - (old - 1.25)))
        bass_time = float(detected["start"])
        next_right = right_by_bar.get(bar + 1, [])
        if next_right:
            stop = min(n["audio_start"] for n in next_right) - .25
        else:
            stop = bass_time + 2.3
        stop = min(max(stop, bass_time + .5), bass_time + 3.1)
        first_beat = bass["score_start_beat"]
        last_beat = max(n["score_start_beat"] for n in series)
        if last_beat <= first_beat:
            move(bass, bass_time, "separated_piano_low_bass_review")
            direct.append((bass["score_id"], round(bass_time + 5, 3)))
            for note in series:
                if note is bass or note["score_start_beat"] != first_beat:
                    continue
                same_pitch_attack = any(abs(d["start"] - bass_time) <= .055
                                        for d in piano.detections[note["midi_pitch"]])
                if same_pitch_attack:
                    move(note, bass_time, "separated_piano_low_octave_review")
                    direct.append((note["score_id"], round(bass_time + 5, 3)))
            continue
        anchors = [(first_beat, bass_time, bass)]
        used.add((bass["midi_pitch"], round(bass_time, 3)))
        previous = bass_time
        previous_beat = first_beat
        for note in series:
            if note is bass or note["score_start_beat"] < first_beat:
                continue
            fraction = (note["score_start_beat"] - first_beat) / (last_beat - first_beat)
            guess = bass_time + fraction * (stop - bass_time)
            candidates = [d for d in piano.detections[note["midi_pitch"]]
                          if abs(d["start"] - guess) <= .34 and
                          d["start"] >= previous + (
                              -.04 if note["score_start_beat"] == previous_beat else .025) and
                          d["velocity"] >= 32 and
                          (note["midi_pitch"], round(d["start"], 3)) not in used and
                          not any(other_id != note["score_id"] and
                                  source[other_id]["measure"] != bar and (
                                  abs(other_time - d["start"]) < .055 or
                                  (other_beat < note["score_start_beat"] and
                                   other_time >= d["start"] - .02) or
                                  (other_beat > note["score_start_beat"] and
                                   other_time <= d["start"] + .02))
                                  for other_time, other_id, other_beat in
                                  reserved[note["midi_pitch"]])]
            if not candidates:
                continue
            selected = min(candidates, key=lambda d: abs(d["start"] - guess))
            when = float(selected["start"])
            anchors.append((note["score_start_beat"], when, note))
            previous = when
            previous_beat = note["score_start_beat"]
            used.add((note["midi_pitch"], round(when, 3)))
        # Require at least two pitch-confirmed attacks before changing the run.
        if len(anchors) < 2 and len(series) > 1:
            continue
        for _, when, note in anchors:
            if abs(note["audio_start"] - when) > .035:
                move(note, when, "separated_piano_left_hand_attack")
                direct.append((note["score_id"], round(when + 5, 3)))
        ordered = sorted(anchors, key=lambda x:x[0])
        distinct = []
        for beat, when, note in ordered:
            if distinct and beat <= distinct[-1][0]:
                continue
            distinct.append((beat, when))
        if len(distinct) < 2 or not np.all(np.diff([x[1] for x in distinct]) > 0):
            continue
        warp = PchipInterpolator(*zip(*distinct), extrapolate=False)
        for note in series:
            beat = note["score_start_beat"]
            if any(abs(beat - item[0]) < 1e-7 for item in distinct):
                continue
            if not distinct[0][0] < beat < distinct[-1][0]:
                continue
            when = float(warp(beat))
            conflict = any(other_id != note["score_id"] and
                           source[other_id]["measure"] != bar and (
                           abs(other_time - when) < .16 or
                           (other_beat < beat and other_time >= when - .02) or
                           (other_beat > beat and other_time <= when + .02))
                           for other_time, other_id, other_beat in
                           reserved[note["midi_pitch"]])
            if np.isfinite(when) and not conflict and abs(note["audio_start"] - when) > .12:
                move(note, when, "left_hand_between_detected_attacks")
                warped.append(note["score_id"])
    return direct, warped


def main():
    baseline = json.loads(BASE.read_text())
    score = json.loads((HERE / "score-events.json").read_text())
    notes = deepcopy(baseline["notes"])
    piano = PianoEvidence(score)
    orchestra = OrchestraEvidence(score)
    muted, promoted = roles(notes)
    ensemble, solo = orchestra_consensus(notes, orchestra)
    part_residuals = orchestra_part_residuals(notes, orchestra)
    direct, warped = piano_left_hand(notes, score, piano)
    # The original note ends were already bounded by decay and hand capacity.
    # Run the overlap bound again after moving the left-hand attacks.
    releases = trim_piano_releases(notes)
    notes.sort(key=lambda n:(n["audio_start"], n["midi_pitch"], n["part_id"]))
    baseline["title"] += " — reviewed"
    baseline["notes"] = notes
    baseline["review_source"] = str(BASE)
    OUTPUT.write_text(json.dumps(baseline, ensure_ascii=False, separators=(",", ":")))
    qa = {"role_demotions":muted,"bassoon_promoted":len(promoted),
          "ensemble_groups_corrected":len(ensemble),
          "ensemble_notes_corrected":sum(row["notes"] for row in ensemble),
          "solo_pitch_corrections":len(solo),
          "part_residual_attacks_corrected":len(part_residuals),
          "left_hand_direct_attacks":len(direct),
          "left_hand_interpolated":len(warped),
          "release_trim_after_review":releases,
          "ensemble_groups":ensemble,"part_residual_attacks":part_residuals,
          "left_hand_direct":direct,
          "left_hand_interpolated_ids":warped,"solo_ids":solo}
    REPORT.write_text(json.dumps(qa, ensure_ascii=False, indent=2))
    print(json.dumps({k:v for k,v in qa.items() if not isinstance(v,list)},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
