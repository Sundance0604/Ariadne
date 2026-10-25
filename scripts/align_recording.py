"""Offline full-recording alignment against auxiliary MIDI; outputs remain unreviewed."""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault('NUMBA_CACHE_DIR', str(ROOT / '.tools/numba-cache'))
os.environ.setdefault('MPLCONFIGDIR', str(ROOT / '.tools/matplotlib'))
os.environ.setdefault('MPLBACKEND', 'Agg')
import numpy as np
import scipy.signal
import soundfile as sf
from synctoolbox.feature.pitch import audio_to_pitch_features
from synctoolbox.feature.pitch_onset import audio_to_pitch_onset_features
from synctoolbox.feature.utils import estimate_tuning
from synctoolbox.feature.chroma import pitch_to_chroma, quantize_chroma
from synctoolbox.feature.dlnco import pitch_onset_features_to_DLNCO
from synctoolbox.dtw.mrmsdtw import sync_via_mrmsdtw, sync_via_mrmsdtw_with_anchors
from synctoolbox.dtw.utils import make_path_strictly_monotonic
from midi_score import read_midi, symbolic_features
from audio_io import audio_info, read_audio


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + '.tmp')
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    pending.replace(path)


def log(message):
    print(time.strftime('%H:%M:%S') + ' ' + message, flush=True)


