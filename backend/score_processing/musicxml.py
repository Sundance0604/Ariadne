"""Read compressed/uncompressed MusicXML and report structural OMR risks.

This is a diagnostic, not a certificate of musical accuracy or XSD validation.
"""
from collections import Counter
from fractions import Fraction
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile
from copy import deepcopy
from contextlib import contextmanager
import shutil

MAX_XML_BYTES = 128 * 1024 * 1024
STREAM_XML_BYTES = 512 * 1024 * 1024
STREAM_THRESHOLD = 16 * 1024 * 1024


@contextmanager
def xml_stream(path):
    path = Path(path)
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            container = ET.fromstring(archive.read('META-INF/container.xml'))
            roots = [e.get('full-path') for e in container.iter()
                     if e.tag.rsplit('}', 1)[-1] == 'rootfile' and
                     e.get('media-type') == 'application/vnd.recordare.musicxml+xml']
            if len(roots) != 1:
                raise ValueError('MXL must declare one MusicXML rootfile')
            info = archive.getinfo(roots[0])
            if info.file_size > STREAM_XML_BYTES:
                raise ValueError('MusicXML exceeds streaming size limit')
            with archive.open(info) as stream:
                yield stream, info.file_size
    else:
        if path.stat().st_size > STREAM_XML_BYTES:
            raise ValueError('MusicXML exceeds streaming size limit')
        with path.open('rb') as stream:
            yield stream, path.stat().st_size


def extract_musicxml(source, destination):
    with xml_stream(source) as (stream, _), Path(destination).open('wb') as output:
        shutil.copyfileobj(stream, output, 1024 * 1024)


def _inspect_stream(path, expected_staves, expected_measures):
    definitions, ids, reports = {}, [], []
    with xml_stream(path) as (stream, _):
        final_tag = None
        for _, element in ET.iterparse(stream, events=('end',)):
            element.tag = element.tag.rsplit('}', 1)[-1]
            final_tag = element.tag
            if element.tag == 'score-part':
                definitions[element.get('id')] = deepcopy(element)
            elif element.tag == 'part':
                part_id = element.get('id')
                ids.append(part_id)
                root = ET.Element('score-partwise')
                listing = ET.SubElement(root, 'part-list')
                if part_id in definitions:
                    listing.append(deepcopy(definitions[part_id]))
                root.append(element)
                reports.append(_inspect_root(root))
                element.clear()
        if final_tag != 'score-partwise':
            raise ValueError('Expected score-partwise MusicXML')
    if not reports:
        return _inspect_root(ET.Element('score-partwise'), expected_staves, expected_measures)
    result = dict(reports[0])
    result['parts'] = [p for r in reports for p in r['parts']]
    result['errors'] = [e for r in reports for e in r['errors'] if e != 'No sounding note data']
    result['issues'] = [e for r in reports for e in r['issues']]
    if len(ids) != len(set(ids)) or set(ids) != set(definitions):
        result['errors'].append('Missing, duplicate or inconsistent part IDs')
    for key in ('part_count', 'staff_count', 'note_elements', 'pitched_notes',
                'unpitched_notes', 'sounding_notes', 'rests'):
        result[key] = sum(r[key] for r in reports)
    if not result['sounding_notes']:
        result['errors'].append('No sounding note data')
    result['time_signatures'] = sorted({t for r in reports for t in r['time_signatures']})
    counts = sorted({p['measures'] for p in result['parts']})
    result['measure_counts_per_part'] = counts
    if len(counts) > 1:
        result['issues'].append({'kind': 'inconsistent_measure_counts', 'counts': counts})
    if expected_staves is not None and result['staff_count'] != expected_staves:
        result['issues'].append({'kind': 'staff_count_mismatch', 'expected': expected_staves,
                                 'actual': result['staff_count']})
    if expected_measures is not None and counts != [expected_measures]:
        result['issues'].append({'kind': 'measure_count_mismatch', 'expected': expected_measures,
                                 'actual': counts})
    result['structurally_valid'] = not result['errors']
    result['issue_count'] = len(result['issues'])
    return result


def read_musicxml(path):
    path = Path(path)
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            container = ET.fromstring(archive.read('META-INF/container.xml'))
            roots = [e.attrib['full-path'] for e in container.iter()
                     if e.tag.rsplit('}', 1)[-1] == 'rootfile'
                     and e.attrib.get('media-type') == 'application/vnd.recordare.musicxml+xml']
            if len(roots) != 1:
                raise ValueError('MXL must declare one MusicXML rootfile')
            info = archive.getinfo(roots[0])
            if info.file_size > MAX_XML_BYTES:
                raise ValueError('MusicXML exceeds size limit')
            data = archive.read(info)
    else:
        if path.stat().st_size > MAX_XML_BYTES:
            raise ValueError('MusicXML exceeds size limit')
        data = path.read_bytes()
    root = ET.fromstring(data)
    for element in root.iter():
        element.tag = element.tag.rsplit('}', 1)[-1]
    if root.tag != 'score-partwise':
        raise ValueError('Expected score-partwise MusicXML')
    return data, root


def inspect_musicxml(path, expected_staves=None, expected_measures=None):
    with xml_stream(path) as (_, size):
        if size > STREAM_THRESHOLD:
            return _inspect_stream(path, expected_staves, expected_measures)
    _, root = read_musicxml(path)
    return _inspect_root(root, expected_staves, expected_measures)


