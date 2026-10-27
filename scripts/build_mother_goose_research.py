"""Score-only Mother Goose evidence. Never activates a playback track or clock.

Run with requirements-analysis.txt in an optional processing environment.
The source-specific editorial guide is kept separately from computed evidence.
"""
import argparse
from collections import Counter, defaultdict
import csv
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.musicxml_analysis.ingest import ingest, xml_root
from backend.musicxml_analysis.analyze import chord_description, orchestration

WORK = ROOT / 'works/ravel-mother-goose'
SOURCE = ROOT / 'resource/mother goose/ma-mere-loye-maurice-ravel.mxl'
MOVEMENTS = [
    (1, '睡美人的帕凡舞', 'Pavane de la Belle au bois dormant', 1, 20, 3, 5),
    (2, '小拇指', 'Petit Poucet', 21, 99, 6, 11),
    (3, '丑姑娘，宝塔女皇', 'Laideronnette, Impératrice des Pagodes', 100, 303, 12, 34),
    (4, '美女与野兽的对话', 'Les entretiens de la Belle et de la Bête', 304, 475, 35, 47),
    (5, '仙境花园', 'Le jardin féerique', 476, 531, 48, 55),
]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')


def notes(data, pid, lo, hi):
    return sorted([e for e in data['events'] if e['part_id'] == pid
                   and lo <= e['measure_sequence'] <= hi and e['analysis_eligible']],
                  key=lambda e: (F(e['score_start_q']), e['source_note_index']))


def compare(data, id, a, b, claim, pages):
    left, right = notes(data, *a), notes(data, *b)
    pairs = list(zip(left, right))
    offsets = sorted({y['concert_pitch']['ps'] - x['concert_pitch']['ps'] for x, y in pairs})
    same_rhythm = len(left) == len(right) and all(
        F(x['duration_q']) == F(y['duration_q']) and
        F(x['score_start_q']) - F(left[0]['score_start_q']) ==
        F(y['score_start_q']) - F(right[0]['score_start_q']) for x, y in pairs)
    return {'id': id, 'claim': claim, 'left_event_ids': [e['id'] for e in left],
            'right_event_ids': [e['id'] for e in right], 'event_counts': [len(left), len(right)],
            'paired_pitch_offsets_semitones': offsets, 'same_notated_onsets_and_durations': same_rhythm,
            'pairing_policy': 'source order; equal counts required for complete correspondence',
            'pdf_pages_examined': pages, 'status': 'agent_symbolic_comparison',
            'human_signoff': None, 'expert_review': None}


def verticals(data):
    """Written time, not audio. No key-profile or Roman-number guesses."""
    starts, ends = defaultdict(list), defaultdict(list)
    for e in data['events']:
        if e['analysis_eligible'] or (e['kind'] == 'unpitched' and not e['exclusion_reason'] and F(e['duration_q']) > 0):
            starts[F(e['score_start_q'])].append(e)
            ends[F(e['score_end_q'])].append(e)
    points = sorted(set(starts) | set(ends) | {F(m['start_q']) for m in data['measures']})
    active, cache, windows = {}, {}, []
    mi = 0
    for start, end in zip(points, points[1:]):
        for e in ends[start]:
            active.pop(e['id'], None)
        for e in starts[start]:
            active[e['id']] = e
        while mi + 1 < len(data['measures']) and F(data['measures'][mi + 1]['start_q']) <= start:
            mi += 1
        pitches = [e for e in active.values() if e['analysis_eligible']]
        key = tuple(sorted({e['concert_pitch']['name'] for e in pitches}))
        if key not in cache:
            cache[key] = chord_description(pitches)
        windows.append({'id': f'mg-v-{len(windows)+1:06d}', 'measure_id': data['measures'][mi]['measure_id'],
                        'start_q': str(start), 'end_q': str(end), 'event_ids': sorted(active),
                        'active_part_ids': sorted({e['part_id'] for e in active.values()}),
                        'sonority': cache[key],
                        'harmonic_notation_event_ids': [e['id'] for e in pitches if any('harmonic' in n for n in e['notations_xml'])],
                        'tremolo_event_ids': [e['id'] for e in pitches if any('tremolo' in n for n in e['notations_xml'])]})
    return {'windows': windows,
            'basis': 'half-open written intervals; XML transpose once; all source witnesses retained',
            'limitations': ['Vertical labels are pitch identities, not functional reductions.',
                           'Natural/artificial harmonic notation needs separate sounding-pitch checking.',
                           'Tremolos, glissandi, ornaments and acoustic sustain are not reconstructed.',
                           'Duplicate source parts do not represent additional players or independent voices.']}


