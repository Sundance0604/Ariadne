"""Inventory the supplied Op.96 edition; no recording clock or playback mutation.

Optional processing packages: music21, pypdfium2. Run from repository root.
All musical positions remain rational and local to the encoded measure.
"""
from collections import Counter, defaultdict
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.compare_mother_goose_sources import xml_events
from backend.musicxml_analysis.ingest import xml_root, pitch_record
from backend.musicxml_analysis.analyze import chord_description

BASE = ROOT / 'resource/American'
OUT = ROOT / 'works/dvorak-american/analysis'
TMP = ROOT / 'tmp/dvorak-american'


def record(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return {'path': path.relative_to(ROOT).as_posix(), 'sha256': h.hexdigest(),
            'bytes': path.stat().st_size}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


def build():
    import music21
    import pypdfium2 as pdfium
    from PIL import Image, ImageDraw
    OUT.mkdir(parents=True, exist_ok=True)
    TMP.mkdir(parents=True, exist_ok=True)
    source = next(BASE.glob('*.mxl'))
    pdf_path = next(BASE.glob('*.pdf'))
    root, _ = xml_root(source)
    data = xml_events(source)
    parts = {p['id']: p['name'] for p in data['parts']}
    if list(parts.values()) != ['Violin 1', 'Violin 2', 'Viola', 'Violoncello']:
        raise ValueError('Reassess supplied part identities')
    measures_by_part = {p.get('id'): p.findall('measure') for p in root.findall('part')}
    top = next(iter(measures_by_part.values()))
    if len(set(map(len, measures_by_part.values()))) != 1:
        raise ValueError('Part measure counts differ')
    elements = {}
    extents = defaultdict(dict)
    directives = defaultdict(list)
    for pid, measures in measures_by_part.items():
        divisions = None
        for seq, m in enumerate(measures, 1):
            cursor = F(0)
            maximum = F(0)
            for child in m:
                if child.tag == 'attributes' and child.find('divisions') is not None:
                    divisions = int(child.findtext('divisions'))
                elif child.tag in ('backup', 'forward'):
                    cursor += (1 if child.tag == 'forward' else -1) * F(child.findtext('duration', '0')) / divisions
                elif child.tag == 'note' and child.find('chord') is None and child.find('grace') is None:
                    cursor += F(child.findtext('duration', '0')) / divisions
                    maximum = max(maximum, cursor)
            extents[seq][pid] = str(maximum)
            for n, note in enumerate(m.findall('note'), 1):
                elements[f'{pid}-xml-m{seq:04d}-n{n:04d}'] = note
            for d in m.findall('direction'):
                value = {'part_id': pid, 'words': [w.text for w in d.findall('direction-type/words') if w.text],
                         'dynamics': [x.tag for x in d.findall('direction-type/dynamics/*')],
                         'other_dynamics_text': [x.text for x in d.findall('direction-type/dynamics/other-dynamics') if x.text],
                         'octave_shifts': [dict(x.attrib) for x in d.findall('direction-type/octave-shift')],
                         'offset_q': str(F(d.findtext('offset', '0')) / divisions),
                         'wedge': [x.attrib for x in d.findall('direction-type/wedge')],
                         'sound': [x.attrib for x in d.findall('sound')]}
                if any(value[k] for k in ('words', 'dynamics', 'wedge', 'sound', 'octave_shifts')):
                    directives[seq].append(value)
    events = []
    by_seq = defaultdict(list)
    for e in data['events']:
        node = elements[e['id']]
        p = node.find('pitch')
        pitch = music21.pitch.Pitch()
        pitch.step = p.findtext('step')
        pitch.octave = int(p.findtext('octave'))
        pitch.accidental = float(p.findtext('alter', '0'))
        # This edition has no explicit transposing instruments; fail rather than guessing.
        if F(e['transpose_semitones']) != 0:
            raise ValueError('Unexpected transposition')
        item = {**e, 'concert_pitch': pitch_record(pitch),
                'ties': [x.get('type') for x in node.findall('tie')],
                'tremolo': [dict(x.attrib, strokes=x.text) for x in node.findall('notations/ornaments/tremolo')],
                'articulations': [x.tag for x in node.findall('notations/articulations/*')],
                'notations_xml': [ET.tostring(x, encoding='unicode') for x in node.findall('notations')]}
        events.append(item)
        by_seq[e['sequence']].append(item)
    page = 1
    system = 0
    movement = 0
    rows = []
    meters = {}
    keys = {}
    for seq, m in enumerate(top, 1):
        if m.get('number') == '1':
            movement += 1
        printing = m.find('print')
        if printing is not None:
            if printing.get('new-page') == 'yes':
                page += 1
                system = 0
            elif printing.get('new-system') == 'yes':
                system += 1
        for attr in m.findall('attributes'):
            if attr.find('time') is not None:
                meters = {x.tag: x.text for x in attr.find('time')}
            if attr.find('key') is not None:
                keys = {x.tag: x.text for x in attr.find('key')}
        notes = [e for e in by_seq[seq] if e['eligible']]
        rows.append({'measure_id': f'xml-m{seq:04d}', 'sequence': seq, 'movement': movement,
                     'local_number': m.get('number'), 'xml_layout_page': page,
                     'xml_layout_system': system, 'pdf_map_status': 'layout_candidate_not_independent_geometry',
                     'meter': dict(meters), 'key_signature': dict(keys),
                     'part_extents_q': extents[seq],
                     'extent_agreement': len(set(extents[seq].values())) == 1,
                     'directions': directives[seq],
                     'barlines': [ET.tostring(x, encoding='unicode') for x in m.findall('barline')],
                     'pitched_note_counts_by_part': dict(Counter(e['part_id'] for e in notes)),
                     'part_ranges_midi': {pid: [min(float(e['concert_ps']) for e in notes if e['part_id'] == pid),
                                               max(float(e['concert_ps']) for e in notes if e['part_id'] == pid)]
                                          for pid in parts if any(e['part_id'] == pid for e in notes)}})
    write(OUT / 'measure-index.json', {'source': record(source), 'parts': parts, 'measures': rows})
    write(OUT / 'musicxml/events.json', {'source': record(source), 'parts': parts, 'events': events,
                                       'clock': 'measure-local rational quarters, no recording seconds',
                                       'tie_policy': 'source tie segments retained; not acoustic releases'})
    pdf = pdfium.PdfDocument(pdf_path)
    pdf_info = []
    for i in range(len(pdf)):
        p = pdf[i]
        textpage = p.get_textpage()
        txt = textpage.get_text_range()
        pdf_info.append({'physical_page': i + 1, 'width_pt': p.get_width(), 'height_pt': p.get_height(), 'text': txt})
        (TMP / f'page-{i+1:02}.txt').write_text(txt, encoding='utf8')
        image = p.render(scale=1.4).to_pil().convert('RGB')
        image.save(TMP / f'page-{i+1:02}.png')
    for start in range(0, len(pdf), 6):
        sheet = Image.new('RGB', (1200, 1700), '#dddddd')
        draw = ImageDraw.Draw(sheet)
        for j in range(start, min(start + 6, len(pdf))):
            image = Image.open(TMP / f'page-{j+1:02}.png')
            image.thumbnail((590, 525))
            x, y = (j-start) % 2 * 600, (j-start) // 2 * 565
            sheet.paste(image, (x, y + 25))
            draw.text((x+8, y+4), f'Physical page {j+1}', fill='black')
        sheet.save(TMP / f'contact-{start+1:02}.png')
    write(OUT / 'pdf-inventory.json', {'source': record(pdf_path), 'page_count': len(pdf), 'pages': pdf_info,
                                     'layout_candidate_pages': page, 'independent_note_geometry': False})
    windows = []
    selections = {1: [1, 3, 17, 26, 36, 43, 44, 59, 60, 64, 84, 108, 116, 132, 156, 168, 178],
                  2: [1, 2, 10, 19, 29, 39, 48, 58, 67, 78, 82, 90, 97],
                  3: [1, 2, 21, 41, 49, 57, 58, 59, 61, 62, 97, 145, 173, 196],
                  4: [1, 4, 26, 33, 50, 51, 67, 69, 99, 123, 179, 219, 280, 315, 350, 382]}
    for row in rows:
        if int(row['local_number']) not in selections[row['movement']]:
            continue
        eligible = [e for e in by_seq[row['sequence']] if e['eligible']]
        points = sorted({F(0), *(F(e['onset_q']) for e in eligible)})
        # Several actual positions, not a union of a whole bar.
        for offset in points[:4]:
            active = [e for e in eligible if F(e['onset_q']) <= offset < F(e['onset_q']) + F(e['duration_q'])]
            windows.append({'id': f'M{row["movement"]}-{row["local_number"]}-q{offset}',
                            'sequence': row['sequence'], 'movement': row['movement'],
                            'local_number': row['local_number'], 'offset_q': str(offset),
                            'extent_agreement': row['extent_agreement'],
                            'event_ids': [e['id'] for e in active], 'selected_events': active,
                            'tremolo_encoding_event_ids': [e['id'] for e in active if e['tremolo']],
                            'sonority': chord_description(active) if row['extent_agreement'] else None,
                            'status': 'encoded_interval_slice_tremolo_requires_notation_review' if any(e['tremolo'] for e in active) else 'local_source_sonority_not_functional_reduction',
                            'human_signoff': None})
    write(OUT / 'score-studies.json', {'method': 'unchanged existing chord_description; half-open written intervals',
                                     'windows': windows, 'human_signoff': None, 'expert_review': None})
    write(OUT / 'symbolic-source-summary.json', {'source': record(source), 'title': data['title'],
          'declared_source': data['declared_source'], 'software': data['software'], 'parts': data['parts'],
          'part_measure_counts': data['part_measure_counts'], 'pitched_events': len(events),
          'eligible_events': sum(e['eligible'] for e in events), 'parser_anomalies': data['anomalies'],
          'extent_disagreements': [r['sequence'] for r in rows if not r['extent_agreement']],
          'movements': [{'movement': mv, 'first_sequence': min(r['sequence'] for r in rows if r['movement'] == mv),
                         'last_sequence': max(r['sequence'] for r in rows if r['movement'] == mv),
                         'count': sum(r['movement'] == mv for r in rows),
                         'xml_layout_page_range': [min(r['xml_layout_page'] for r in rows if r['movement'] == mv),
                                                   max(r['xml_layout_page'] for r in rows if r['movement'] == mv)]}
                        for mv in range(1, 5)],
          'midi': record(next(BASE.glob('*.mid'))), 'pdf': record(pdf_path),
          'playback_activation': False, 'recording_projection': None})
    # Human-readable research aid contains every local measure, without musical claims.
    lines = []
    for r in rows:
        seq = r['sequence']
        fragments = []
        for pid in parts:
            es = sorted([e for e in by_seq[seq] if e['eligible']], key=lambda e: (F(e['onset_q']), F(e['concert_ps'])))
            es = [e for e in es if e['part_id'] == pid]
            fragments.append(pid + ':' + ' '.join(f'{e["concert_pitch"]["name"]}@{e["onset_q"]}/{e["duration_q"]}' for e in es))
        ds = ['%s:%s:%s' % (d['part_id'], ','.join(d['words']), ','.join(d['dynamics'])) for d in r['directions']]
        lines.append(f'M{r["movement"]} m{r["local_number"]} seq{seq} p{r["xml_layout_page"]} {r["meter"]} KEY{r["key_signature"]} ' + ' | '.join(fragments) + ' DIR' + str(ds))
    (TMP / 'all-measures.txt').write_text('\n'.join(lines), encoding='utf8')
    print(json.dumps({'measures': len(rows), 'notes': len(events), 'pdf_pages': len(pdf), 'layout_pages': page,
                      'extent_disagreements': [r['sequence'] for r in rows if not r['extent_agreement']],
                      'windows': len(windows)}, ensure_ascii=False))


if __name__ == '__main__':
    build()
