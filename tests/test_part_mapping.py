from pathlib import Path
import json
import shutil
import sys
import unittest
from uuid import uuid4
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.score_processing.part_mapping import map_musicxml
from backend.score_processing.musicxml import read_musicxml
from backend.score_processing.pipeline import digest


class PartMappingTests(unittest.TestCase):
    def setUp(self):
        self.folder = ROOT / 'tmp' / f'part-mapping-test-{uuid4().hex}'
        self.folder.mkdir(parents=True)
        self.addCleanup(self.cleanup)
        self.xml, self.book, self.mapping = [self.folder / n for n in ('raw.musicxml', 'source.omr', 'map.json')]
        note = lambda pitch, duration: (f'<note><pitch><step>{pitch}</step><octave>4</octave></pitch>'
                                       f'<duration>{duration}</duration><type>quarter</type></note>')
        rest = lambda duration: f'<note><rest/><duration>{duration}</duration><type>quarter</type></note>'
        root = ET.Element('score-partwise', version='4.0')
        parts = ET.SubElement(root, 'part-list')
        for pid, divisions, items in [('P1', 1, [note('C', 1), rest(1)]),
                                      ('P2', 1, [note('G', 1), note('A', 1)]),
                                      ('P3', 2, [rest(2), note('E', 2)])]:
            ET.SubElement(ET.SubElement(parts, 'score-part', id=pid), 'part-name').text = pid
            part = ET.SubElement(root, 'part', id=pid)
            for i, item in enumerate(items, 1):
                measure = ET.SubElement(part, 'measure', number=str(i))
                if i == 1:
                    attrs = ET.SubElement(measure, 'attributes')
                    ET.SubElement(attrs, 'divisions').text = str(divisions)
                    time = ET.SubElement(attrs, 'time')
                    ET.SubElement(time, 'beats').text = '1'
                    ET.SubElement(time, 'beat-type').text = '4'
                measure.append(ET.fromstring(item))
        ET.ElementTree(root).write(self.xml, encoding='utf-8', xml_declaration=True)
        book = ET.Element('book')
        for i, ids in [(1, [1, 2]), (2, [3, 2])]:
            sheet = ET.SubElement(book, 'sheet', number=str(i))
            ET.SubElement(sheet, 'steps').text = 'PAGE'
            system = ET.SubElement(ET.SubElement(sheet, 'page', id='1', **{'delta-measure-id': '1'}), 'system')
            for logical_id in ids:
                part = ET.SubElement(system, 'part', **{'logical-id': str(logical_id)})
                ET.SubElement(part, 'staff-configuration', **{'line-count': '5'})
        score = ET.SubElement(book, 'score')
        for i in (1, 2):
            ET.SubElement(score, 'page', **{'sheet-number': str(i), 'sheet-page-id': '1'})
        self.book_xml = book
        self.write_book()
        self.plan = {'source_pdf_sha256': 'expected-pdf', 'logical_parts': [
            {'id': 1, 'name': 'Flûtes', 'abbreviation': 'Fl.', 'staff_lines': [5]},
            {'id': 2, 'name': 'Strings', 'abbreviation': 'Str.', 'staff_lines': [5]}],
            'systems': [{'pdf_page': i, 'page_id': 1, 'system_index': 1, 'logical_ids': [1, 2]}
                        for i in (1, 2)]}
        self.write_mapping()

    def write_book(self):
        with zipfile.ZipFile(self.book, 'w') as z:
            z.writestr('book.xml', ET.tostring(self.book_xml, encoding='utf-8'))

    def write_mapping(self):
        self.mapping.write_text(json.dumps(self.plan, ensure_ascii=False), encoding='utf8')

    def convert(self):
        return map_musicxml(self.xml, self.book, self.folder / 'mapped.musicxml', self.mapping, 'expected-pdf')

    def cleanup(self):
        self.assertEqual(self.folder.resolve().parent, (ROOT / 'tmp').resolve())
        shutil.rmtree(self.folder)

    def test_reviewed_page_mapping_preserves_notes_and_division_context(self):
        original_sha = digest(self.xml)
        report = self.convert()
        self.assertEqual(report['validation']['part_count'], 2)
        self.assertEqual(report['validation']['pitched_notes'], 4)
        self.assertEqual(report['validation']['issue_count'], 0)
        self.assertTrue(report['pitched_note_content_preserved'])
        _, root = read_musicxml(report['output'])
        self.assertEqual(root.findtext('./part-list/score-part/part-name'), 'Flûtes')
        self.assertEqual(root.findtext('./part[@id="P1"]/measure[@number="2"]/attributes/divisions'), '2')
        self.assertEqual(root.findtext('./part[@id="P1"]/measure[@number="2"]/note/pitch/step'), 'E')
        self.assertEqual(digest(self.xml), original_sha)

    def test_unreviewed_page_is_rejected(self):
        self.plan['systems'].pop()
        self.write_mapping()
        with self.assertRaisesRegex(ValueError, 'Unreviewed'):
            self.convert()

    def test_wrong_source_and_part_count_are_rejected(self):
        self.plan['source_pdf_sha256'] = 'other'
        self.write_mapping()
        with self.assertRaisesRegex(ValueError, 'another source'):
            self.convert()
        self.plan['source_pdf_sha256'] = 'expected-pdf'
        self.plan['systems'][0]['logical_ids'] = [1]
        self.write_mapping()
        with self.assertRaisesRegex(ValueError, 'Part count'):
            self.convert()

    def test_page_span_mismatch_is_rejected(self):
        self.book_xml.find('./sheet/page').set('delta-measure-id', '2')
        self.write_book()
        with self.assertRaisesRegex(ValueError, 'spans'):
            self.convert()

    def test_unpitched_notes_are_retained(self):
        tree = ET.parse(self.xml)
        note = tree.find('./part[@id="P2"]/measure[@number="2"]/note')
        note.remove(note.find('pitch'))
        unpitched = ET.SubElement(note, 'unpitched')
        ET.SubElement(unpitched, 'display-step').text = 'C'
        ET.SubElement(unpitched, 'display-octave').text = '5'
        tree.write(self.xml, encoding='utf-8')
        self.assertEqual(self.convert()['validation']['unpitched_notes'], 1)


if __name__ == '__main__':
    unittest.main()