def score_studies(data):
    def window(seq, offset, parts):
        start = F(data['measures'][seq-1]['start_q']) + F(offset)
        active = [e for e in data['events'] if e['analysis_eligible'] and
                  F(e['score_start_q']) <= start < F(e['score_end_q'])]
        selected = [e for e in active if e['part_id'] in parts]
        return {'measure_id': f'xml-m{seq:04d}', 'offset_q': str(offset),
                'selected_event_ids': [e['id'] for e in selected],
                'other_active_event_ids': [e['id'] for e in active if e not in selected],
                'selected_pitches': sorted({e['concert_pitch']['name'] for e in selected}),
                'all_active_pitches': sorted({e['concert_pitch']['name'] for e in active})}
    cases = [
        {'id': 'I-opening-verticals', 'title': '旋律音集不是起始同时和弦', 'pdf_pages': [3],
         'windows': [window(1,0,['P3','P14']),window(1,1,['P3','P14'])],
         'reading': '第一曲起点为A3/A4的八度，下一四分音符时点为G4/E5。整小节旋律的五声集合不能冒充起始和弦。'},
        {'id': 'I-moving-inner-line', 'title': '持续层与经过的半音线分开', 'pdf_pages': [3],
         'windows': [window(5,0,['P2','P3','P8','P36']),window(5,1,['P2','P3','P8','P36']),
                     window(5,2,['P2','P3','P8','P36'])],
         'reading': '保留E低层与F–F♯–G内声的时点差异。这里只选长笛、单簧管与大提琴代表层，不把其他加倍或泛音抹掉。'},
        {'id': 'I-return-d-minor-seventh', 'title': '第13小节起点的D小七和弦身份', 'pdf_pages': [4],
         'windows': [window(13,0,['P2','P8','P14','P33'])],
         'reading': 'D3、F4、A4、C4构成D小七和弦音高身份；以A调式为背景可讨论下属区域，功能结论还依赖前后句法。'},
        {'id': 'V-first-bar-extension', 'title': '终曲第一小节的扩展音逐步加入', 'pdf_pages': [48],
         'windows': [window(476,0,['P28','P30','P33','P36']),window(476,1,['P28','P30','P33','P36'])],
         'reading': '起点C2、E3、C4只给主音与三音；第二拍C2、E3、B3、D4可读为省略五音的C大七加九。该标签限于第二拍，不能回填起点。'}
    ]
    for case in cases:
        case.update({'status': 'agent_score_sample_and_symbolic_reasoning', 'human_signoff': None, 'expert_review': None})
    return {'cases': cases, 'policy': 'Every reduction lists selected and other active source events separately.'}


