"""Build a whole-movement *coarse* score/recording clock for Prokofiev 3/I.

The XML has 276 measures and seven tempo marks. This score clock is only a
search prior: it must not be mistaken for verified individual piano attacks,
orchestral attacks, or played note releases.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd
from synctoolbox.dtw.mrmsdtw import sync_via_mrmsdtw
from synctoolbox.dtw.utils import make_path_strictly_monotonic
from synctoolbox.feature.csv_tools import df_to_pitch_features, df_to_pitch_onset_features
from synctoolbox.feature.chroma import pitch_to_chroma, quantize_chroma
from synctoolbox.feature.dlnco import pitch_onset_features_to_DLNCO
from synctoolbox.feature.pitch import audio_to_pitch_features
from synctoolbox.feature.pitch_onset import audio_to_pitch_onset_features
from synctoolbox.feature.utils import estimate_tuning

from prepare_preview import (AUDIO, EXPECTED_AUDIO_SHA256, EXPECTED_SCORE_SHA256,
                             FFMPEG, HERE, MXL, digest, parse_xml)

RATE = 22050
FEATURE_RATE = 25
# The track is 587.08 s, but the final chord has fallen to the recording's
# noise floor by about 580 s. Excluding the trailing silence prevents the
# forced DTW endpoint from stretching the last notated measure by 8 seconds.
SECONDS = 580.0
LAST_MEASURE = 276
# The first field is the beat at the start of the printed measure.
TEMPI = ((0, 78), (40, 146), (400, 176), (556, 92),
         (672, 156), (940, 144), (1040, 156))


def score_seconds(beat: float) -> float:
    value = 0.0
    for i, (start, bpm) in enumerate(TEMPI):
        stop = TEMPI[i + 1][0] if i + 1 < len(TEMPI) else beat
        if beat <= start:
            break
        value += (min(beat, stop) - start) * 60 / bpm
        if beat < stop:
            break
    return value


def annotation(events: list[dict]) -> pd.DataFrame:
    rows = []
    for event in events:
        start = score_seconds(event['start_beat'])
        end = score_seconds(event['end_beat'])
        part = event['part_id']
        weight = (100 if part == 'P14' else
                  87 if part in ('P4', 'P15', 'P16') else
                  75 if part in ('P2', 'P3', 'P17') else 57)
        rows.append({'start': start, 'duration': max(.04, end - start),
                     'pitch': event['midi_pitch'], 'velocity': weight,
                     'instrument': event['part_name']})
    return pd.DataFrame(rows)


def decode() -> np.ndarray:
    command = [str(FFMPEG), '-hide_banner', '-loglevel', 'error', '-nostdin',
               '-i', str(AUDIO), '-t', str(SECONDS), '-ac', '1', '-ar',
               str(RATE), '-f', 'f32le', 'pipe:1']
    return np.frombuffer(subprocess.run(command, check=True,
                                       capture_output=True).stdout, '<f4').copy()


def main() -> None:
    if digest(AUDIO) != EXPECTED_AUDIO_SHA256 or digest(MXL) != EXPECTED_SCORE_SHA256:
        raise ValueError('Recording or MusicXML fingerprint changed')
    events = parse_xml(MXL, max_measure=LAST_MEASURE)
    score = annotation(events)
    audio = decode()
    tuning = estimate_tuning(audio[:RATE * 75], RATE)
    print(f'audio_samples={len(audio)} score_events={len(events)} '
          f'score_nominal_seconds={score_seconds(LAST_MEASURE * 4):.2f} '
          f'tuning_cents={tuning:.2f}', flush=True)
    audio_pitch = audio_to_pitch_features(f_audio=audio, Fs=RATE,
                                         tuning_offset=tuning,
                                         feature_rate=FEATURE_RATE, verbose=False)
    audio_chroma = quantize_chroma(pitch_to_chroma(f_pitch=audio_pitch))
    del audio_pitch
    audio_peaks = audio_to_pitch_onset_features(f_audio=audio, Fs=RATE,
                                               tuning_offset=tuning, verbose=False)
    audio_onset = pitch_onset_features_to_DLNCO(
        f_peaks=audio_peaks, feature_rate=FEATURE_RATE,
        feature_sequence_length=audio_chroma.shape[1], visualize=False)
    del audio_peaks, audio
    print(f'audio_features={audio_chroma.shape[1]}', flush=True)
    score_pitch = df_to_pitch_features(score, feature_rate=FEATURE_RATE)
    score_chroma = quantize_chroma(pitch_to_chroma(f_pitch=score_pitch))
    del score_pitch
    score_peaks = df_to_pitch_onset_features(score)
    score_onset = pitch_onset_features_to_DLNCO(
        f_peaks=score_peaks, feature_rate=FEATURE_RATE,
        feature_sequence_length=score_chroma.shape[1], visualize=False)
    del score_peaks
    print(f'score_features={score_chroma.shape[1]}', flush=True)
    path = sync_via_mrmsdtw(
        f_chroma1=audio_chroma, f_chroma2=score_chroma,
        f_onset1=audio_onset, f_onset2=score_onset,
        input_feature_rate=FEATURE_RATE,
        step_weights=np.array([1.5, 1.5, 2.0]),
        threshold_rec=10**6, verbose=False)
    path = make_path_strictly_monotonic(path)
    score_times = path[1] / FEATURE_RATE
    performance_times = path[0] / FEATURE_RATE
    beats = np.arange(0, LAST_MEASURE * 4 + .001, .25)
    nominal = np.array([score_seconds(float(beat)) for beat in beats])
    mapped = np.interp(nominal, score_times, performance_times)
    if np.any(np.diff(mapped) < -1e-8):
        raise RuntimeError('Nonmonotone score/audio map')
    record = {
        'source_audio_sha256': digest(AUDIO),
        'source_score_sha256': digest(MXL),
        'method': 'Sync Toolbox 1.4.2 MrMsDTW, chroma+DLNCO, all 7 XML tempo cues',
        'sample_rate': RATE, 'feature_rate': FEATURE_RATE,
        'tuning_cents': float(tuning), 'score_events': len(events),
        'score_measures': LAST_MEASURE, 'path_points': int(path.shape[1]),
        'beat_time': [[round(float(beat), 5), round(float(time), 5)]
                      for beat, time in zip(beats, mapped)],
    }
    output = HERE / 'prokofiev3-full-global-clock.json'
    output.write_text(json.dumps(record, ensure_ascii=False,
                                 separators=(',', ':')) + '\n')
    print('wrote', output, 'endpoint', round(float(mapped[-1]), 3), flush=True)


if __name__ == '__main__':
    main()
