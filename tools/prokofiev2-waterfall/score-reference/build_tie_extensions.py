"""Recover the notated duration of tied notes omitted from onset matching."""

from bisect import bisect_right
from collections import defaultdict
from fractions import Fraction
import gzip
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
score = json.loads((HERE / "score-notes.json").read_text())
clock = json.loads((HERE / "full-alignment-work/global-clock.json").read_text())
with gzip.open(HERE / "score-events.json.gz", "rt") as stream:
    events = json.load(stream)["events"]

measure_starts = score["measure_starts_quarters"]
grid_q = clock["quarter_grid"]
grid_t = clock["audio_seconds_grid"]


def time_at(quarter):
    i = max(0, min(len(grid_q) - 2, bisect_right(grid_q, quarter) - 1))
    fraction = (quarter - grid_q[i]) / (grid_q[i + 1] - grid_q[i])
    return grid_t[i] + fraction * (grid_t[i + 1] - grid_t[i])


by_line = defaultdict(list)
for event in events:
    if event.get("kind") != "pitched" or not event.get("concert_pitch"):
        continue
    measure = event.get("measure_sequence")
    if not isinstance(measure, int) or not 1 <= measure <= len(measure_starts):
        continue
    onset = Fraction(str(measure_starts[measure - 1])) + Fraction(event["onset_q"])
    duration = Fraction(event["duration_q"])
    pitch = round(float(event["concert_pitch"]["ps"]))
    by_line[(event["part_id"], event.get("voice_id"), pitch)].append(
        (onset, onset + duration, event))

for line in by_line.values():
    line.sort(key=lambda item: (item[0], item[1]))

score_by_id = {note["id"]: note for note in score["notes"]}
extensions = {}
for line in by_line.values():
    for i, (onset, end, event) in enumerate(line):
        if "start" not in event.get("tie", []) or event["id"] not in score_by_id:
            continue
        current_end = end
        for next_onset, next_end, next_event in line[i + 1:]:
            if next_onset > current_end + Fraction(1, 100):
                break
            if abs(next_onset - current_end) <= Fraction(1, 100) and \
                    "stop" in next_event.get("tie", []):
                current_end = next_end
                if "start" not in next_event.get("tie", []):
                    break
        original = score_by_id[event["id"]]["end_q"]
        if float(current_end) > original + .001:
            extensions[event["id"]] = {
                "end_q": round(float(current_end), 5),
                "extra_seconds": round(time_at(float(current_end)) -
                                       time_at(original), 4),
            }

target = HERE / "score-tie-extensions.json"
target.write_text(json.dumps(extensions, ensure_ascii=False,
                             separators=(",", ":")) + "\n")
print(f"{len(extensions)} tied notes extended: {target}")

voice_map = {event["id"]: {"voice": event.get("voice"),
                           "staff": event.get("staff")}
             for event in events if event.get("kind") == "pitched"}
for note in score["notes"]:
    voice_map[note["id"]]["start_q"] = note["start_q"]
voice_target = HERE / "score-voice-map.json"
voice_target.write_text(json.dumps(voice_map, ensure_ascii=False,
                                   separators=(",", ":")) + "\n")
print(f"{len(voice_map)} score note voices/staves mapped: {voice_target}")