def build(out, cache=None):
    out = out.resolve()
    if not out.is_relative_to(WORK.resolve()) or out.exists():
        raise ValueError('Choose a new snapshot directory inside works/ravel-mother-goose')
    protected = ['library.json', 'alignment.json', 'measure-map.json', 'analysis/musicxml/current.json',
                 'analysis/musicxml/interpretation-current.json', 'analysis/hud/current.json']
    before = {p: digest(ROOT / p) for p in protected}
    source_hash = digest(SOURCE)
    if cache:
        envelope = json.loads(cache.read_text(encoding='utf-8'))
        if envelope['source_sha256'] != source_hash or envelope['ingest_code_sha256'] != digest(ROOT / 'backend/musicxml_analysis/ingest.py'):
            raise ValueError('Ingest cache fingerprint mismatch')
        data = envelope['data']
    else:
        data = ingest(SOURCE)
    xml, _ = xml_root(SOURCE)
    source_counts = {p.get('id'): sum(len(m.findall('note')) for m in p.findall('measure')) for p in xml.findall('part')}
    if source_counts != dict(Counter(e['part_id'] for e in data['events'])):
        raise ValueError('Source event census does not agree')
    if len(data['measures']) != 531 or len(data['parts']) != 40:
        raise ValueError('This adapter expects the supplied five-movement edition')
    print('Building written verticals and instrument evidence.', flush=True)
    measures = data['measures']
    movement_rows = []
    for number, title, french, lo, hi, first_page, last_page in MOVEMENTS:
        row = {'movement': number, 'title': title, 'french_title': french,
               'first_sequence_index': lo, 'last_sequence_index': hi,
               'measure_count': hi-lo+1, 'first_pdf_page': first_page, 'last_pdf_page': last_page,
               'start_q': measures[lo-1]['start_q'],
               'end_q': str(F(measures[hi-1]['start_q']) + F(measures[hi-1]['duration_q'])),
               'numbering_basis': 'local orchestral measure = global XML sequence - first sequence + 1',
               'pdf_scope_status': 'movement title and page span checked by agent; no measure rectangles'}
        movement_rows.append(row)
        for m in measures[lo-1:hi]:
            m.update({'movement': number, 'movement_measure': m['sequence']-lo+1})
            m['xml_layout_page'] = m.pop('page')
            m['xml_layout_system_index'] = m.pop('system_index')
    comparisons = [
        compare(data, 'pavane-return', ('P3', 1, 2), ('P2', 13, 14),
                '第一曲1–2与13–14：旋律复现，配器及低声部更换。', [3, 4]),
        compare(data, 'pavane-inner-line', ('P3', 5, 7), ('P30', 17, 19),
                '第一曲5–7长笛2与17–19第二小提琴：半音内声的局部复现。', [3, 5]),
        compare(data, 'pavane-doubling', ('P14', 1, 3), ('P33', 1, 3),
                '第一曲圆号与中提琴的同度加倍；加倍不另算独立旋律。', [3]),
        compare(data, 'poucet-octaves', ('P1', 80, 83), ('P35', 80, 83),
                '第二曲60–63：短笛与独奏大提琴的两个八度加倍。只确认此窗口。', [10]),
        compare(data, 'pagodes-octaves', ('P2', 169, 175), ('P23', 169, 175),
                '第三曲70–76：长笛与钢片琴低谱表的局部同度支撑，不是先后模仿。', [22]),
        compare(data, 'beast-transposition', ('P13', 352, 355), ('P13', 363, 366),
                '第四曲49–52与60–63：野兽主题上移大二度。', [38, 39]),
        compare(data, 'beast-prince', ('P13', 363, 366), ('P25', 451, 454),
                '第四曲60–63与148–151：音高顺序上移五个八度，节奏经改写，不称为逐音原样复制。', [38, 39, 46]),
    ]
    duplicates = []
    index = defaultdict(list)
    for e in data['events']:
        if e['analysis_eligible']:
            index[(e['measure_id'], e['onset_q'], e['duration_q'], e['concert_pitch']['name'])].append(e)
    for key, values in index.items():
        if len({e['part_id'] for e in values}) > 1:
            duplicates.append({'measure_id': key[0], 'onset_q': key[1], 'duration_q': key[2], 'pitch': key[3],
                               'event_ids': [e['id'] for e in values],
                               'status': 'coincident_source_events; genuine doubling vs exported divisi copies not globally resolved'})
    guide = json.loads((WORK / 'analysis/guide.json').read_text(encoding='utf-8'))
    for section in guide['sections']:
        mv = movement_rows[section['movement']-1]
        lo, hi = [mv['first_sequence_index'] + x - 1 for x in section['local_measures']]
        section.update({'first_measure_id': f'xml-m{lo:04d}', 'last_measure_id': f'xml-m{hi:04d}',
                        'start_q': measures[lo-1]['start_q'],
                        'end_q': str(F(measures[hi-1]['start_q'])+F(measures[hi-1]['duration_q'])),
                        'pdf_movement_pages': [mv['first_pdf_page'], mv['last_pdf_page']],
                        'pdf_precision': 'movement_only; section page not inferred from XML layout',
                        'evidence_event_ids': [e['id'] for e in data['events'] if lo <= e['measure_sequence'] <= hi
                                               and e['part_id'] in section['evidence_parts'] and e['analysis_eligible']],
                        'interpretation_status': 'agent_editorial_synthesis_with_attributed_readings',
                        'human_signoff': None, 'expert_review': None})
    out.mkdir(parents=True)
    outputs = {'events.json': {'events': data['events']}, 'parts.json': {'parts': data['parts']},
               'measures.json': {'measures': measures}, 'notation.json': {'notation': data['notation']},
               'parse-audit.json': data['audit'], 'verticals.json': verticals(data),
               'orchestration.json': orchestration(data), 'comparisons.json': {'comparisons': comparisons},
               'coincident-events.json': {'groups': duplicates}, 'sections.json': guide,
               'score-studies.json': score_studies(data),
               'movements.json': {'movements': movement_rows}}
    for name, document in outputs.items():
        write(out / name, document)
    with (out / 'measure-index.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        fields = ['measure_id', 'sequence', 'movement', 'movement_measure', 'start_q', 'duration_q', 'xml_layout_page']
        writer = csv.DictWriter(stream, fields, extrasaction='ignore'); writer.writeheader(); writer.writerows(measures)
    pdf = next((ROOT / 'resource/mother goose').glob('IMSLP*.pdf'))
    editorial_paths = ['works/ravel-mother-goose/analysis/guide.json',
                       'works/ravel-mother-goose/analysis/sources.json',
                       'works/ravel-mother-goose/analysis/alternate-source-audit.json']
    (out / 'editorial').mkdir()
    for path in editorial_paths:
        shutil.copyfile(ROOT / path, out / 'editorial' / Path(path).name)
    sources = [{'path': p.relative_to(ROOT).as_posix(), 'sha256': digest(p), 'bytes': p.stat().st_size}
               for p in sorted((ROOT / 'resource/mother goose').rglob('*')) if p.is_file()]
    manifest = {'schema_version': '1.0.0', 'work_id': 'ravel-mother-goose', 'edition': 'five-movement orchestral suite',
                'source': {'path': SOURCE.relative_to(ROOT).as_posix(), 'sha256': source_hash},
                'pdf': {'path': pdf.relative_to(ROOT).as_posix(), 'sha256': digest(pdf), 'page_count': 55},
                'inputs': sources, 'counts': {'parts': len(data['parts']), 'measures': len(measures),
                    'events': len(data['events']), 'eligible_pitched_events': sum(e['analysis_eligible'] for e in data['events']),
                    'sections': len(guide['sections']), 'comparisons': len(comparisons),
                    'written_windows': len(outputs['verticals.json']['windows'])},
                'music21_version': data['audit']['music21_version'],
                'code': {p: digest(ROOT / p) for p in ['scripts/build_mother_goose_research.py',
                          'scripts/compare_mother_goose_sources.py',
                          'backend/musicxml_analysis/ingest.py', 'backend/musicxml_analysis/analyze.py']},
                'editorial_inputs': {p: digest(ROOT / p) for p in editorial_paths},
                'files': {p.relative_to(out).as_posix(): {'sha256': digest(p), 'bytes': p.stat().st_size}
                          for p in sorted(out.rglob('*')) if p.is_file()},
                'protected_inputs': before, 'audio': None, 'recording_projection': None,
                'status': 'score_only_research; agent_sample_checked; human_and_expert_review_pending',
                'limitations': ['No complete PDF measure geometry or sound alignment.',
                    'XML transcription provenance and all-note accuracy are not established.',
                    'Harmonic notation and sounding pitches require additional review.',
                    'Piano-version numbers, especially movement III, are not silently mapped to orchestral bars.']}
    if any(digest(ROOT / p) != before[p] for p in protected):
        raise ValueError('An existing active input changed')
    if digest(SOURCE) != source_hash:
        raise ValueError('Source changed during build')
    write(out / 'manifest.json', manifest)
    write(WORK / 'analysis/current.json', {'path': out.relative_to(ROOT).as_posix(),
                                          'manifest_sha256': digest(out / 'manifest.json'), 'mode': 'score_only'})
    write(WORK / 'project.json', {'format_version': '1.0.0', 'id': 'ravel-mother-goose',
        'title': '拉威尔 · 鹅妈妈（五曲管弦乐组曲）', 'stage': 'score_only_research',
        'inputs': sources, 'audio': None, 'alignment': None,
        'analysis_pointer': 'works/ravel-mother-goose/analysis/current.json',
        'movements': movement_rows, 'library_registration': 'pending_media_or_explicit_score_only_UI_support',
        'human_signoff': None, 'expert_review': None})
    print(json.dumps(manifest['counts'], ensure_ascii=False), flush=True)
    print('Comparisons:', [(x['id'], x['event_counts'], x['paired_pitch_offsets_semitones'],
                            x['same_notated_onsets_and_durations']) for x in comparisons], flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='works/ravel-mother-goose/analysis/musicxml/score-20261026')
    parser.add_argument('--ingest-cache', type=Path, help='Optional local source- and code-fingerprint-bound parse envelope')
    args = parser.parse_args()
    build(ROOT / args.output, args.ingest_cache)
