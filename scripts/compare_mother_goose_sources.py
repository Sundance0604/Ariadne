"""Audit the supplied alternate Mother Goose sources without choosing a winner.

Requires optional pdfplumber and mido. Uses original MusicXML event order and
explicit transposition, never MIDI performance seconds as an audio clock.
"""
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.musicxml_analysis.ingest import xml_root

BASE = ROOT / 'resource/mother goose'
OUT = ROOT / 'works/ravel-mother-goose/analysis'


def file_record(p):
    return {'path': p.relative_to(ROOT).as_posix(), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
            'bytes': p.stat().st_size}


def xml_events(path):
    root, _ = xml_root(path)
    parts = [{'id': p.get('id'), 'name': p.findtext('part-name')}
             for p in root.findall('part-list/score-part')]
    events, meters, directions, anomalies = [], [], [], []
    sizes = {}
    step_pc = dict(C=0, D=2, E=4, F=5, G=7, A=9, B=11)
    for part in root.findall('part'):
        pid = part.get('id'); div = None; transposes = {}
        sizes[pid] = len(part.findall('measure'))
        for seq, measure in enumerate(part.findall('measure'), 1):
            cursor = F(0); previous = F(0); ni = 0
            for child in measure:
                if child.tag == 'attributes':
                    if child.find('divisions') is not None:
                        div = int(child.findtext('divisions'))
                    for t in child.findall('transpose'):
                        transposes[t.get('number', 'all')] = F(t.findtext('chromatic', '0')) + 12*F(t.findtext('octave-change', '0'))
                    if child.find('time') is not None:
                        meters.append({'part_id': pid, 'measure_sequence': seq,
                                       'time': {e.tag: e.text for e in child.find('time')}})
                elif child.tag in {'backup', 'forward'}:
                    cursor += (1 if child.tag == 'forward' else -1)*F(child.findtext('duration', '0'))/(div or 1)
                    if cursor < 0:
                        anomalies.append({'kind': 'negative_xml_cursor', 'part_id': pid,
                                          'sequence': seq, 'cursor_q': str(cursor) if div else None,
                                          'cursor_source_units': str(cursor) if not div else None})
                elif child.tag == 'direction':
                    if pid == parts[0]['id']:
                        words = [w.text for w in child.findall('direction-type/words') if w.text]
                        rehearsal = [w.text for w in child.findall('direction-type/rehearsal')]
                        if words or rehearsal:
                            directions.append({'sequence': seq, 'xml_number': measure.get('number'), 'words': words, 'rehearsal': rehearsal})
                elif child.tag == 'note':
                    ni += 1; duration = F(child.findtext('duration', '0'))/(div or 1)
                    if div is None and seq == 1 and ni == 1:
                        anomalies.append({'kind': 'missing_divisions', 'part_id': pid,
                                          'consequence': 'duration and onset retained in unspecified source units; no quarter-note clock inferred'})
                    onset = previous if child.find('chord') is not None else cursor
                    if child.find('chord') is None:
                        previous = onset
                        if child.find('grace') is None:
                            cursor += duration
                    pitch = child.find('pitch')
                    if pitch is None:
                        continue
                    staff = child.findtext('staff', '1')
                    encoded = (int(pitch.findtext('octave'))+1)*12 + step_pc[pitch.findtext('step')] + F(pitch.findtext('alter', '0'))
                    transpose = transposes.get(staff, transposes.get('all', F(0)))
                    events.append({'id': f'{pid}-xml-m{seq:04d}-n{ni:04d}', 'part_id': pid,
                                   'sequence': seq, 'xml_number': measure.get('number'),
                                   'onset_q': str(onset) if div else None, 'duration_q': str(duration) if div else None,
                                   'onset_source_units': str(onset) if not div else None,
                                   'duration_source_units': str(duration) if not div else None,
                                   'encoded_ps': str(encoded), 'concert_ps': str(encoded+transpose),
                                   'transpose_semitones': str(transpose), 'staff': staff,
                                   'voice': child.findtext('voice', '1'),
                                   'eligible': div is not None and duration > 0 and child.find('grace') is None and child.get('print-object') != 'no' and child.findtext('notehead') != 'none',
                                   'harmonic_notation': child.find('.//harmonic') is not None})
    return {'source': file_record(path), 'title': root.findtext('work/work-title'), 'parts': parts,
            'part_measure_counts': sizes, 'events': events, 'meters': meters, 'directions': directions,
            'anomalies': anomalies,
            'declared_source': root.findtext('identification/source'),
            'software': [e.text for e in root.findall('identification/encoding/software')]}


def signature(events, lo, hi, pids=None, mode='full'):
    groups = defaultdict(set)
    for e in events:
        if e['eligible'] and lo <= e['sequence'] <= hi and (pids is None or e['part_id'] in pids):
            if mode == 'full':
                v = (e['onset_q'], e['duration_q'], e['concert_ps'])
            else:
                v = int(F(e['concert_ps'])) % 12
            groups[e['sequence']].add(v)
    return [tuple(sorted(groups[i])) for i in range(lo, hi+1)]


