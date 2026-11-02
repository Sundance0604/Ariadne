"""Auditable full-score orchestral foreground classification.

The first 90 measures retain the reviewed three-minute role decisions. Later
measures use written dynamics, register, attack activity, piano density, and
phrase continuity. These are *score* role candidates; the audio evidence and
confidence audit are added by align_full.py. No background note is deleted.
"""

from __future__ import annotations

from collections import defaultdict
from math import log1p
from statistics import median
import zipfile
import xml.etree.ElementTree as ET

from align_three_minutes import orchestra_role
from prepare_preview import MXL

DYNAMIC = {'ppp': 0, 'pp': 1, 'p': 2, 'mp': 3, 'mf': 4,
           'f': 5, 'ff': 6, 'fff': 7, 'sf': 5, 'sfz': 6, 'fp': 4}
FAMILY_WEIGHT = {'P1': .04, 'P2': .11, 'P3': .10, 'P4': .09,
                 'P5': -.04, 'P6': .05, 'P7': .01, 'P8': -.08,
                 'P15': .12, 'P16': .02, 'P17': -.04,
                 'P18': -.11, 'P19': -.14}


def written_dynamics() -> dict[tuple[int, str], int]:
    with zipfile.ZipFile(MXL) as archive:
        name = next(n for n in archive.namelist()
                    if n.endswith('.xml') and not n.startswith('META-INF'))
        root = ET.fromstring(archive.read(name))
    table = {}
    for part in root.findall('part'):
        part_id = part.get('id')
        current = 3
        for measure_number, measure in enumerate(part.findall('measure'), 1):
            values = []
            for direction in measure.findall('direction'):
                dynamics = direction.find('direction-type/dynamics')
                if dynamics is not None:
                    values += [DYNAMIC[x.tag] for x in dynamics
                               if x.tag in DYNAMIC]
            if values:
                current = max(values)
            table[(measure_number, part_id)] = current
    return table


def kind_at_attack(items: list[dict]) -> str:
    pitches = sorted({item['midi_pitch'] for item in items})
    # An octave or two octave notes are still one melodic voice.
    if len(pitches) <= 1 or all((p-pitches[0]) % 12 == 0 for p in pitches):
        return 'orchestra_melody'
    return 'orchestra_chord'


def classify(events: list[dict]) -> tuple[dict[tuple[int, str], dict], list[dict]]:
    dynamics = written_dynamics()
    by_measure = defaultdict(lambda: defaultdict(list))
    for event in events:
        by_measure[event['measure']][event['part_id']].append(event)
    selected = {}
    rows = []
    previous = set()
    for measure in range(1, 277):
        parts = by_measure[measure]
        piano = parts.get('P14', [])
        piano_attacks = len({e['start_beat'] for e in piano})
        candidates = []
        for part_id, notes in parts.items():
            if part_id not in FAMILY_WEIGHT:
                continue
            attacks = len({e['start_beat'] for e in notes})
            pitch = median(e['midi_pitch'] for e in notes)
            length = median(e['end_beat']-e['start_beat'] for e in notes)
            dynamic = dynamics.get((measure, part_id), 3)
            score = (FAMILY_WEIGHT[part_id] + .23*log1p(attacks)
                     + .023*(pitch-60) + .19*(dynamic-3)
                     + .12*min(length, 2) + (.20 if part_id in previous else 0))
            candidates.append({'part': part_id, 'score': score,
                               'attacks': attacks, 'pitch': pitch,
                               'dynamic': dynamic,
                               'notes': len(notes)})
        candidates.sort(key=lambda x: x['score'], reverse=True)
        chosen = []
        if measure <= 90:
            chosen = sorted({part for part, notes in parts.items()
                             if part != 'P14' and any(orchestra_role(e)[0]=='lead'
                                                       for e in notes)})
            for part in chosen:
                selected[(measure, part)] = {'source': 'reviewed opening role',
                                             'confidence': 'reviewed'}
        elif candidates:
            strongest = candidates[0]
            # Piano-dominated bars are deliberately selective. In an
            # orchestra-led interlude, highlight the main written voice even
            # when its dynamic is soft; the harmony may also be highlighted.
            orchestra_led = piano_attacks <= 3
            threshold = -10.0 if orchestra_led else 1.46 if piano_attacks >= 10 else 1.23
            if strongest['score'] >= threshold:
                chosen = [strongest['part']]
                top_attacks = {e['start_beat'] for e in parts[strongest['part']]}
                for cand in candidates[1:]:
                    if len(chosen) >= (3 if orchestra_led else 2):
                        break
                    other = {e['start_beat'] for e in parts[cand['part']]}
                    shared = len(top_attacks & other)/max(1, min(len(top_attacks),len(other)))
                    close_score = cand['score'] >= strongest['score']-(.48 if orchestra_led else .30)
                    active_harmony = (orchestra_led and cand['attacks'] >= 2
                                      and cand['notes'] >= 2*cand['attacks']
                                      and cand['score'] >= strongest['score']-.55)
                    if (close_score and shared >= .54) or active_harmony:
                        chosen.append(cand['part'])
            for part in chosen:
                grade = next(c['score'] for c in candidates if c['part']==part)
                selected[(measure, part)] = {
                    'source': 'score dynamics/texture/continuity',
                    'confidence': 'high' if grade >= threshold+.38 else 'review',
                    'score': round(grade, 3)}
        previous = set(chosen)
        rows.append({'measure': measure, 'piano_attacks': piano_attacks,
                     'selected_parts': chosen,
                     'candidates': [{**x, 'score': round(x['score'], 3)}
                                    for x in candidates[:5]]})
    return selected, rows


def role_for(event: dict, selected: dict[tuple[int, str], dict],
             all_events_at_attack: list[dict]) -> str:
    if event['part_id'] == 'P14':
        return 'piano'
    if event['measure'] <= 90:
        # Preserve the exact reviewed opening event criteria (which can be
        # narrower than an entire measure/part).
        old_role, _, old_label = orchestra_role(event)
        if old_role != 'lead':
            return 'orchestra_support'
        return ('orchestra_chord' if 'harmony' in old_label
                else 'orchestra_melody')
    if (event['measure'], event['part_id']) not in selected:
        return 'orchestra_support'
    foreground = [item for item in all_events_at_attack
                  if (item['measure'],item['part_id']) in selected]
    if not foreground:
        return 'orchestra_support'
    highest = max(item['midi_pitch'] for item in foreground)
    # The upper melodic octave remains the melody. Notes that form other
    # pitch classes at this ensemble attack are the foreground harmony,
    # even when each instrument writes only one pitch on its own staff.
    return ('orchestra_melody' if (highest-event['midi_pitch']) % 12 == 0
            else 'orchestra_chord')
