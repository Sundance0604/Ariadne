"""Optional, isolated ChordGNN input and inference experiment; never activates data."""
from pathlib import Path
import argparse
import math
import os
import sys
from fractions import Fraction as F

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.chordgnn_experiment import (
    DATA, EXPERIMENT, fingerprint, prepare, read, recording_time,
    resolve_meters, source_keys, verify_protected, write,
)


def make_score(case):
    """Build a concert score, retaining exact rational times and source IDs."""
    import partitura as pt
    from music21.pitch import Pitch

    start = F(case['context_start_q'])
    measures = resolve_meters(case['measures'])
    times = [F(n[k]) - start for n in case['notes'] for k in ('start_q', 'end_q')]
    times += [F(m[k]) - start for m in case['measures'] for k in ('start_q', 'end_q')]
    divisions = math.lcm(*(q.denominator for q in times))
    if divisions > 10000:
        raise ValueError('Excessive source divisions: inspect before graph construction')
    parts = []
    witnesses = {}
    for part_id in sorted({n['part_id'] for n in case['notes']}):
        notes = [n for n in case['notes'] if n['part_id'] == part_id]
        part = pt.score.Part(part_id, part_name=notes[0]['label'], quarter_duration=divisions)
        source_part=notes[0]['source_event_id'].split('-xml-')[0]
        previous_meter = None
        previous_key = None
        for m in measures:
            a, b = (int((F(m[k]) - start) * divisions) for k in ('start_q', 'end_q'))
            part.add(pt.score.Measure(number=m['local_number']), a, b)
            if m['time_signature'] != previous_meter:
                beats, beat_type = map(int, m['time_signature'].split('/'))
                part.add(pt.score.TimeSignature(beats, beat_type), a)
                previous_meter = m['time_signature']
            signature=source_keys(str(ROOT/m['source']))[(source_part,m['source_sequence'])]
            fifths=signature['concert_fifths']
            if fifths is None:raise ValueError('Missing explicit/inherited XML key signature')
            key=(fifths,signature['mode'])
            if key!=previous_key:
                part.add(pt.score.KeySignature(fifths=fifths,mode=signature['mode']),a)
                previous_key=key
        for note in notes:
            concert = note.get('concert_pitch')
            if concert:
                step, octave, alter = concert['step'], concert['octave'], concert['alter']
            else:
                p = Pitch(note['encoded_name'].replace('b', '-')).transpose(note['transpose'])
                step, octave, alter = p.step, p.octave, p.accidental.alter if p.accidental else 0
            pitch = Pitch()
            pitch.step, pitch.octave = step, octave
            pitch.accidental = alter
            if pitch.ps != note['ps']:
                raise ValueError('Concert pitch mismatch: ' + note['id'])
            if int(alter) != alter:
                raise ValueError('Microtonal spelling is outside model vocabulary')
            voice = int(note.get('voice') or 1)
            identity = note['id']
            pn = pt.score.Note(step=step, octave=octave, alter=int(alter),
                               id=identity, voice=voice, staff=int(note.get('staff') or 1))
            a, b = (int((F(note[k]) - start) * divisions) for k in ('start_q', 'end_q'))
            if b <= a:
                raise ValueError('Non-positive note: ' + identity)
            part.add(pn, a, b)
            witnesses[identity] = {'source_event_ids': note['source_event_ids'],
                'pitch': int(note['ps']), 'onset_div': a, 'duration_div': b-a,
                'source_xml_path': note['source_xml_path']}
        parts.append(part)
    return pt.score.Score(parts), divisions, witnesses


