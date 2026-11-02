"""Cache score-pitch attack/energy evidence for the full stereo recording.

Decodes at most 60 seconds at once. The resulting compact float16 feature
chunks are analysis evidence, never an unconstrained audio transcription.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

import numpy as np

from align_opening import DT, PITCH_MAX, PITCH_MIN, RATE, extract_features
from prepare_preview import (AUDIO, EXPECTED_AUDIO_SHA256, EXPECTED_SCORE_SHA256,
                             FFMPEG, HERE, MXL, digest)

LIMIT = 580
CHUNK = 50
OUT = HERE / 'orchestra-full-features'


def stereo_window(start: int, duration: int) -> np.ndarray:
    command = [str(FFMPEG), '-hide_banner', '-loglevel', 'error', '-nostdin',
               '-ss', str(start), '-i', str(AUDIO), '-t', str(duration),
               '-ac', '2', '-ar', str(RATE), '-f', 'f32le', 'pipe:1']
    data = subprocess.run(command, capture_output=True, check=True).stdout
    return np.frombuffer(data, '<f4').reshape(-1, 2).T.copy()


def main() -> None:
    if digest(AUDIO) != EXPECTED_AUDIO_SHA256 or digest(MXL) != EXPECTED_SCORE_SHA256:
        raise ValueError('Source fingerprint changed')
    clock = json.loads((HERE/'prokofiev3-full-global-clock.json').read_text())
    OUT.mkdir(exist_ok=True)
    for start in range(0, LIMIT, CHUNK):
        end = min(start + CHUNK, LIMIT)
        output = OUT / f'features-{start:03}-{end:03}.npz'
        if output.is_file():
            print('reusing', output.name, flush=True)
            continue
        print('analyzing audio', start, end, flush=True)
        features = extract_features(stereo_window(start, end-start),
                                    tuning_cents=clock['tuning_cents'])
        chosen = {key: np.asarray(features[key], np.float16)
                  for key in ('mid_onset', 'mid_energy', 'first_onset',
                              'first_energy', 'second_onset', 'second_energy')}
        np.savez_compressed(output, **chosen)
        print('saved', output.name, 'shape', chosen['mid_onset'].shape,
              flush=True)
    manifest = {'source_audio_sha256': EXPECTED_AUDIO_SHA256,
                'source_score_sha256': EXPECTED_SCORE_SHA256,
                'limit_seconds': LIMIT, 'chunk_seconds': CHUNK,
                'sample_interval_seconds': DT,
                'pitch_min': PITCH_MIN, 'pitch_max': PITCH_MAX}
    (OUT/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')


if __name__ == '__main__':
    main()
