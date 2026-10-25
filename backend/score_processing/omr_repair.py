"""Conservative repair of a specific Audiveris 5.11 MEASURES/CHORDS failure.

An empty measure ending *before* its staff begins is not a musical pickup.
Move that barline to the part's starting barline, then rebuild empty measure
stack bounds. Never change recognized heads, rests, stems, pitches or durations.
"""
from collections import Counter
from copy import deepcopy
from pathlib import Path
from statistics import median
import xml.etree.ElementTree as ET
import zipfile

from .pipeline import digest, write_json


def repair_sheet(root):
    changes = []
    for system in root.findall('.//system'):
        parts, stacks = system.findall('part'), system.findall('stack')
        if not parts or not stacks or any(len(stack) for stack in stacks):
            continue
        nodes = {e.get('id'): e for e in system.findall('./sig/inters/*')}
        counts = Counter(len(p.findall('measure')) for p in parts)
        usual = counts.most_common(1)[0][0]
        if set(counts) != {usual, usual + 1} or len(stacks) != usual + 1:
            continue
        repairs = []
        for part in parts:
            measures = part.findall('measure')
            if len(measures) == usual:
                continue
            first = measures[0]
            bar = first.find('right-barline')
            # Require an otherwise empty initial measure, no starting barline,
            # and a right barline wholly to the left of every associated staff.
            if (bar is None or len(first) != 1 or part.find('left-barline') is not None
                    or not part.findall('staff')):
                repairs = []
                break
            refs = (bar.findtext('staff-barlines') or '').split()
            left = min(float(s.get('left')) for s in part.findall('staff'))
            bounds = [nodes[r].find('bounds') for r in refs if r in nodes]
            if (len(bounds) != len(refs) or not bounds or any(b is None for b in bounds)
                    or any(float(b.get('x')) + float(b.get('w')) >= left for b in bounds)):
                repairs = []
                break
            repairs.append((part, first, bar))
        if not repairs:
            continue
        # Validate all remaining barline coordinates before modifying anything.
        right_edges = []
        for i in range(usual):
            edges = []
            for part in parts:
                measures = part.findall('measure')
                measure = measures[i + (len(measures) == usual + 1)]
                refs = (measure.findtext('right-barline/staff-barlines') or '').split()
                for ref in refs:
                    if ref in nodes and nodes[ref].find('bounds') is not None:
                        b = nodes[ref].find('bounds')
                        edges.append(float(b.get('x')) + float(b.get('w')) / 2)
            if not edges and i == usual - 1:
                # An open final measure ends at the staff's right edge.
                edges = [float(staff.get('right')) for p in parts for staff in p.findall('staff')]
            if not edges:
                right_edges = []
                break
            right_edges.append(round(median(edges)))
        left = round(min(float(s.get('left')) for p in parts for s in p.findall('staff')))
        if not right_edges or [left, *right_edges] != sorted(set([left, *right_edges])):
            continue
        for part, first, bar in repairs:
            starting = deepcopy(bar)
            starting.tag = 'left-barline'
            part.insert(list(part).index(first), starting)
            part.remove(first)
            for i, measure in enumerate(part.findall('measure'), 1):
                measure.set('id', str(i))
        for stack in stacks:
            system.remove(stack)
        insertion = next((i for i, e in enumerate(system) if e.tag == 'sig'), len(system))
        for i, right in enumerate(right_edges):
            system.insert(insertion + i, ET.Element('stack', id=str(i + 1),
                          left=str(left if i == 0 else right_edges[i - 1]), right=str(right)))
        # A failed CHORDS step can have partially built containers. Discard only
        # these derived containers/edges, so the engine rebuilds them once.
        derived = {e.get('id') for e in system.findall('./sig/inters/*')
                   if e.tag in ('head-chord', 'rest-chord', 'small-chord')}
        for parent in system.iter():
            for element in list(parent):
                if (element.get('id') in derived
                        or element.tag in ('head-chords', 'rest-chords')
                        or (element.tag == 'relation' and
                            (element.get('source') in derived or element.get('target') in derived))):
                    parent.remove(element)
        changes.append({'system': system.get('id'), 'parts': [p.get('id') for p, _, _ in repairs],
                        'removed_empty_leading_measures': len(repairs), 'measure_count': usual,
                        'stack_boundaries': [left, *right_edges],
                        'rebuilt_derived_chord_containers': len(derived)})
    return changes


def repair_book(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination:
        raise ValueError('Repair must use a separate book, preserving the original')
    changes, replacements = [], {}
    with zipfile.ZipFile(source) as archive:
        book = ET.fromstring(archive.read('book.xml'))
        for stub in book.findall('sheet'):
            steps = (stub.findtext('steps') or '').split()
            if 'MEASURES' not in steps or 'CHORDS' in steps:
                continue
            number = int(stub.get('number'))
            entry = f'sheet#{number}/sheet#{number}.xml'
            root = ET.fromstring(archive.read(entry))
            # Preserve recognized note/rest identities exactly.
            recognized = lambda r: {(e.tag, e.get('id')) for e in r.findall('.//sig/inters/*')
                                    if e.tag in ('head', 'rest', 'stem')}
            before = recognized(root)
            edits = repair_sheet(root)
            if edits:
                if before != recognized(root):
                    raise ValueError('Repair unexpectedly changed recognized note/rest/stem identities')
                changes.append({'sheet': number, 'edits': edits})
                replacements[entry] = ET.tostring(root, encoding='utf-8', xml_declaration=True)
        if not changes:
            return None
        destination.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED) as output:
            for info in archive.infolist():
                output.writestr(info.filename, replacements.get(info.filename, archive.read(info.filename)))
    report = {'source': str(source), 'source_sha256': digest(source), 'output': str(destination),
              'output_sha256': digest(destination), 'changes': changes,
              'kind': 'empty_measure_before_staff_start', 'musical_accuracy_verified': False}
    write_json(destination.with_suffix('.repair.json'), report)
    return report
