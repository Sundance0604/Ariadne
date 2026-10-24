"""Read local score assets without changing or uploading them.

Run with Python 3.12 and requirements-audit.txt. Optional project-local
dependencies in .tools/audit-packages are also supported.
"""

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
LOCAL_PACKAGES = ROOT / '.tools' / 'audit-packages'
if LOCAL_PACKAGES.is_dir():
    sys.path.insert(0, str(LOCAL_PACKAGES))

from pypdf import PdfReader
from mutagen.mp3 import MP3


def fingerprint(path):
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': path.relative_to(ROOT).as_posix(),
            'bytes': path.stat().st_size, 'sha256': digest}


def inspect_pdf(path):
    reader = PdfReader(path)
    pages = []
    for index, page in enumerate(reader.pages):
        text = page.extract_text() or ''
        pages.append({'page_number': index + 1,
                      'width_pt': float(page.mediabox.width),
                      'height_pt': float(page.mediabox.height),
                      'rotation': page.rotation,
                      'text_characters': len(text)})
    return {**fingerprint(path), 'kind': 'pdf', 'page_count': len(pages),
            'encrypted': reader.is_encrypted,
            'metadata': {str(k): str(v) for k, v in (reader.metadata or {}).items()},
            'pages_with_extractable_text': sum(p['text_characters'] > 0 for p in pages),
            'first_page_text_excerpt': (reader.pages[0].extract_text() or '')[:1800],
            'pages': pages, 'omr_status': 'not_run'}


def inspect_audio(path):
    audio = MP3(path)
    info = audio.info
    return {**fingerprint(path), 'kind': 'mp3',
            'duration_seconds': info.length, 'sample_rate_hz': info.sample_rate,
            'channels': info.channels, 'bitrate_bps': info.bitrate,
            'bitrate_mode': str(info.bitrate_mode),
            'mpeg_version': info.version, 'layer': info.layer,
            'header_sketchy': info.sketchy,
            'tags': {key: str(value) for key, value in (audio.tags or {}).items()},
            'inspection_method': 'mutagen metadata; not full audio decode or listening'}


def inspect_midi(path):
    # Import only when MIDI is provided; the PDF + MP3 route does not need mido.
    from mido import MidiFile, merge_tracks, tempo2bpm, tick2second
    midi = MidiFile(path)
    if midi.type == 2:
        raise ValueError('Type 2 MIDI has independent timelines; manual review required')
    tracks = []
    for index, track in enumerate(midi.tracks):
        pitches = [e.note for e in track if e.type == 'note_on' and e.velocity > 0]
        tracks.append({'track_index': index, 'name': track.name,
                       'message_count': len(track), 'note_on_count': len(pitches),
                       'end_tick': sum(e.time for e in track),
                       'channels': sorted({e.channel for e in track if hasattr(e, 'channel')}),
                       'pitch_range': [min(pitches), max(pitches)] if pitches else None})
    events = []
    tick, seconds, tempo = 0, 0.0, 500000
    counts = Counter()
    for event in merge_tracks(midi.tracks):
        tick += event.time
        seconds += tick2second(event.time, midi.ticks_per_beat, tempo)
        counts[event.type] += 1
        if event.type in {'set_tempo', 'time_signature', 'key_signature', 'marker', 'text'}:
            record = event.dict()
            record.pop('time', None)
            record.update(tick=tick, midi_seconds=seconds)
            if event.type == 'set_tempo':
                record['quarter_notes_per_minute'] = tempo2bpm(event.tempo)
            events.append(record)
        if event.type == 'set_tempo':
            tempo = event.tempo
    tempos = [e['quarter_notes_per_minute'] for e in events if e['type'] == 'set_tempo']
    meters = sorted({(e['numerator'], e['denominator']) for e in events
                     if e['type'] == 'time_signature'})
    return {**fingerprint(path), 'kind': 'midi', 'optional': True,
            'format_type': midi.type, 'ticks_per_beat': midi.ticks_per_beat,
            'track_count': len(tracks), 'duration_seconds': midi.length,
            'integrated_duration_seconds': seconds,
            'event_counts': dict(counts), 'note_on_count': sum(t['note_on_count'] for t in tracks),
            'quarter_note_bpm_range': [min(tempos), max(tempos)] if tempos else None,
            'distinct_time_signatures': [f'{a}/{b}' for a, b in meters],
            'metadata_text_encoding': 'mido default latin1; labels may need manual correction',
            'tracks': tracks, 'timeline_events': events}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resource-dir', type=Path,
                        default=ROOT / 'resource' / 'ravel left hand piano concerto')
    parser.add_argument('--skip-midi', action='store_true')
    parser.add_argument('--output', type=Path, default=ROOT / 'reports' / 'input-audit.json')
    args = parser.parse_args()
    files = sorted(args.resource_dir.resolve().iterdir())
    audio_paths = [p for p in files if p.suffix.lower() == '.mp3']
    pdf_paths = [p for p in files if p.suffix.lower() == '.pdf']
    midi_paths = [p for p in files if p.suffix.lower() in {'.mid', '.midi'}]
    if not audio_paths or not pdf_paths:
        parser.error('At least one MP3 and one PDF are required; MIDI is optional')
    assets = [inspect_audio(p) for p in audio_paths] + [inspect_pdf(p) for p in pdf_paths]
    if midi_paths and not args.skip_midi:
        assets.extend(inspect_midi(p) for p in midi_paths)
    result = {
        'audit_format_version': '1.0.0',
        'created_at': datetime.now(timezone(timedelta(hours=8))).isoformat(),
        'local_only': True,
        'midi_status': 'skipped_by_request' if args.skip_midi else
                       ('provided' if midi_paths else 'not_provided'),
        'tools': {name: version(name) for name in ['pypdf', 'mutagen']},
        'assets': assets,
        'compatibility_status': 'needs_score_and_audio_review',
        'limitations': ['Metadata does not establish edition compatibility.',
                        'No OMR, full audio decoding, alignment or listening was performed.']}
    if midi_paths and not args.skip_midi:
        result['tools']['mido'] = version('mido')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(args.output), 'assets': len(assets),
                      'midi_status': result['midi_status']}, ensure_ascii=True))


if __name__ == '__main__':
    main()