def compare(old, new, label, old_span, new_span, old_parts, new_parts):
    a = signature(old['events'], *old_span, old_parts)
    b = signature(new['events'], *new_span, new_parts)
    detail = []
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            detail.append({'old_local': i+1, 'new_local': i+1,
                           'old_only': sorted(set(x)-set(y)), 'new_only': sorted(set(y)-set(x))})
    return {'label': label, 'old_span_global': old_span, 'new_span_local': new_span,
            'old_part_ids': old_parts, 'new_part_ids': new_parts, 'compared_measure_count': min(len(a), len(b)),
            'equal_measure_signatures': sum(x == y for x, y in zip(a, b)), 'differences': detail,
            'scope': 'unique (onset,duration,concert pitch) events within stated instrument family; not notehead correctness',
            'same_signature_is_not_independent_verification': True}


def build():
    import pdfplumber
    import mido
    OUT.mkdir(parents=True, exist_ok=True)
    original = xml_events(BASE / 'ma-mere-loye-maurice-ravel.mxl')
    candidates = [xml_events(p) for p in sorted((BASE / 'new').glob('*.mxl'))]
    rows = []
    for c in candidates:
        stem = Path(c['source']['path']).stem
        pdf = BASE / 'new' / (stem+'.pdf'); midi_path = BASE / 'new' / (stem+'.mid')
        with pdfplumber.open(pdf) as doc:
            pdf_info = {**file_record(pdf), 'page_count': len(doc.pages)}
        midi = mido.MidiFile(midi_path)
        channels = Counter(m.channel for tr in midi.tracks for m in tr if m.type == 'note_on' and m.velocity > 0)
        rows.append({k: v for k, v in c.items() if k != 'events'} | {'pitched_event_count': len(c['events']),
                    'eligible_pitched_event_count': sum(e['eligible'] for e in c['events']),
                    'pdf': pdf_info, 'midi': file_record(midi_path) | {'tracks': len(midi.tracks),
                        'ticks_per_beat': midi.ticks_per_beat, 'note_on_counts_by_channel': dict(channels)},
                    'status': 'unverified_transcription; edition_scope_checked; no_activation'})
    pavane = next(c for c in candidates if 'pavane' in c['source']['path'])
    beauty = next(c for c in candidates if 'iv-mei' in c['source']['path'])
    garden = next(c for c in candidates if 'di7qu' in c['source']['path'])
    checks = [
        compare(original, pavane, '帕凡舞前20小节／长笛组', [1,20], [1,20], ['P2','P3'], ['P2']),
        compare(original, pavane, '帕凡舞前20小节／圆号组', [1,20], [1,20], ['P14','P15'], ['P8']),
        compare(original, beauty, '美女与野兽前172小节／单簧管组', [304,475], [1,172], ['P7','P8','P9','P10'], ['P5']),
        compare(original, beauty, '美女与野兽前172小节／低音巴松', [304,475], [1,172], ['P13'], ['P7']),
        compare(original, garden, '仙境花园56小节／竖琴', [476,531], [1,56], ['P24'], ['P14']),
        compare(original, garden, '仙境花园56小节／钢片琴', [476,531], [1,56], ['P23'], ['P13']),
    ]
    alignments = []
    for c, span in [(pavane,(1,20)), (beauty,(304,475)), (garden,(476,531))]:
        a = signature(original['events'], *span, mode='pcs')
        b = signature(c['events'], 1, max(c['part_measure_counts'].values()), mode='pcs')
        matcher = SequenceMatcher(None, a, b, autojunk=False)
        alignments.append({'new_source': c['source']['path'], 'old_span_global': list(span),
                           'method': 'sequence comparison of per-measure pitch-class unions; only structural candidates',
                           'candidate_blocks': [{'old_global_start': span[0]+x.a, 'new_local_start': x.b+1, 'length': x.size}
                                                for x in matcher.get_matching_blocks() if x.size],
                           'caution': 'Pitch-class union discards timing, voice, spelling and octave. It cannot certify a bar map.'})
    document = {'schema_version': '1.0.0', 'checked_on': '2026-10-26',
                'original': original['source'], 'candidates': rows, 'family_comparisons': checks,
                'structural_candidates': alignments, 'decision': 'retain_original_suite_basis; use_new_as_ballet_comparison',
                'limitations': ['Only three overlapping movements; no new Petit Poucet or Laideronnette.',
                    'Extra bars are not automatically transcription errors or verified ballet interludes.',
                    'PDF and MusicXML can share one transcription lineage.',
                    'MIDI is inventoried as symbolic media; notes and timing are not established as correct.',
                    'Harmonics, ties, grace notes and glissandi need notation-aware checks; event differences are diagnostics.'],
                'human_signoff': None, 'expert_review': None}
    (OUT / 'alternate-source-audit.json').write_text(json.dumps(document, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'candidates': len(rows), 'comparisons': [{k:v for k,v in c.items() if k in ['label','compared_measure_count','equal_measure_signatures']} for c in checks],
                      'structural_candidates': alignments}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    build()
