"""Apply a source-reviewed physical-to-logical staff map to a separate OMR copy.

This never infers instrument identity from ordinal position on an unreviewed
page, nor adjusts pitches, rhythm or transposition.
"""
from copy import deepcopy
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

from .pipeline import digest, write_json
from .musicxml import inspect_musicxml, read_musicxml


def map_musicxml(source, source_book, destination, mapping_path, pdf_sha256, sheet_page_offset=0):
    """Rebind complete page segments using a reviewed map; preserve sounding notes.

    Audiveris can rebuild its score model during export, discarding external
    logical assignments. This independent export works on its actual MusicXML
    and retains source attribute context at each segment boundary.
    """
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination:
        raise ValueError('Mapping must preserve raw MusicXML')
    mapping = json.loads(Path(mapping_path).read_text(encoding='utf8'))
    if mapping['source_pdf_sha256'] != pdf_sha256:
        raise ValueError('Part mapping belongs to another source PDF')
    canonical = {p['id']: p for p in mapping['logical_parts']}
    reviewed = {(s['pdf_page'], s['page_id'], s['system_index']): s for s in mapping['systems']}
    _, original = read_musicxml(source)
    raw_parts = {p.get('id'): p for p in original.findall('part')}
    contexts = {}
    for part_id, part in raw_parts.items():
        inherited, per_measure = {}, []
        for measure in part.findall('measure'):
            per_measure.append(deepcopy(inherited))
            for attrs in measure.findall('attributes'):
                for attr in attrs:
                    key = (attr.tag, attr.get('number'))
                    inherited[key] = deepcopy(attr)
        contexts[part_id] = per_measure
    with zipfile.ZipFile(source_book) as archive:
        book = ET.fromstring(archive.read('book.xml'))
    scores = book.findall('score')
    if len(scores) != 1:
        raise ValueError('Reviewed export requires one score')
    segments, first_measure = [], 0
    for ref in scores[0].findall('page'):
        sheet_number, page_id = int(ref.get('sheet-number')), int(ref.get('sheet-page-id'))
        page = book.find(f'./sheet[@number="{sheet_number}"]/page[@id="{page_id}"]')
        if page is None or len(page.findall('system')) != 1:
            raise ValueError('This reviewed export currently requires one system per source page')
        key = (sheet_number + sheet_page_offset, page_id, 1)
        if key not in reviewed:
            raise ValueError(f'Unreviewed source page {key}')
        physical = page.findall('system/part')
        ids = reviewed[key]['logical_ids']
        if len(ids) != len(physical) or len(ids) != len(set(ids)):
            raise ValueError('Part count differs from reviewed source')
        length = int(page.get('delta-measure-id', '0'))
        if length <= 0:
            raise ValueError('Missing source page measure span')
        sources = {}
        for node, canonical_id in zip(physical, ids):
            if canonical_id not in canonical:
                raise ValueError('Undefined canonical part')
            if [int(s.get('line-count')) for s in node.findall('staff-configuration')] != canonical[canonical_id]['staff_lines']:
                raise ValueError('Reviewed staff configuration mismatch')
            raw_id = 'P' + node.get('logical-id')
            if raw_id not in raw_parts:
                raise ValueError('OMR and raw MusicXML part IDs differ')
            sources[canonical_id] = raw_id
        segments.append({'page': key[0], 'start': first_measure, 'end': first_measure + length,
                         'sources': sources})
        first_measure += length
    if not segments or any(len(p.findall('measure')) != first_measure for p in raw_parts.values()):
        raise ValueError('OMR page spans and MusicXML measures disagree')
    output = deepcopy(original)
    old_list = output.find('part-list')
    if old_list is None:
        raise ValueError('MusicXML has no part-list')
    list_position = list(output).index(old_list)
    output.remove(old_list)
    for part in output.findall('part'):
        output.remove(part)
    part_list = ET.Element('part-list')
    output.insert(list_position, part_list)
    for canonical_id in sorted({c for s in segments for c in s['sources']}):
        info = canonical[canonical_id]
        part_id = f'P{canonical_id}'
        definition = ET.SubElement(part_list, 'score-part', id=part_id)
        ET.SubElement(definition, 'part-name').text = info['name']
        ET.SubElement(definition, 'part-abbreviation').text = info['abbreviation']
        part = ET.SubElement(output, 'part', id=part_id)
        for segment in segments:
            raw_id = segment['sources'].get(canonical_id)
            if raw_id is None:
                active = set(segment['sources'].values())
                raw_id = next((pid for pid, p in raw_parts.items() if pid not in active and
                    all(n.find('rest') is not None for m in p.findall('measure')[segment['start']:segment['end']]
                        for n in m.findall('note'))), None)
                if raw_id is None:
                    raise ValueError('No verified silent template for absent staff')
            measures = raw_parts[raw_id].findall('measure')
            for index in range(segment['start'], segment['end']):
                measure = deepcopy(measures[index])
                if index == segment['start']:
                    attrs = ET.Element('attributes')
                    for value in contexts[raw_id][index].values():
                        attrs.append(deepcopy(value))
                    insertion = 1 if measure.find('print') is not None else 0
                    if len(attrs):
                        measure.insert(insertion, attrs)
                # A per-note instrument reference must not point into a removed
                # raw part-list. No playback instrument assignment is invented.
                for note in measure.findall('note'):
                    for instrument in note.findall('instrument'):
                        note.remove(instrument)
                part.append(measure)
    # Exact note content must survive staff rebinding, including duration/type.
    from collections import Counter
    signature = lambda root: Counter(tuple(n.findtext(t, '') for t in
        ('pitch/step', 'pitch/alter', 'pitch/octave', 'unpitched/display-step',
         'unpitched/display-octave', 'duration', 'type'))
        for n in root.findall('.//note') if n.find('rest') is None)
    if signature(original) != signature(output):
        raise ValueError('Reviewed mapping would change sounding note content')
    destination.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(output).write(destination, encoding='utf-8', xml_declaration=True)
    validation = inspect_musicxml(destination)
    if not validation['structurally_valid']:
        raise ValueError('Mapped MusicXML failed structural validation')
    report = {'source_musicxml': str(source), 'source_omr': str(Path(source_book).resolve()),
              'source_sha256': digest(source), 'output': str(destination),
              'output_sha256': digest(destination), 'mapping_sha256': digest(mapping_path),
              'source_pdf_pages': [s['page'] for s in segments],
              'segments': segments, 'pitched_note_content_preserved': True,
              'musical_accuracy_verified': False, 'validation': validation,
              'scope': 'Reviewed staff identities only; no pitch, meter, rhythm or transpose correction'}
    write_json(destination.with_suffix('.review.json'), report)
    return report