def _inspect_root(root, expected_staves=None, expected_measures=None):
    definitions = {e.get('id'): e.findtext('part-name', '')
                   for e in root.findall('./part-list/score-part')}
    parts, errors, issues = [], [], []
    ids = [p.get('id') for p in root.findall('part')]
    if not ids or len(ids) != len(set(ids)) or set(ids) != set(definitions):
        errors.append('Missing, duplicate or inconsistent part IDs')
    meters = set()
    for part in root.findall('part'):
        divisions, expected, staves = None, None, 1
        counts = Counter()
        measures = part.findall('measure')
        for sequence, measure in enumerate(measures, 1):
            cursor, last_start = Fraction(0), Fraction(0)
            voice_ends = {}
            for item in measure:
                if item.tag == 'attributes':
                    if item.find('divisions') is not None:
                        divisions = int(item.findtext('divisions'))
                        if divisions <= 0:
                            raise ValueError('Non-positive divisions')
                    staves = max(staves, int(item.findtext('staves', '1')))
                    time = item.find('time')
                    if time is not None and time.find('beats') is not None:
                        beats, units = time.findall('beats'), time.findall('beat-type')
                        expected = sum((sum(Fraction(b) for b in beat.text.split('+'))
                                        * 4 / int(unit.text)
                                        for beat, unit in zip(beats, units)), Fraction(0))
                        meters.add('+'.join(f'{b.text}/{u.text}' for b, u in zip(beats, units)))
                elif item.tag in ('backup', 'forward', 'note'):
                    is_note = item.tag == 'note'
                    if is_note:
                        counts['note_elements'] += 1
                        counts['rests' if item.find('rest') is not None else 'sounding_notes'] += 1
                        counts['pitched_notes'] += item.find('pitch') is not None
                        counts['unpitched_notes'] += item.find('unpitched') is not None
                        counts['grace_notes'] += item.find('grace') is not None
                        staves = max(staves, int(item.findtext('staff', '1')))
                        if item.find('grace') is not None:
                            continue
                    raw = item.findtext('duration')
                    if raw is None or divisions is None:
                        issues.append({'part': part.get('id'), 'measure': sequence,
                                       'kind': 'missing_duration_or_divisions'})
                        continue
                    duration = Fraction(raw) / divisions
                    if duration < 0:
                        raise ValueError('Negative duration')
                    if item.tag == 'backup':
                        cursor -= duration
                        if cursor < 0:
                            issues.append({'part': part.get('id'), 'measure': sequence,
                                           'kind': 'negative_musicxml_cursor'})
                    elif item.tag == 'forward':
                        cursor += duration
                    else:
                        chord = item.find('chord') is not None
                        start = last_start if chord else cursor
                        voice = (item.findtext('staff', '1'), item.findtext('voice', '1'))
                        voice_ends[voice] = max(voice_ends.get(voice, Fraction(0)), start + duration)
                        if not chord:
                            last_start, cursor = start, start + duration
            if expected is not None and measure.get('implicit') != 'yes':
                for (staff, voice), end in voice_ends.items():
                    if end != expected:
                        issues.append({'part': part.get('id'), 'measure': sequence,
                                       'xml_number': measure.get('number'), 'staff': staff,
                                       'voice': voice, 'kind': 'voice_extent_differs_from_meter',
                                       'expected_quarters': str(expected), 'actual_quarters': str(end)})
        if not measures:
            errors.append(f'Part {part.get("id")} has no measures')
        if expected is None:
            issues.append({'part': part.get('id'), 'kind': 'missing_time_signature',
                           'detail': 'Cannot check durations against meter; do not assume 4/4.'})
        parts.append({'id': part.get('id'), 'name': definitions.get(part.get('id'), ''),
                      'measures': len(measures), 'staves': staves, **dict(counts)})
    total = {key: sum(p.get(key, 0) for p in parts)
             for key in ('note_elements', 'pitched_notes', 'unpitched_notes', 'sounding_notes', 'rests')}
    if not total['sounding_notes']:
        errors.append('No sounding note data')
    measure_counts = sorted({p['measures'] for p in parts})
    if len(measure_counts) > 1:
        issues.append({'kind': 'inconsistent_measure_counts', 'counts': measure_counts})
    staves = sum(p['staves'] for p in parts)
    if expected_staves is not None and staves != expected_staves:
        issues.append({'kind': 'staff_count_mismatch', 'expected': expected_staves, 'actual': staves})
    if expected_measures is not None and measure_counts != [expected_measures]:
        issues.append({'kind': 'measure_count_mismatch', 'expected': expected_measures,
                       'actual': measure_counts})
    return {'structurally_valid': not errors, 'errors': errors, 'part_count': len(parts),
            'staff_count': staves, 'measure_counts_per_part': measure_counts,
            'time_signatures': sorted(meters), **total, 'parts': parts,
            'issues': issues, 'issue_count': len(issues),
            'quality_status': 'needs_manual_review', 'musical_accuracy_verified': False,
            'limitations': ['No pitch-by-pitch comparison or XSD validation.',
                            'Parts can combine several instruments; counts are not accuracy scores.',
                            'Voice extent differences are review hints, not proof of rhythm errors.',
                            'Page-local measure numbers are not original full-score measure numbers.']}
