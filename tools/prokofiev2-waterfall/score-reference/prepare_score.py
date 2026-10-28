"""Prepare a conservative score clock and note events for Prokofiev 2/I.

The supplied MusicXML has several overfilled string measures. The shared
measure duration is selected from the majority of parts and overflow notes
are excluded from the visualization reference, with every exclusion logged.
"""

from collections import Counter
from fractions import Fraction
import gzip
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
PART_FAMILIES = {
    **{f"P{i}": "woodwind" for i in range(1, 5)},
    **{f"P{i}": "brass" for i in range(5, 9)},
    **{f"P{i}": "percussion" for i in range(9, 14)},
    "P14": "ossia",
    "P15": "piano",
    **{f"P{i}": "strings" for i in range(16, 21)},
}


def main():
    archived = HERE / "score-events.json.gz"
    if archived.exists():
        with gzip.open(archived, "rt") as stream:
            source = json.load(stream)
    else:
        source = json.loads((HERE / "score-events.json").read_text())
    measures = source["measures"]
    starts = {}
    lengths = {}
    current = Fraction(0)
    warnings = []
    for row in measures:
        counts = row["part_duration_counts"]
        # Seventeen or more of twenty parts agree on the actual bar length.
        common = max(counts, key=lambda duration: (counts[duration], -float(Fraction(duration))))
        duration = Fraction(common)
        starts[row["measure_id"]] = current
        lengths[row["measure_id"]] = duration
        if row["duration_q"] != common:
            warnings.append({"measure": row["sequence"], "issue": "overfilled_part",
                             "durations": counts, "used_quarters": common})
        current += duration

    parts = {part["id"]: part["name"] for part in source["parts"]}
    notes = []
    exclusions = Counter()
    for event in source["events"]:
        family = PART_FAMILIES.get(event["part_id"], "other")
        if family in {"ossia", "percussion"}:
            exclusions[family] += 1
            continue
        if not event["analysis_eligible"] or not event["concert_pitch"]:
            exclusions["not_sounding_note"] += 1
            continue
        if "stop" in event.get("tie", []):
            exclusions["tie_continuation"] += 1
            continue
        onset = Fraction(event["onset_q"])
        duration = Fraction(event["duration_q"])
        bar_length = lengths[event["measure_id"]]
        if onset >= bar_length:
            exclusions["beyond_bar"] += 1
            continue
        if onset + duration > bar_length:
            exclusions["end_clipped_to_bar"] += 1
            duration = bar_length - onset
        if duration <= 0:
            continue
        pitch = round(float(event["concert_pitch"]["ps"]))
        if not 0 <= pitch <= 127:
            exclusions["pitch_out_of_range"] += 1
            continue
        start_q = starts[event["measure_id"]] + onset
        notes.append({"id": event["id"], "part_id": event["part_id"],
                      "part_name": parts[event["part_id"]], "family": family,
                      "pitch": pitch, "start_q": float(start_q),
                      "end_q": float(start_q + duration),
                      "measure": event["measure_sequence"]})
    notes.sort(key=lambda n: (n["start_q"], n["family"], n["pitch"]))
    document = {"source_mxl": "source/piano-concerto-no2-op16-s-prokofiev.mxl",
                "movement": 1, "measure_count": len(measures),
                "duration_quarters": float(current),
                "measure_starts_quarters": [float(starts[m["measure_id"]]) for m in measures],
                "measure_lengths_quarters": [float(lengths[m["measure_id"]]) for m in measures],
                "notes": notes, "warnings": warnings,
                "excluded_event_counts": dict(exclusions),
                "status": "source-faithful candidate; overfilled bars repaired by majority clock"}
    target = HERE / "score-notes.json"
    target.write_text(json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(json.dumps({"notes": len(notes), "quarter_length": float(current),
                      "warnings": len(warnings), "exclusions": dict(exclusions),
                      "family_counts": dict(Counter(n["family"] for n in notes))},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
