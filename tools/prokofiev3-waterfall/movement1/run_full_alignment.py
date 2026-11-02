"""Resume/rebuild the complete score/audio alignment with one command.

Requires the three Python environments and piano model described in README.md.
Existing compact, fingerprint-matched stages are reused to spare CPU/GPU and
disk. Pass --refresh-clock to deliberately rerun the expensive global DTW.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from prepare_preview import (AUDIO, EXPECTED_AUDIO_SHA256, EXPECTED_SCORE_SHA256,
                             HERE, MXL, digest)


def call(script:str,*args:str) -> None:
    subprocess.run([sys.executable,str(HERE/script),*args],check=True)


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir',type=Path)
    parser.add_argument('--separator')
    parser.add_argument('--transkun')
    parser.add_argument('--refresh-clock',action='store_true')
    parser.add_argument('--scratch-root',type=Path,
                        default=Path(tempfile.gettempdir())/'prok3-full-pipeline')
    args=parser.parse_args()
    if digest(AUDIO)!=EXPECTED_AUDIO_SHA256 or digest(MXL)!=EXPECTED_SCORE_SHA256:
        raise ValueError('Source fingerprint changed; old caches cannot be reused')
    clock=HERE/'prokofiev3-full-global-clock.json'
    if args.refresh_clock or not clock.is_file():
        call('sync_full.py')
    else:
        record=json.loads(clock.read_text())
        if (record['source_audio_sha256']!=EXPECTED_AUDIO_SHA256 or
                record['source_score_sha256']!=EXPECTED_SCORE_SHA256):
            raise ValueError('Existing full clock belongs to other inputs')
        print('reusing full score/audio clock',flush=True)
    opening=((0,125,'piano-audio125-transkun.mid'),
             (115,70,'piano-audio115-185-transkun.mid'))
    missing_piano=(any(not (HERE/name).is_file() for _,_,name in opening)
                   or any(not (HERE/f'piano-audio{a}-{b}-transkun.mid').is_file()
                          for a,b in ((175,250),(245,320),(315,390),
                                      (385,460),(455,530),(525,580))))
    missing_sustain=not (HERE/'piano-sustain-features/manifest.json').is_file()
    if missing_piano or missing_sustain:
        if not (args.model_dir and args.separator and
                (args.transkun or not missing_piano)):
            parser.error('Missing piano evidence requires --model-dir, '
                         '--separator and (for transcription) --transkun')
    scratch=args.scratch_root.resolve()
    if scratch==Path('/') or scratch==HERE.resolve():
        raise ValueError('Unsafe scratch directory')
    if missing_piano:
        for start,duration,name in opening:
            if (HERE/name).is_file():continue
            child=scratch/f'opening-{start}-{start+duration}'
            call('prepare_piano_onsets.py','--model-dir',str(args.model_dir),
                 '--separator',args.separator,'--transkun',args.transkun,
                 '--start',str(start),'--seconds',str(duration),
                 '--scratch',str(child),'--output',str(HERE/name))
            if child.exists():shutil.rmtree(child)
        call('run_full_piano.py','--model-dir',str(args.model_dir),
             '--separator',args.separator,'--transkun',args.transkun,
             '--scratch-root',str(scratch/'later'))
    call('extract_full_orchestra.py')
    if missing_sustain:
        call('extract_piano_sustain.py','--model-dir',str(args.model_dir),
             '--separator',args.separator,'--scratch',str(scratch/'sustain'))
    call('align_full.py')
    call('verify_full.py')
    call('build_role_table.py')
    print('Complete:',HERE/'prokofiev3-full-alignment.json',flush=True)


if __name__=='__main__':main()
