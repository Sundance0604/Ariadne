"""Targeted score-constrained performance timing review for movement III.

The orchestra pass uses pitch appearance in the recording rather than the
largest later onset peak. The malformed piano passage uses the already cached
separated-piano transcription directly, with a score-pitch check. No source
separation or transcription is rerun.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import json

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks

from align_notes import HERE, PianoEvidence, trim_piano_releases
from audio_evidence import OrchestraEvidence
from refine_alignment import move

SOURCE = HERE / 'alignment-reviewed.json'
OUTPUT = HERE / 'alignment-performance-reviewed.json'
REPORT = HERE / 'alignment-performance-reviewed-qa.json'


def spectral_births(evidence, part, pitch, old):
    """Find first strong appearances of a pitch near its written event."""
    grid = np.arange(old - .86, old + .071, .01)
    energy = gaussian_filter1d(evidence.sample(part, [pitch], grid, 'energy'), 1.5)
    onset = gaussian_filter1d(evidence.sample(part, [pitch], grid, 'onset'), 1.0)
    peak = max(float(energy.max()), 1e-8)
    positions, _ = find_peaks(onset, prominence=max(.012, .11 * float(onset.max())), distance=8)
    found = []
    for index in positions:
        if index < 12 or index > len(grid) - 11:
            continue
        before = float(np.median(energy[index - 12:index - 4]))
        after = float(np.median(energy[index + 2:index + 11]))
        rise = (after - before) / peak
        if rise < .18 or after < .22 * peak or onset[index] < .08:
            continue
        found.append((float(grid[index]), float(rise * min(1., onset[index] / .12))))
    return found


def orchestra_appearance_alignment(notes, evidence):
    """Build a phrase clock from simultaneous new-pitch appearances.

    The older matcher often chose a louder *later* attack of a note already
    sounding. Octave harmonics of an active prior note cannot become anchors.
    A smooth phrase shift is accepted only where the target pitch is audible.
    """
    groups = defaultdict(list)
    for note in notes:
        if (note['family'] != 'piano' and note['visual_role'] == 'lead'
                and 157 <= note['audio_start'] < 214):
            groups[(note['part_id'], note['score_start_beat'])].append(note)
    births = defaultdict(list)
    for (part, beat), members in groups.items():
        old = float(np.median([n['audio_start'] for n in members]))
        candidates = []
        for pitch in sorted({n['midi_pitch'] for n in members}):
            if not 36 <= pitch <= 100:
                continue
            previous = [n for (other_part, prior_beat), prior in groups.items()
                        if other_part == part and beat - 3 <= prior_beat < beat
                        for n in prior if n['audio_end'] > old - .86]
            if any(pitch - n['midi_pitch'] in (0, 12, 19, 24) for n in previous):
                continue
            candidates.extend((when, strength, pitch) for when, strength
                              in spectral_births(evidence, part, pitch, old)
                              if .12 < old - when < .84 and strength >= .20)
        if candidates:
            when, strength, pitch = max(candidates,
                key=lambda row: row[1] + .08 * (old - row[0]) / .8)
            births[beat].append((part, old, when, strength, pitch))

    anchors = []
    for beat, rows in sorted(births.items()):
        best = None
        for i, first in enumerate(rows):
            for second in rows[i + 1:]:
                if first[0] == second[0] or abs(first[2] - second[2]) >= .13:
                    continue
                # Two instruments in an octave still provide a valid root
                # appearance, but two identical-pitch rows are one signal.
                if first[4] == second[4]:
                    continue
                pair = (first, second)
                if best is None or sum(x[3] for x in pair) > sum(x[3] for x in best):
                    best = pair
        if best:
            old = float(np.median([x[1] for x in best]))
            when = float(np.median([x[2] for x in best]))
            anchors.append((beat, when - old, [x[0] for x in best]))
        elif rows:
            strongest = max(rows, key=lambda row: row[3])
            if strongest[3] >= .52:
                anchors.append((beat, strongest[2] - strongest[1], [strongest[0]]))
    if len(anchors) < 4:
        raise RuntimeError(f'Insufficient spectral appearance anchors: {len(anchors)}')

    beats = np.asarray([a[0] for a in anchors])
    shifts = np.asarray([a[1] for a in anchors])
    changed = []
    previous_by_part = {}
    for (part, beat), members in sorted(groups.items(), key=lambda item:
                                         (item[0][0], item[0][1])):
        old = float(np.median([n['audio_start'] for n in members]))
        weights = np.exp(-.5 * ((beats - beat) / 7.5) ** 2)
        shift = float(np.sum(weights * shifts) / max(np.sum(weights), 1e-8))
        target = old + np.clip(shift, -.65, -.06)
        pitches = sorted({n['midi_pitch'] for n in members if 36 <= n['midi_pitch'] <= 100})
        candidates = [(when, quality) for pitch in pitches
                      for when, quality in spectral_births(evidence, part, pitch, old)
                      if quality >= .18 and abs(when - target) <= .38]
        previous = previous_by_part.get(part)
        if previous:
            prior_beat, prior_time = previous
            minimum = prior_time + max(.07, .18 * (beat - prior_beat))
            candidates = [row for row in candidates if row[0] >= minimum]
        if not candidates:
            previous_by_part[part] = (beat, old)
            continue
        # The first supported rise is the actual entrance; a stronger later
        # peak of the already sounding pitch is not a new score note.
        target = min(candidates, key=lambda row: row[0])[0]
        previous_by_part[part] = (beat, target)
        if abs(old - target) < .09:
            continue
        for note in members:
            move(note, target + note['audio_start'] - old, 'recorded_pitch_appearance_clock')
        changed.append({'beat': beat, 'part': part, 'old_video': round(old + 5, 3),
                        'new_video': round(target + 5, 3)})
    return anchors, changed


def piano_acoustic_start(piano, pitch, detection):
    """Correct a transcription attack using its separated-stem energy rise."""
    at = float(detection['start'])
    grid = np.arange(at - .18, at + .091, .01)
    energy = gaussian_filter1d(piano.energy(pitch, grid), 1)
    before = float(np.median(energy[:7]))
    peak = float(np.max(energy[15:]))
    if peak < max(6e-5, 2.5 * before):
        return at
    threshold = before + .18 * (peak - before)
    crossings = np.where(energy >= threshold)[0]
    if not len(crossings):
        return at
    onset = float(grid[crossings[0]] - .01)
    return max(at - .13, min(at, onset))


def piano_performance_notes(notes, piano):
    """Use the separated transcription for the malformed-score passage."""
    start, stop = 302., 389.
    originals = [n for n in notes if n['part_id'] == 'P14'
                 and start <= n['audio_start'] < stop]
    by_pitch = defaultdict(list)
    for note in originals:
        by_pitch[note['midi_pitch']].append(note)
    generated = []
    for pitch, detections in piano.detections.items():
        templates = by_pitch[pitch]
        if not templates:
            continue
        for detection in detections:
            at = float(detection['start'])
            if not start <= at < stop:
                continue
            duration = float(detection['end'] - detection['start'])
            minimum_velocity = 35 if pitch < 57 else 40
            if detection['velocity'] < minimum_velocity or duration < .04:
                continue
            template = min(templates, key=lambda n: abs(n['audio_start'] - at))
            if abs(template['audio_start'] - at) > 1.3:
                continue
            onset = piano_acoustic_start(piano, pitch, detection)
            note = deepcopy(template)
            note['score_id'] = f"{template['score_id']}-performance-{len(generated)}"
            note['event_id'] = note['score_id']
            note['audio_start'] = round(onset, 4)
            note['audio_end'] = round(max(onset + .08, float(detection['end'])), 4)
            note['clock_shift_seconds'] = round(note['clock_shift_seconds']
                                               + onset - template['audio_start'], 4)
            note['onset_source'] = 'separated_piano_performance_transcription'
            note['release_source'] = 'separated_piano_transcription_release'
            generated.append(note)
    if len(generated) < 450:
        raise RuntimeError(f'Too few score-validated piano detections: {len(generated)}')
    notes[:] = [n for n in notes if n not in originals] + generated
    return len(originals), len(generated)


def main():
    score = json.loads((HERE / 'score-events.json').read_text())
    document = json.loads(SOURCE.read_text())
    notes = deepcopy(document['notes'])
    piano = PianoEvidence(score)
    orchestra = OrchestraEvidence(score)
    anchors, orchestra_changes = orchestra_appearance_alignment(notes, orchestra)
    old_piano, new_piano = piano_performance_notes(notes, piano)
    bass = []
    for note in notes:
        if (note['part_id'] == 'P14' and note['measure'] == 145
                and note['midi_pitch'] in (33, 45)):
            candidates = [d for d in piano.detections[note['midi_pitch']]
                          if abs(d['start'] - note['audio_start']) < .08]
            if candidates:
                target = piano_acoustic_start(piano, note['midi_pitch'], candidates[0])
                if target < note['audio_start'] - .015:
                    bass.append((note['score_id'], note['audio_start'], target))
                    move(note, target, 'separated_piano_bass_acoustic_rise')
    release = trim_piano_releases(notes)
    notes.sort(key=lambda n: (n['audio_start'], n['midi_pitch'], n['part_id']))
    document['notes'] = notes
    document['review_source'] = str(SOURCE)
    document['title'] += ' — performance verified'
    OUTPUT.write_text(json.dumps(document, ensure_ascii=False, separators=(',', ':')))
    qa = {'orchestra_spectral_anchors': [
        {'beat': b, 'shift_seconds': round(s, 3), 'parts': parts}
        for b, s, parts in anchors],
          'orchestra_notes_moved': sum(len([n for n in notes if n['family'] != 'piano'
                                            and n['score_start_beat'] == row['beat']
                                            and n['part_id'] == row['part']])
                                      for row in orchestra_changes),
          'orchestra_groups_moved': len(orchestra_changes),
          'orchestra_changes': orchestra_changes,
          'piano_score_notes_replaced': old_piano,
          'piano_score_validated_detections': new_piano,
          'piano_octave_acoustic_rises': bass,
          'release_bounds': release}
    REPORT.write_text(json.dumps(qa, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in qa.items() if k not in
                      ('orchestra_changes', 'orchestra_spectral_anchors')}, indent=2))


if __name__ == '__main__':
    main()