def reduce_path(path):
    # Use the midpoint of all audio frames assigned to one score frame, while
    # retaining the raw DTW path separately. No linear full-duration allocation.
    score, first, counts = np.unique(path[1], return_index=True, return_counts=True)
    audio = np.array([np.median(path[0, i:i+n]) for i, n in zip(first, counts)])
    return score, audio


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audio', type=Path)
    parser.add_argument('--midi', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'alignment.json')
    parser.add_argument('--anchors', type=Path)
    parser.add_argument('--feature-rate', type=int, default=50, choices=[50])
    args = parser.parse_args()
    default_resource = ROOT / 'resource/ravel left hand piano concerto'
    args.audio = (args.audio or next(default_resource.glob('*.mp3'), None))
    args.midi = (args.midi or next(default_resource.glob('*.mid'), None))
    if args.audio is None:
        parser.error('No MP3 input found. Supply --audio.')
    if args.midi is None:
        parser.error('This test command requires an auxiliary MIDI. The PDF OMR-only full-score route is not implemented yet.')
    args.audio, args.midi, args.output = args.audio.resolve(), args.midi.resolve(), args.output.resolve()
    if not all(p.is_relative_to(ROOT) for p in [args.audio,args.midi,args.output]):
        parser.error('Inputs and output must be within this local project directory.')
    if args.output.exists():
        previous = json.loads(args.output.read_text(encoding='utf-8'))
        if previous.get('human_anchors') or any(m.get('review_status') in {'verified','corrected'}
                                               for m in previous.get('measures', [])):
            raise SystemExit('Existing human review is protected. Use a new --output path.')
    start_time = time.perf_counter()
    audio_hash, midi_hash = digest(args.audio), digest(args.midi)
    rate, fs = args.feature_rate, 22050
    cache = ROOT / '.tools/features' / (audio_hash[:12] + '-' + midi_hash[:12] + '-v1')
    cache.mkdir(parents=True, exist_ok=True)
    log('Parsing original MIDI tracks and tempo changes')
    score = read_midi(args.midi)
    report_directory = ROOT / 'reports' if args.output == ROOT / 'alignment.json' else args.output.parent / 'reports'
    save_json(report_directory / 'midi-parse.json', {
        k: v for k, v in score.items() if k not in {'notes', 'measures'}})
    log(f"Parsed {len(score['notes'])} note intervals; {len(score['measures'])} inferred bars")
    info = audio_info(args.audio)
    audio_duration = info.frames / info.samplerate
    if (cache / 'features.npz').exists():
        log('Loading fingerprinted feature cache')
        with np.load(cache / 'features.npz') as data:
            audio_chroma, audio_onset = data['audio_chroma'], data['audio_onset']
            score_chroma, score_onset = data['score_chroma'], data['score_onset']
            tuning = int(data['tuning'])
    else:
        log('Decoding full audio locally and resampling to 22050 Hz')
        wave, sample_rate = read_audio(args.audio, dtype='float32', always_2d=True)
        wave = wave.mean(axis=1)
        if sample_rate != fs:
            import math
            g = math.gcd(sample_rate, fs)
            wave = scipy.signal.resample_poly(wave, fs // g, sample_rate // g)
        # Tuning sample spans the recording; do not build a large full-file STFT.
        clips = [wave[int(t*fs):int((t+8)*fs)] for t in np.linspace(10, audio_duration-20, 8)]
        tuning = int(estimate_tuning(np.concatenate(clips), fs))
        log(f'Estimated tuning offset: {tuning} cents; extracting full-recording pitch features')
        pitch = audio_to_pitch_features(wave, Fs=fs, feature_rate=rate, tuning_offset=tuning)
        audio_chroma = quantize_chroma(pitch_to_chroma(pitch))
        del pitch
        log('Extracting full-recording onset features')
        peaks = audio_to_pitch_onset_features(wave, Fs=fs, tuning_offset=tuning)
        audio_onset = pitch_onset_features_to_DLNCO(peaks,
            feature_sequence_length=audio_chroma.shape[1], feature_rate=rate)
        del peaks, wave
        pitch, peaks, selected = symbolic_features(score['notes'], score['duration'], rate)
        score_chroma = quantize_chroma(pitch_to_chroma(pitch))
        score_onset = pitch_onset_features_to_DLNCO(peaks,
            feature_sequence_length=score_chroma.shape[1], feature_rate=rate)
        del pitch, peaks
        np.savez_compressed(cache / 'features.npz', audio_chroma=audio_chroma,
            audio_onset=audio_onset, score_chroma=score_chroma,
            score_onset=score_onset, tuning=tuning)
        log(f'Feature cache saved; {len(selected)} pitched note intervals used')
    parameters = dict(input_feature_rate=rate, step_weights=np.array([1.5, 1.5, 2.0]),
                      threshold_rec=10**6, verbose=False)
    anchors = []
    anchor_history = []
    if args.anchors:
        document = json.loads(args.anchors.read_text(encoding='utf-8'))
        if document['audio_sha256'] != audio_hash or document['score_sha256'] != midi_hash:
            raise ValueError('Anchor input fingerprints do not match the recording and MIDI')
        anchors = document['anchors']
        anchor_history = document.get('history', [])
        pairs = [(float(a['audio_seconds']), float(a['midi_seconds'])) for a in anchors]
        if any(not (0 < a < audio_duration and 0 < s < score['duration']) for a,s in pairs):
            raise ValueError('Anchor times must be inside both timelines')
        if any(a2 <= a1 or s2 <= s1 for (a1,s1),(a2,s2) in zip(pairs,pairs[1:])):
            raise ValueError('Anchor pairs must increase on both timelines')
        parameters['anchor_pairs'] = pairs
    log('Running full-recording multiscale DTW with chroma + DLNCO')
    align = sync_via_mrmsdtw_with_anchors if anchors else sync_via_mrmsdtw
    path = align(f_chroma1=audio_chroma, f_chroma2=score_chroma,
                 f_onset1=audio_onset, f_onset2=score_onset, **parameters)
    raw_path_file = args.output.with_suffix('.path.npz')
    np.savez_compressed(raw_path_file, path=path, feature_rate=rate)
    strict = make_path_strictly_monotonic(path)
    score_frames, audio_frames = reduce_path(path)
    def recording_at(midi_seconds):
        for anchor in anchors:
            if abs(anchor['midi_seconds']-midi_seconds)<1e-8:
                return float(anchor['audio_seconds'])
        return min(audio_duration, max(0.0, float(np.interp(midi_seconds * rate, score_frames, audio_frames) / rate)))
    log('Running chroma-only comparison to locate algorithm disagreement')
    baseline = align(f_chroma1=audio_chroma, f_chroma2=score_chroma, **parameters)
    base_score, base_audio = reduce_path(baseline)
    measures = []
    for original in score['measures']:
        measure = dict(original)
        a, b = recording_at(measure['midi_start_seconds']), recording_at(measure['midi_end_seconds'])
        measure.update(start_seconds=a, end_seconds=b,
            review_status='unreviewed', source='midi_auxiliary_mrmsdtw',
            pdf_mapping_status='missing', quality_metrics={})
        base = float(np.interp(measure['midi_start_seconds'] * rate, base_score, base_audio) / rate)
        measure['quality_metrics']['chroma_only_start_disagreement_seconds'] = abs(a-base)
        if b <= a:
            measure['flags'].append('collapsed_or_reversed_interval')
        if abs(a-base) > 2:
            measure['flags'].append('feature_variant_disagreement_over_2s')
        if (b-a) > 30:
            measure['flags'].append('long_interval_check_cadenza_or_fermata')
        if measure['flags']:
            measure['review_status'] = 'needs_review'
        if any(a.get('measure_id')==measure['measure_id'] for a in anchors):
            measure['review_status']='corrected'
        measures.append(measure)
    markers = [{**m, 'audio_seconds': recording_at(m['midi_seconds']),
                'review_status': 'unreviewed'} for m in score['markers']]
    map_points = [{'midi_seconds': float(s/rate), 'audio_seconds': float(a/rate)}
                  for s,a in zip(score_frames[::5], audio_frames[::5])]
    map_points.append({'midi_seconds':score['duration'],'audio_seconds':recording_at(score['duration'])})
    for anchor in anchors:
        map_points.append({'midi_seconds':anchor['midi_seconds'],'audio_seconds':anchor['audio_seconds']})
    map_points=sorted({p['midi_seconds']:p for p in map_points}.values(),key=lambda p:p['midi_seconds'])
    result = {'format_version': '1.0.0', 'created_at': datetime.now(timezone(timedelta(hours=8))).isoformat(),
        'status': 'algorithmic_alignment_needs_review', 'source_type': 'user_midi_auxiliary',
        'pdf_omr_used': False, 'audio': {'path': args.audio.relative_to(ROOT).as_posix(),
            'sha256': audio_hash, 'duration_seconds': audio_duration},
        'symbolic_reference': {'path': args.midi.relative_to(ROOT).as_posix(),
            'sha256': midi_hash, 'duration_seconds': score['duration']},
        'algorithm': {'name': 'Sync Toolbox MrMsDTW', 'version': version('synctoolbox'),
            'feature_rate_hz': rate, 'sample_rate_hz': fs, 'tuning_offset_cents': tuning,
            'features': ['quantized_chroma', 'DLNCO'], 'step_weights': [1.5,1.5,2.0],
            'threshold_rec': 10**6, 'pitch_range': [21,108],
            'drum_channels_excluded': True, 'sustain_and_pitchbend_modeled': False,
            'path_reduction': 'median audio frame per score frame; raw path retained'},
        'runtime': {'python': sys.version, 'executable': sys.executable,
            'packages': {k: version(k) for k in ['synctoolbox','numpy','scipy','numba','librosa','mido','soundfile']},
            'elapsed_seconds': time.perf_counter()-start_time},
        'quality': {'raw_path_points': path.shape[1], 'strict_path_points': strict.shape[1],
            'monotone_path': bool(np.all(np.diff(path,axis=1)>=0)),
            'full_feature_endpoints': bool(np.array_equal(path[:,0],[0,0]) and
                np.array_equal(path[:,-1],[audio_chroma.shape[1]-1,score_chroma.shape[1]-1])),
            'feature_shapes': [list(audio_chroma.shape),list(score_chroma.shape)],
            'flag_counts': dict(Counter(f for m in measures for f in m['flags'])),
            'warning': 'Variant agreement is diagnostic, not an independently calibrated accuracy probability.'},
        'raw_path': raw_path_file.relative_to(ROOT).as_posix(),
        'human_anchors': anchors, 'measures': measures, 'rehearsal_markers': markers,
        'time_map': map_points, 'correction_history': anchor_history,
        'limitations': ['MIDI-inferred bars and numbering require PDF validation.',
            'Global DTW endpoints are forced and may include leading/trailing silence.',
            'No human listening verification or calibrated confidence.',
            'PDF OMR-only input route is not completed by this auxiliary MIDI run.']}
    save_json(args.output,result)
    runtime_path = ROOT/'reports/alignment-runtime.json' if args.output.resolve()==ROOT/'alignment.json' else args.output.with_suffix('.runtime.json')
    save_json(runtime_path, result['runtime'])
    log(f"Saved {args.output}; {len(measures)} bars; flags {result['quality']['flag_counts']}")


if __name__ == '__main__':
    main()
