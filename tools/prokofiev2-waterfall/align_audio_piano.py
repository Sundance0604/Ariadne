"""Use recorded piano attacks and releases as the piano waterfall source.

The XML is retained only for orchestration and for auditing / assigning hands.
No score-time fallback is allowed for piano notes in the replacement interval.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pretty_midi

HERE = Path(__file__).resolve().parent
BASE = HERE / "data/orchestra-reference-v8.timeline.json"
VOICE = HERE / "data/score-voice-map.json"


def read_model_notes(path: Path, audio_offset: float):
    midi = pretty_midi.PrettyMIDI(str(path))
    notes = sorted((note for instrument in midi.instruments for note in instrument.notes
                    if not instrument.is_drum), key=lambda note: (note.start, note.pitch))
    return [{"pitch": note.pitch, "start": audio_offset + note.start,
             "end": audio_offset + note.end, "velocity": note.velocity}
            for note in notes if 21 <= note.pitch <= 108 and note.end > note.start]


def associate_score(model, score, voice_map):
    """Audit pitch correspondence without moving the measured audio times."""
    by_pitch = defaultdict(list)
    for note in score:
        by_pitch[note["midi_pitch"]].append(note)
    for sequence in by_pitch.values():
        sequence.sort(key=lambda note: note["audio_start"])
    used = set()
    for index, note in enumerate(model):
        choices = [(abs(source["audio_start"] - note["start"]), source)
                   for source in by_pitch[note["pitch"]]
                   if id(source) not in used and
                   abs(source["audio_start"] - note["start"]) <= .8]
        if choices:
            delta, source = min(choices, key=lambda pair: pair[0])
            used.add(id(source))
            note["score_id"] = source["score_id"]
            first_id = source["score_id"].split(",")[0]
            note["hand"] = voice_map.get(first_id, {}).get("staff", 1)
            note["score_delta"] = delta
        else:
            note["score_id"] = f"P15-audio-{index:06d}"
            note["hand"] = 2 if note["pitch"] < 60 else 1
            note["score_delta"] = None


def two_hand_reachable(active):
    """A chord may cross the XML staff boundary, so test both hands jointly."""
    pitches = sorted(note["pitch"] for note in active)
    for split in range(max(0, len(pitches) - 5), min(5, len(pitches)) + 1):
        left, right = pitches[:split], pitches[split:]
        if (not left or left[-1] - left[0] <= 18) and (
                not right or right[-1] - right[0] <= 18):
            return True
    return False


def trim_unplayable(model):
    """Same-key reattacks require the preceding key hold to end first.

    Preserve measured releases otherwise. XML staff labels are not reliable
    hand assignments for cross-staff and wide chordal writing.
    """
    cuts = Counter()
    by_pitch = defaultdict(list)
    for note in model:
        by_pitch[note["pitch"]].append(note)
    for sequence in by_pitch.values():
        sequence.sort(key=lambda note: note["start"])
        for left, right in zip(sequence, sequence[1:]):
            if left["end"] > right["start"] - .006:
                left["end"] = max(left["start"] + .035, right["start"] - .006)
                cuts["same_key"] += 1
    return cuts


def audit(model):
    violations = Counter()
    for note in model:
        t = note["start"] + .001
        active = [other for other in model if other["start"] <= t < other["end"]]
        if not two_hand_reachable(active):
            violations["unreachable_two_hand_chord"] += 1
    return violations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--midi", type=Path, required=True)
    parser.add_argument("--base", type=Path, default=BASE,
                        help="Score-aligned orchestral reference timeline")
    parser.add_argument("--voice-map", type=Path, default=VOICE)
    parser.add_argument("--audio-offset", type=float, default=0.)
    parser.add_argument("--supplement-midi", type=Path)
    parser.add_argument("--supplement-offset", type=float, default=0.)
    parser.add_argument("--start", type=float, default=0.)
    parser.add_argument("--end", type=float, default=1e9)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--qa", type=Path, required=True)
    args = parser.parse_args()
    base = json.loads(args.base.read_text())
    voice_map = json.loads(args.voice_map.read_text())
    source_piano = [note for note in base["notes"]
                    if note["family"] == "piano" and
                    args.start <= note["audio_start"] < args.end]
    model = [note for note in read_model_notes(args.midi, args.audio_offset)
             if args.start <= note["start"] < args.end]
    supplemental_count = 0
    if args.supplement_midi:
        extra = read_model_notes(args.supplement_midi, args.supplement_offset)
        for note in extra:
            # A crop boundary can create spurious transients. Only retain a
            # note detected inside the crop and absent from the full pass.
            if not (max(args.start, args.supplement_offset + .5) <= note["start"] <
                    min(args.end, args.supplement_offset + 49.5)):
                continue
            if any(other["pitch"] == note["pitch"] and
                   abs(other["start"] - note["start"]) < .12 for other in model):
                continue
            if not any(other["midi_pitch"] == note["pitch"] and
                       abs(other["audio_start"] - note["start"]) < 1.2
                       for other in source_piano):
                continue
            model.append(note)
            supplemental_count += 1
        model.sort(key=lambda note: (note["start"], note["pitch"]))
    associate_score(model, source_piano, voice_map)
    cuts = trim_unplayable(model)
    violations = audit(model)
    if violations:
        raise RuntimeError(f"Unplayable model note intervals: {violations}")
    replaced = []
    for note in model:
        replaced.append({"family": "piano", "part_id": "P15", "part_name": "Piano",
                         "midi_pitch": note["pitch"],
                         "audio_start": round(note["start"], 4),
                         "audio_end": round(note["end"], 4),
                         "score_id": note["score_id"],
                         "performed_velocity": note["velocity"]})
    keep = [dict(note) for note in base["notes"]
            if note["family"] != "piano" or not
            (args.start <= note["audio_start"] < args.end)]
    combined = sorted(keep + replaced,
                      key=lambda note: (note["audio_start"], note["family"],
                                        note["midi_pitch"]))
    for index, note in enumerate(combined):
        note["event_id"] = str(index)
    result = deepcopy(base)
    result.update(title="Prokofiev 2/I audio-transcribed piano v9",
                  notes=combined,
                  piano_alignment_method="separated-piano audio transcription; no score-time fallback")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.qa.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False,
                                      separators=(",", ":")) + "\n")
    matched = [note["score_delta"] for note in model
               if note["score_delta"] is not None]
    report = {"model": str(args.midi), "audio_offset": args.audio_offset,
              "replacement_interval": [args.start, args.end],
              "old_piano_notes": len(source_piano),
              "audio_transcribed_piano_notes": len(model),
              "supplemental_audio_detections": supplemental_count,
              "score_time_fallback_notes": 0,
              "score_pitch_matches_within_800ms": len(matched),
              "median_match_shift_seconds": (round(float(np.median(matched)), 4)
                                             if matched else None),
              "physical_release_cuts": cuts,
              "physical_violations": violations,
              "result": str(args.output)}
    args.qa.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
