"""Transcribe the remaining Prokofiev 3/I piano in bounded, overlapping crops.

Large WAV stems are disposable and removed after each verified compact MIDI.
The model and executable paths are supplied by the caller, not downloaded by
this script. Each crop is independent, so an interrupted run resumes safely.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from prepare_preview import HERE


# Five seconds of context at both sides of every join. The last crop excludes
# the recording's trailing near-silence, which has no scored attacks.
CROPS = ((175, 75), (245, 75), (315, 75), (385, 75), (455, 75), (525, 55))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir', type=Path, required=True)
    parser.add_argument('--separator', required=True)
    parser.add_argument('--transkun', required=True)
    parser.add_argument('--scratch-root', type=Path,
                        default=Path(tempfile.gettempdir())/'prok3-piano-crops')
    args = parser.parse_args()
    root = args.scratch_root.resolve()
    if root == Path('/') or str(root).startswith(str(HERE.resolve())):
        raise ValueError('Scratch directory must be a separate temporary directory')
    root.mkdir(parents=True, exist_ok=True)
    for start, duration in CROPS:
        stop = start + duration
        output = HERE / f'piano-audio{start}-{stop}-transkun.mid'
        if output.is_file() and output.stat().st_size > 100:
            print('reusing', output.name, flush=True)
            continue
        scratch = root / f'crop-{start}-{stop}'
        command = [sys.executable, str(HERE / 'prepare_piano_onsets.py'),
                   '--model-dir', str(args.model_dir),
                   '--separator', args.separator, '--transkun', args.transkun,
                   '--scratch', str(scratch), '--start', str(start),
                   '--seconds', str(duration), '--output', str(output)]
        print('processing', start, stop, flush=True)
        subprocess.run(command, check=True)
        if not output.is_file() or output.stat().st_size < 100:
            raise RuntimeError(f'Empty transcription: {output}')
        shutil.rmtree(scratch)
        print('saved compact MIDI; deleted WAV scratch', output.name, flush=True)


if __name__ == '__main__':
    main()
