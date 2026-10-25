from copy import deepcopy
from pathlib import Path
import shutil
import sys
import unittest
from uuid import uuid4
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.score_processing.omr_repair import repair_book, repair_sheet
from backend.score_processing.pipeline import digest


def sheet():
    root = ET.fromstring('<sheet><system id="1"><sig><inters/><relations/></sig></system></sheet>')
    system = root.find('system')
    for n in range(1, 4):
        part = ET.SubElement(system, 'part', id=str(n))
        ET.SubElement(part, 'staff', id=str(n), left='100', right='400')
        xs = [80, 200] if n == 1 else [200]
        for i, x in enumerate(xs, 1):
            bar_id = f'b{n}-{i}'
            bar = ET.SubElement(system.find('sig/inters'), 'staff-barline', id=bar_id)
            ET.SubElement(bar, 'bounds', x=str(x), y=str(n * 100), w='2', h='60')
            measure = ET.SubElement(part, 'measure', id=str(i))
            ET.SubElement(ET.SubElement(measure, 'right-barline'), 'staff-barlines').text = bar_id
        ET.SubElement(part, 'measure', id=str(len(xs) + 1))
    for i in range(3):
        ET.SubElement(system, 'stack', id=str(i + 1), left='80', right='400')
    ET.SubElement(system.find('sig/inters'), 'head', id='h1')
    ET.SubElement(system.find('sig/inters'), 'stem', id='s1')
    ET.SubElement(system.find('sig/inters'), 'head-chord', id='c1')
    ET.SubElement(system.find('sig/relations'), 'relation', source='c1', target='h1')
    return root


class OmrRepairTests(unittest.TestCase):
    def test_phantom_before_staff_moves_to_start_and_preserves_heads(self):
        root = sheet()
        report = repair_sheet(root)
        self.assertEqual(report[0]['parts'], ['1'])
        self.assertEqual([len(p.findall('measure')) for p in root.findall('.//part')], [2, 2, 2])
        self.assertEqual(root.findtext('.//part/left-barline/staff-barlines'), 'b1-1')
        self.assertEqual(len(root.findall('.//stack')), 2)
        self.assertIsNotNone(root.find('.//head[@id="h1"]'))
        self.assertIsNotNone(root.find('.//stem[@id="s1"]'))
        self.assertIsNone(root.find('.//head-chord'))
        self.assertIsNone(root.find('.//relation'))
        self.assertEqual(repair_sheet(root), [])

    def test_real_pickup_inside_staff_is_not_removed(self):
        root = sheet()
        root.find('.//staff-barline[@id="b1-1"]/bounds').set('x', '120')
        before = ET.tostring(root)
        self.assertEqual(repair_sheet(root), [])
        self.assertEqual(ET.tostring(root), before)

    def test_nonempty_leading_measure_is_not_removed(self):
        root = sheet()
        ET.SubElement(root.find('.//part/measure'), 'head-chords').text = 'c1'
        self.assertEqual(repair_sheet(root), [])

    def test_rhythm_processed_stacks_are_not_rewritten(self):
        root = sheet()
        ET.SubElement(root.find('.//stack'), 'slot')
        self.assertEqual(repair_sheet(root), [])

    def test_book_repair_preserves_original_and_completed_pages(self):
        folder = ROOT / 'tmp' / f'omr-repair-test-{uuid4().hex}'
        folder.mkdir(parents=True)
        self.addCleanup(lambda: self.cleanup(folder))
        original, output = folder / 'source.omr', folder / 'output.omr'
        completed = ET.tostring(sheet())
        with zipfile.ZipFile(original, 'w') as z:
            z.writestr('book.xml', '<book><sheet number="1"><steps>MEASURES CHORDS PAGE</steps></sheet>'
                        '<sheet number="2"><steps>MEASURES</steps></sheet></book>')
            z.writestr('sheet#1/sheet#1.xml', completed)
            z.writestr('sheet#2/sheet#2.xml', ET.tostring(sheet()))
            z.writestr('sheet#2/BINARY.png', b'unchanged image data')
        original_sha = digest(original)
        result = repair_book(original, output)
        self.assertEqual(result['changes'][0]['sheet'], 2)
        self.assertEqual(digest(original), original_sha)
        with zipfile.ZipFile(output) as z:
            self.assertEqual(z.read('sheet#1/sheet#1.xml'), completed)
            self.assertEqual(z.read('sheet#2/BINARY.png'), b'unchanged image data')
        with self.assertRaises(ValueError):
            repair_book(original, original)

    def cleanup(self, folder):
        self.assertEqual(folder.resolve().parent, (ROOT / 'tmp').resolve())
        shutil.rmtree(folder)


if __name__ == '__main__':
    unittest.main()
