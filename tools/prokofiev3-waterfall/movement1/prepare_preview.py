"""Prepare a score-led, audio-warped 30-second Prokofiev 3/I orchestral preview.

This is a trial adapter, not the Prokofiev 2 piano-transcription pipeline. It
keeps the XML parts and uses local spectral evidence to warp the opening score
clock. The orchestral foreground selections below are intentionally explicit
and auditable before any whole-movement automation is attempted.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET

import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.ndimage import gaussian_filter1d
from scipy.signal import stft


HERE = Path(__file__).resolve().parent
TOOLS = HERE.parents[1]
PACKAGE = TOOLS / "prokofiev2-waterfall"
sys.path.insert(0, str(PACKAGE))
from build_render_plan import compile_look  # noqa: E402

MXL = Path(os.environ.get(
    "PROK3_SCORE_PATH",
    str(HERE / "inputs/score.mxl")))
EXPECTED_SCORE_SHA256 = "efec61153d497dd8b16dc5589c188d518f2703becee4cf51e9e4bbb29608a8f7"
AUDIO = Path(os.environ.get(
    "PROK3_AUDIO_PATH",
    str(HERE / "inputs/audio.mp3")))
EXPECTED_AUDIO_SHA256 = "55b26a3b8e26090f97a1248f1fab020c1096f1a42b10652520d95afbb7db00d1"
FFMPEG = Path(os.environ.get(
    "PROK3_FFMPEG",
    shutil.which("ffmpeg") or "ffmpeg"))
PART_FAMILY = {
    "P1": "woodwind", "P2": "woodwind", "P3": "woodwind",
    "P4": "woodwind", "P5": "woodwind", "P6": "brass",
    "P7": "brass", "P8": "brass", "P14": "piano",
    "P15": "strings", "P16": "strings", "P17": "strings",
    "P18": "strings", "P19": "strings",
}
STEPS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
DT = 0.04

# (score beat, sounding MIDI pitch, audio search window). The first phrase's
# score pitches can be checked directly in the MP3; the windows distinguish
# repeated pitches/harmonics. Every anchor is re-detected from audio on a run.
ANCHOR_WINDOWS = [
    (16, 64, 14.3, 15.4), (17, 69, 15.6, 16.5),
    (17.5, 71, 16.0, 16.9), (18, 72, 16.5, 17.2),
    (18.5, 74, 17.0, 17.8), (19, 76, 17.5, 18.3),
    (19.5, 77, 18.0, 18.7), (20, 79, 17.9, 18.3),
    (21, 81, 19.0, 20.0), (22, 82, 20.0, 21.0),
    (23, 83, 21.4, 22.7), (24, 84, 22.7, 23.5),
    (25, 91, 24.4, 25.2), (25.5, 89, 25.1, 25.8),
    (26, 96, 25.5, 26.4), (27, 93, 26.3, 27.1),
    (28, 91, 27.3, 28.3), (29, 86, 28.5, 29.5),
    (30, 84, 29.8, 30.8), (30.5, 86, 30.5, 31.2),
    (31, 84, 31.0, 31.7), (31.5, 89, 31.5, 32.2),
    (32, 91, 32.0, 32.6), (33, 89, 33.2, 33.9),
    (33.5, 88, 33.6, 34.3), (34, 86, 34.2, 35.2),
    (35, 88, 35.6, 36.5), (36, 88, 36.95, 37.35),
    (37.5, 89, 38.4, 38.7), (38, 86, 39.0, 39.4),
    (39.5, 88, 40.9, 41.3), (40, 84, 41.5, 41.9),
    (44, 62, 42.8, 43.05), (48, 69, 44.68, 44.95),
]


def digest(path: Path) -> str:
    h = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def parse_xml(path: Path, max_measure: int = 18) -> list[dict]:
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("score.xml"))
    names = {part.get("id"): part.findtext("part-name")
             for part in root.find("part-list").findall("score-part")}
    events = []
    for part in root.findall("part"):
        part_id = part.get("id")
        if part_id not in PART_FAMILY:
            continue  # pitched percussion is not a keyboard lane
        beat_base = 0.0
        divisions = 480
        chromatic_shift = 0
        for measure_index, measure in enumerate(part.findall("measure"), 1):
            if measure_index > max_measure:
                break
            attributes = measure.find("attributes")
            if attributes is not None:
                if attributes.findtext("divisions"):
                    divisions = int(attributes.findtext("divisions"))
                transpose = attributes.find("transpose")
                if transpose is not None:
                    chromatic_shift = (int(transpose.findtext("chromatic", "0"))
                                       + 12 * int(transpose.findtext("octave-change", "0")))
            cursor = 0
            last_onset = 0
            for item in measure:
                if item.tag == "backup":
                    cursor -= int(item.findtext("duration", "0"))
                elif item.tag == "forward":
                    cursor += int(item.findtext("duration", "0"))
                elif item.tag == "note":
                    duration = int(item.findtext("duration", "0"))
                    if item.find("chord") is None:
                        last_onset = cursor
                    pitch = item.find("pitch")
                    if (pitch is not None and item.findtext("notehead") != "none"
                            and item.get("print-object") != "no"):
                        midi = (12 * (int(pitch.findtext("octave")) + 1)
                                + STEPS[pitch.findtext("step")]
                                + int(pitch.findtext("alter", "0")) + chromatic_shift)
                        if 21 <= midi <= 108:
                            start_beat = beat_base + last_onset / divisions
                            end_beat = start_beat + duration / divisions
                            events.append({"part_id": part_id, "part_name": names[part_id],
                                           "family": PART_FAMILY[part_id],
                                           "measure": measure_index, "midi_pitch": midi,
                                           "start_beat": start_beat, "end_beat": end_beat,
                                           "tie_start": any(x.get("type") == "start"
                                                            for x in item.findall("tie")),
                                           "tie_stop": any(x.get("type") == "stop"
                                                           for x in item.findall("tie"))})
                    if item.find("chord") is None:
                        cursor += duration
            beat_base += 4  # verified: opening measures are 4/4
    return merge_ties(events)


def merge_ties(events: list[dict]) -> list[dict]:
    """Join XML cross-bar continuations rather than creating a new attack."""
    active = {}
    out = []
    for event in sorted(events, key=lambda e: (e["start_beat"], e["part_id"], e["midi_pitch"])):
        key = (event["part_id"], event["midi_pitch"])
        previous = active.get(key)
        if (event["tie_stop"] and previous is not None
                and abs(previous["end_beat"] - event["start_beat"]) < 1e-6):
            previous["end_beat"] = event["end_beat"]
            if not event["tie_start"]:
                active.pop(key, None)
        else:
            out.append(event)
            if event["tie_start"]:
                active[key] = event
    return out


def nominal_time(beat: float) -> float:
    # Tempo markings in the XML: Andante quarter=78, Allegro at measure 11=146.
    return min(beat, 40) * 60 / 78 + max(0, beat - 40) * 60 / 146


def audio_salience(path: Path, ffmpeg: Path, seconds: float = 60) -> np.ndarray:
    command = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-i", str(path),
               "-t", str(seconds), "-ac", "1", "-ar", "11025", "-f", "f32le", "pipe:1"]
    decoded = subprocess.run(command, capture_output=True, check=True)
    samples = np.frombuffer(decoded.stdout, dtype="<f4")
    rate = 11025
    _, stft_times, spectrum = stft(samples, fs=rate, nperseg=2048,
                                   noverlap=2048 - 441, boundary="zeros")
    magnitude = np.abs(spectrum)
    frequency_step = rate / 2048
    activations = []
    for midi in range(48, 101):
        frequency = 440 * 2 ** ((midi - 69) / 12)
        index = round(frequency / frequency_step)
        fundamental = magnitude[max(0, index - 1):index + 2].max(axis=0)
        harmonic_index = round(2 * frequency / frequency_step)
        harmonic = magnitude[harmonic_index - 1:harmonic_index + 2].max(axis=0)
        activations.append(fundamental + .23 * harmonic)
    matrix = np.array(activations, dtype=np.float32).T
    matrix = np.log1p(matrix * 150)
    matrix /= np.maximum(matrix.max(axis=1, keepdims=True), .01)
    return matrix[:round(seconds / DT) + 1]


def score_salience(events: list[dict], seconds: float = 48) -> np.ndarray:
    count = round(seconds / DT) + 1
    matrix = np.zeros((count, 53), np.float32)
    for event in events:
        midi = event["midi_pitch"]
        if not 48 <= midi <= 100:
            continue
        part = event["part_id"]
        weight = (1.15 if part == "P14" else 1.0 if part == "P4" else
                  .85 if part == "P15" else .33 if part == "P16" else
                  .28 if part == "P2" else .10)
        lo = max(0, round(nominal_time(event["start_beat"]) / DT))
        hi = min(count, round(nominal_time(event["end_beat"]) / DT))
        if hi > lo:
            matrix[lo:hi, midi - 48] += weight
    matrix = gaussian_filter1d(matrix, sigma=1, axis=0)
    matrix /= np.maximum(np.linalg.norm(matrix, axis=1, keepdims=True), .01)
    return matrix


def align_clock(score: np.ndarray, audio: np.ndarray) -> tuple[np.ndarray, dict]:
    """Constrained local DTW with a nominal-tempo prior and smoothed warp."""
    n, m = score.shape[0], audio.shape[0]
    cost = np.full((n, m), np.inf, np.float32)
    step = np.zeros((n, m), np.int8)
    # Avoid a spurious long zero-score path at the opening; both inputs start at 0.
    cost[0, 0] = 0
    width = round(10.0 / DT)
    for i in range(1, n):
        center = i
        for j in range(max(1, center - width), min(m, center + width + 1)):
            dot = float(score[i] @ audio[j])
            norm = float(np.linalg.norm(audio[j]))
            mismatch = 1 - dot / max(norm, .01)
            prior = .001 * ((j - center) * DT) ** 2
            options = (cost[i - 1, j - 1],
                       cost[i - 1, j] + .12,
                       cost[i, j - 1] + .12)
            choice = int(np.argmin(options))
            cost[i, j] = mismatch + prior + options[choice]
            step[i, j] = choice
    endpoint = min(range(max(1, n - width), min(m, n + width + 1)),
                   key=lambda j: float(cost[n - 1, j]) + .006 * abs(j - n))
    groups = defaultdict(list)
    i, j = n - 1, endpoint
    while i > 0 and j > 0:
        groups[i].append(j)
        choice = step[i, j]
        if choice == 0:
            i -= 1; j -= 1
        elif choice == 1:
            i -= 1
        else:
            j -= 1
    groups[0].append(0)
    indices = np.array(sorted(groups))
    values = np.array([np.median(groups[k]) for k in indices])
    mapped = np.interp(np.arange(n), indices, values) * DT
    mapped = gaussian_filter1d(mapped, sigma=2)
    mapped = np.maximum.accumulate(mapped)
    mapped[0] = 0
    qa = {"dtw_cost_per_step": round(float(cost[n - 1, endpoint] / n), 4),
          "anchors_seconds": [[round(t, 2), round(float(np.interp(t / DT, np.arange(n), mapped)), 2)]
                               for t in (0, 4, 8, 12, 16, 20, 24, 28, 32)]}
    return mapped, qa


def detected_melody_anchors(path: Path, ffmpeg: Path) -> tuple[list[tuple[float, float]], list[dict]]:
    """Locate distinct score-pitch attacks in this recording; reject weak fits."""
    command = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-i", str(path),
               "-t", "45", "-ac", "1", "-ar", "22050", "-f", "f32le", "pipe:1"]
    decoded = subprocess.run(command, capture_output=True, check=True)
    samples = np.frombuffer(decoded.stdout, dtype="<f4")
    rate, fft_size, hop = 22050, 2048, 220
    frequencies, times, spectrum = stft(samples, fs=rate, nperseg=fft_size,
                                        noverlap=fft_size - hop)
    magnitude = np.abs(spectrum)
    curves = {}
    anchors = []
    detail = []
    for beat, pitch, lo, hi in ANCHOR_WINDOWS:
        if pitch not in curves:
            hz = 440 * 2 ** ((pitch - 69) / 12)
            bin_index = int(np.argmin(np.abs(frequencies - hz)))
            energy = gaussian_filter1d(magnitude[bin_index - 1:bin_index + 2].max(axis=0), 2)
            curves[pitch] = np.maximum(0, energy - np.roll(energy, 8))
        novelty = curves[pitch]
        candidates = np.where((times >= lo) & (times < hi))[0]
        index = candidates[int(np.argmax(novelty[candidates]))]
        strength = float(novelty[index] / max(novelty.max(), 1e-12))
        if strength < .08:
            raise ValueError(f"No convincing score-pitch attack near beat {beat}, pitch {pitch}")
        second = float(times[index])
        anchors.append((beat, second))
        detail.append({"beat": beat, "pitch": pitch, "audio_seconds": round(second, 3),
                       "relative_attack_strength": round(strength, 3)})
    if any(right[1] <= left[1] for left, right in zip(anchors, anchors[1:])):
        raise ValueError("Detected melodic attacks are out of score order")
    return anchors, detail


def refined_time(beat: float, coarse_warp: np.ndarray,
                 melody_map: PchipInterpolator, anchors: list[tuple[float, float]]) -> float:
    if beat < anchors[0][0]:
        coarse = float(np.interp(nominal_time(beat) / DT,
                                 np.arange(len(coarse_warp)), coarse_warp))
        join = float(np.interp(nominal_time(anchors[0][0]) / DT,
                               np.arange(len(coarse_warp)), coarse_warp))
        return opening_time_correction(coarse) + (anchors[0][1] - join) * min(1, beat / 16)
    if beat <= anchors[-1][0]:
        return float(melody_map(beat))
    # XML marks Allegro at bar 11. Beyond the last verified attack we use its
    # score tempo only for the remaining few seconds of this review clip.
    return anchors[-1][1] + (beat - anchors[-1][0]) * 60 / 146


def role_for(event: dict) -> tuple[str, str | None]:
    measure, part = event["measure"], event["part_id"]
    # First six bars: solo clarinet. Bar 7: first violins/flutes take the
    # melody, second violins play voiced harmonic pillars. Other layers are
    # visual support, including basses, so the foreground stays legible.
    if measure <= 7 and part == "P4":
        return "lead", "#f5d883"
    if (7 <= measure <= 11 or 13 <= measure <= 14) and part == "P15":
        return "lead", "#8ce5e0"
    if (7 <= measure <= 11 or 13 <= measure <= 14) and part == "P16":
        return "lead", "#a9b8ff"
    if measure == 12 and part == "P16":
        return "lead", "#8ce5e0"
    if measure == 12 and part == "P17":
        return "lead", "#a9b8ff"
    return "support", None


def opening_time_correction(time: float) -> float:
    """Refine five clearly audible clarinet attacks measured from this MP3."""
    knots = np.array([0, .5345, 1.0269, 1.5687, 2.2992, 3.2441, 4.3])
    offsets = np.array([0, -.18, -.17, -.19, -.04, -.11, 0])
    return time + float(np.interp(time, knots, offsets))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mxl", type=Path, default=MXL)
    parser.add_argument("--audio", type=Path, default=AUDIO)
    parser.add_argument("--ffmpeg", type=Path, default=FFMPEG)
    parser.add_argument("--output", type=Path, default=HERE / "preview-15-45.timeline.json")
    args = parser.parse_args()
    audio_sha256 = digest(args.audio)
    if audio_sha256 != EXPECTED_AUDIO_SHA256:
        raise ValueError("The melodic attack windows belong to the supplied Lang Lang/Rattle MP3 only")
    score_sha256 = digest(args.mxl)
    if score_sha256 != EXPECTED_SCORE_SHA256:
        raise ValueError("The melodic attack windows belong to the supplied MusicXML only")
    events = parse_xml(args.mxl)
    score = score_salience(events)
    audio = audio_salience(args.audio, args.ffmpeg)
    warp, qa = align_clock(score, audio)
    anchors, anchor_qa = detected_melody_anchors(args.audio, args.ffmpeg)
    melody_map = PchipInterpolator(*zip(*anchors))
    violin_unisons = {(e["start_beat"], e["midi_pitch"])
                      for e in events if e["part_id"] == "P15"}
    clarinet_unisons = {(e["start_beat"], e["midi_pitch"])
                        for e in events if e["part_id"] == "P4"}
    section = compile_look({"look": "glass", "density": .28, "speed": .62,
                            "piano_low": "#ead39f", "piano_high": "#b4dada",
                            "keyboard": "#b5afb0", "horizon": "#d3ccbf",
                            "appearance_overrides": {"background_motif_opacity": 0.0,
                                                     "orchestra_base_alpha": .34,
                                                     "orchestra_lead_alpha": .92,
                                                     "orchestra_emitter_scale": .30,
                                                     "orchestra_neutral_color": "#aeb6bb"}})
    notes = []
    for index, event in enumerate(events):
        unison = (event["start_beat"], event["midi_pitch"])
        if ((event["part_id"] == "P2" and unison in violin_unisons) or
                (event["part_id"] == "P16" and unison in clarinet_unisons)):
            continue  # keep one visible colour per physical key
        start = refined_time(event["start_beat"], warp, melody_map, anchors)
        end = refined_time(event["end_beat"], warp, melody_map, anchors)
        if end < 10 or start > 50 or end - start < .02:
            continue
        role, color = role_for(event)
        note = {"score_id": f"p3-m{event['measure']}-{event['part_id']}-{index}",
                "event_id": f"p3-{event['part_id']}-{index}",
                "part_id": event["part_id"], "part_name": event["part_name"],
                "family": event["family"], "midi_pitch": event["midi_pitch"],
                "audio_start": round(start, 4), "audio_end": round(end, 4),
                "visual_role": role}
        if color:
            note["accent_color"] = color
            note["accent_emitter_scale"] = (.72 if event["part_id"] == "P4" else
                                            .85 if event["part_id"] == "P15" else .58)
            note["accent_filament_attack_count"] = 2
            note["accent_filament_per_second"] = 1.3
            note["accent_light_per_second"] = 1.6
        notes.append(note)
    timeline = {"format_version": 1, "title": "Prokofiev 3/I — seconds 15–45 alignment review",
                "orchestra_pressed_keys": True,
                "sources": {"audio": {"path": str(args.audio.resolve()),
                                      "sha256": audio_sha256},
                            "score": {"path": str(args.mxl.resolve()),
                                      "sha256": score_sha256}},
                "render_interval": {"start_seconds": 15, "duration_seconds": 30,
                                    "lookahead_seconds": 5},
                "visual_sections": [{"name": "clarinet to strings",
                                     "start_seconds": 0, "end_seconds": 50,
                                     "transition_seconds": 0, "preset": section}],
                "notes": notes}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(timeline, ensure_ascii=False,
                                      separators=(",", ":")) + "\n")
    qa.update({"melody_attack_anchors": anchor_qa,
               "source_notes": len(events), "preview_notes": len(notes),
               "visible_piano_notes": sum(n["family"] == "piano" for n in notes),
               "roles": {"clarinet_melody": sum(n["part_id"] == "P4" and n["visual_role"] == "lead" for n in notes),
                         "violin_melody": sum(n["part_id"] == "P15" and n["visual_role"] == "lead" for n in notes),
                         "violin_chords": sum(n["part_id"] == "P16" and n["visual_role"] == "lead" for n in notes)}})
    (args.output.parent / f"{args.output.stem}.qa.json").write_text(
        json.dumps(qa, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(qa, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