def graph_probe(case, upstream):
    import numpy as np
    import torch
    sys.path.insert(0, str(upstream))
    from chordgnn.utils import hetero_graph_from_note_array, select_features

    score, divisions, witnesses = make_score(case)
    arr = score.note_array(include_time_signature=True, include_pitch_spelling=True)
    if len(arr) != len(case['notes']):
        raise ValueError('Note count changed in score adapter')
    # Partitura prefixes IDs with its part index in merged arrays.
    expected = sorted((w['onset_div'], w['duration_div'], w['pitch']) for w in witnesses.values())
    actual = sorted((int(n['onset_div']), int(n['duration_div']), int(n['pitch'])) for n in arr)
    if actual != expected:
        raise ValueError('Pitch or rational timing changed in score adapter')
    _, edges = hetero_graph_from_note_array(arr.copy())
    features = select_features(arr, 'chord')
    if features.shape != (len(arr), 83) or not np.isfinite(features).all():
        raise ValueError('Invalid ChordGNN input features')
    resolved = resolve_meters(case['measures'])
    meter_by_div = [(int((F(m['start_q'])-F(case['context_start_q']))*divisions),
                     int((F(m['end_q'])-F(case['context_start_q']))*divisions),m) for m in resolved]
    expected_downbeat=[]
    for note in arr:
        a, b, measure=next(x for x in meter_by_div if x[0]<=note['onset_div']<x[1])
        beats, beat_type=map(int,measure['time_signature'].split('/'))
        if (note['ts_beats'],note['ts_beat_type'])!=(beats,beat_type):
            raise ValueError('Meter lost in adapter')
        expected_downbeat.append(note['onset_div']==a)
    # The upstream descriptor computes onset_beat modulo the current numerator.
    # With changing meters this can disagree with actual XML bar beginnings.
    modulo_disagreements=int(np.count_nonzero(features[:,-4]!=expected_downbeat))
    # Model output has one row per unique attack, not per video frame or bar.
    onset_divs = np.unique(arr['onset_div'])
    alignment = read(DATA / 'alignment.json')
    target_onsets = []
    for div in onset_divs:
        q = F(case['context_start_q']) + F(int(div), divisions)
        if not F(case['start_q']) <= q < F(case['end_q']):
            continue
        active = [n for n in case['notes'] if F(n['start_q']) <= q < F(n['end_q'])]
        measure = next(m for m in case['measures'] if F(m['start_q']) <= q < F(m['end_q']))
        target_onsets.append({'score_q': str(q), 'onset_div': int(div),
            'measure_id': measure['measure_id'], 'bar': measure['local_number'],
            'recording_seconds': recording_time(alignment, q, case['movement']),
            'sounding_pitch_classes': sorted({int(n['ps']) % 12 for n in active}),
            'bass_midi': min(int(n['ps']) for n in active),
            'active_source_event_ids': [i for n in active for i in n['source_event_ids']]})
    report = {'id': case['id'], 'status': 'graph_features_passed_no_prediction',
        'divisions': divisions, 'notes': len(arr), 'parts': len(score.parts),
        'all_context_onsets': len(onset_divs), 'target_onsets': len(target_onsets),
        'feature_dimensions': list(features.shape),
        'edge_counts': {str(int(k)): int((edges[2] == k).sum()) for k in np.unique(edges[2])},
        'pitch_and_rational_time_multiset_exact': True,
        'feature_values_finite': True, 'torch_version': torch.__version__,
        'xml_meter_checks_passed':True,
        'resolved_meters':resolved,
        'upstream_first_bar_feature_disagreements':modulo_disagreements,
        'model_predictions': None, 'onsets': target_onsets,
        'witnesses': witnesses,
        'limitations': ['Input validation is not a harmonic accuracy test.',
            'Notation durations exclude acoustic pedal and reverberation.',
            'Existing synchronization is reused and is not independently revalidated.']}
    return report, score


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=EXPERIMENT)
    parser.add_argument('--upstream', type=Path, default=ROOT / '.tools/chordgnn/upstream')
    parser.add_argument('--prepare', action='store_true')
    args = parser.parse_args()
    if args.prepare:
        prepare(args.output)
    os.environ.setdefault('MPLCONFIGDIR', str(ROOT / '.tools/chordgnn/matplotlib'))
    manifest = read(args.output / 'manifest.json')
    verify_protected(manifest['protected_inputs'])
    reports = []
    for case in manifest['cases']:
        source = args.output / 'inputs' / (case['id'] + '.json')
        result, _ = graph_probe(read(source), args.upstream)
        result['input'] = fingerprint(source)
        write(args.output / 'graphs' / (case['id'] + '.json'), result)
        reports.append({k: v for k, v in result.items() if k not in ('witnesses', 'onsets','resolved_meters')})
        print(case['id'], result['notes'], result['target_onsets'], result['edge_counts'], flush=True)
    verify_protected(manifest['protected_inputs'])
    manifest.update(graph_checks=reports)
    if 'analysisgnn' not in manifest:manifest['status']='graph_features_passed_no_prediction'
    write(args.output / 'manifest.json', manifest)


if __name__ == '__main__':
    main()
