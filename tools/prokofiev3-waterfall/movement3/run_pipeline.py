"""Rebuild the third-movement alignment from the supplied score and audio.

Use --timeline-only after an alignment has already been reviewed. The script
does not render video; render_full.py is an explicit, separate step.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from parse_score import AUDIO, HERE, SOURCE, digest


def call(name: str) -> None:
    subprocess.run([sys.executable, str(HERE / name)], check=True)


def verify_sources() -> None:
    if not SOURCE.is_file() or not AUDIO.is_file():
        raise FileNotFoundError('Set PROK3_M3_SCORE_PATH and PROK3_M3_AUDIO_PATH to the supplied files')
    current = json.loads((HERE / 'alignment-performance-reviewed.json').read_text())
    expected = current['sources']
    if digest(SOURCE) != expected['score']['sha256'] or digest(AUDIO) != expected['audio']['sha256']:
        raise ValueError('This saved alignment belongs to a different score or recording')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeline-only', action='store_true',
                        help='Reuse the reviewed alignment and rebuild scene data only')
    args = parser.parse_args()
    if args.timeline_only:
        verify_sources()
        call('build_render.py')
        call('prepare_chunks.py')
        return
    call('parse_score.py')
    score = json.loads((HERE / 'score-events.json').read_text())
    clock_file = HERE / 'score-audio-clock.json'
    reuse_clock = False
    if clock_file.exists():
        old = json.loads(clock_file.read_text())
        reuse_clock = (old.get('source_score_sha256') == score['source_score_sha256']
                       and old.get('source_audio_sha256') == score['source_audio_sha256'])
    if not reuse_clock:
        call('sync_score.py')
    call('extract_orchestra.py')
    call('extract_piano.py')
    call('align_notes.py')
    call('refine_alignment.py')
    call('performance_refinement.py')
    call('build_render.py')
    call('prepare_chunks.py')


if __name__ == '__main__':
    main()
