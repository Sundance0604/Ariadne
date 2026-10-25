"""Offline tests for result validation, recovery and cache integrity (no OMR engine)."""
import json
import os
from pathlib import Path
import sys
import shutil
import unittest
from unittest.mock import MagicMock, patch
import zipfile
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.score_processing.musicxml import inspect_musicxml, read_musicxml
from backend.score_processing.pipeline import _convert_page, run_command, select_pages

XML = b'''<?xml version="1.0"?>
<score-partwise version="4.0"><part-list><score-part id="P1">
<part-name>Test</part-name></score-part></part-list><part id="P1">
<measure number="1"><attributes><divisions>2</divisions>
<time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>8</duration><voice>1</voice></note>
<note><chord/><pitch><step>E</step><octave>4</octave></pitch><duration>8</duration><voice>1</voice></note>
<backup><duration>8</duration></backup>
<note><rest/><duration>8</duration><voice>2</voice></note>
</measure></part></score-partwise>'''


class WorkspaceTemp:
    # Windows Python's mkdtemp(mode=0700) excludes the restricted runner's SID.
    # Use a randomly named, normally inherited workspace directory instead.
    def __init__(self):
        self.path = ROOT / 'tmp' / f'score-processing-test-{uuid4().hex}'
        self.path.mkdir(parents=True)
        self.name = str(self.path)

    def cleanup(self):
        target = self.path.resolve()
        if target.parent != (ROOT / 'tmp').resolve():
            raise ValueError('Test cleanup target is outside workspace tmp')
        shutil.rmtree(target)


def write_mxl(path, data=XML):
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('META-INF/container.xml', '''<container
        xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>
        <rootfile full-path="score.xml" media-type="application/vnd.recordare.musicxml+xml"/>
        </rootfiles></container>''')
        archive.writestr('score.xml', data)


class ValidationTests(unittest.TestCase):
    def setUp(self):
        (ROOT / 'tmp').mkdir(exist_ok=True)
        self.temp = WorkspaceTemp()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'test.mxl'

    def test_mxl_container_chords_and_backups(self):
        write_mxl(self.path)
        report = inspect_musicxml(self.path, 1, 1)
        self.assertTrue(report['structurally_valid'])
        self.assertEqual(report['pitched_notes'], 2)
        self.assertEqual(report['rests'], 1)
        self.assertEqual(report['issue_count'], 0)
        self.assertFalse(report['musical_accuracy_verified'])

    def test_missing_meter_is_reported_not_assumed(self):
        write_mxl(self.path, XML.replace(b'<time><beats>4</beats><beat-type>4</beat-type></time>', b''))
        report = inspect_musicxml(self.path)
        self.assertEqual(report['time_signatures'], [])
        self.assertIn('missing_time_signature', [i['kind'] for i in report['issues']])

    def test_rhythm_and_staff_mismatches_flagged(self):
        write_mxl(self.path, XML.replace(b'<duration>8</duration>', b'<duration>6</duration>'))
        report = inspect_musicxml(self.path, 17, 4)
        self.assertEqual({i['kind'] for i in report['issues']},
                         {'voice_extent_differs_from_meter', 'staff_count_mismatch',
                          'measure_count_mismatch'})

    def test_no_notes_and_bad_container_fail(self):
        write_mxl(self.path, b'<score-partwise><part-list/></score-partwise>')
        self.assertFalse(inspect_musicxml(self.path)['structurally_valid'])
        with zipfile.ZipFile(self.path, 'w') as archive:
            archive.writestr('META-INF/container.xml', '<container/>')
        with self.assertRaises(ValueError):
            read_musicxml(self.path)

    def test_plain_musicxml_and_namespaces(self):
        self.path.write_bytes(XML.replace(b'<score-partwise version="4.0">',
                                         b'<score-partwise xmlns="urn:example" version="4.0">'))
        self.assertEqual(inspect_musicxml(self.path)['part_count'], 1)

    def test_streamed_and_in_memory_validation_agree(self):
        write_mxl(self.path)
        standard = inspect_musicxml(self.path, 1, 1)
        with patch('backend.score_processing.musicxml.STREAM_THRESHOLD', 0):
            self.assertEqual(inspect_musicxml(self.path, 1, 1), standard)

    def test_stream_accepts_an_all_rest_part_when_other_parts_sound(self):
        _, root = read_musicxml(self._stream_fixture())
        import copy
        rest_part = copy.deepcopy(root.find('part'))
        rest_part.set('id', 'P2')
        for note in rest_part.findall('.//note'):
            pitch = note.find('pitch')
            if pitch is not None:
                note.remove(pitch)
                import xml.etree.ElementTree as ET
                note.insert(0, ET.Element('rest'))
        root.append(rest_part)
        definition = copy.deepcopy(root.find('./part-list/score-part'))
        definition.set('id', 'P2')
        root.find('part-list').append(definition)
        import xml.etree.ElementTree as ET
        self.path.write_bytes(ET.tostring(root, encoding='utf-8'))
        normal = inspect_musicxml(self.path)
        with patch('backend.score_processing.musicxml.STREAM_THRESHOLD', 0):
            self.assertEqual(inspect_musicxml(self.path), normal)
            self.assertTrue(inspect_musicxml(self.path)['structurally_valid'])

    def _stream_fixture(self):
        write_mxl(self.path)
        return self.path

    def test_page_ranges(self):
        self.assertEqual(select_pages('1,3-5,3', 5), [1, 3, 4, 5])
        self.assertEqual(select_pages(None, 2), [1, 2])
        for value in ('0', '6', '3-1', '', '1-2-3'):
            with self.assertRaises(ValueError):
                select_pages(value, 5)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        (ROOT / 'tmp').mkdir(exist_ok=True)
        self.temp = WorkspaceTemp()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / 'page'
        from PIL import Image
        self.document = MagicMock()
        self.document.__getitem__.return_value.render.return_value.to_pil.side_effect = (
            lambda: Image.new('RGB', (10, 10), 'white'))

    def convert(self, **kwargs):
        return _convert_page(self.document, 1, self.folder, Path('fake-engine'), {}, 300,
                             kwargs.get('retries', 0), 10, kwargs.get('force', False),
                             1, 1, kwargs.get('musescore'))

    def success(self, command, log, env, timeout):
        log.write_text('successful test double', encoding='utf8')
        folder = Path(command[command.index('-output') + 1])
        write_mxl(folder / 'test.mxl')
        (folder / 'test.omr').write_bytes(b'test-double-project')

    @patch('backend.score_processing.pipeline.run_command')
    def test_cache_revalidation_and_tampered_output_rebuild(self, run):
        run.side_effect = self.success
        first = self.convert()
        self.assertEqual(first['status'], 'converted_needs_review')
        self.assertTrue(self.convert()['cache_hit'])
        self.assertEqual(run.call_count, 1)
        Path(first['musicxml'][0]).write_text('corrupted', encoding='utf8')
        rebuilt = self.convert()
        self.assertFalse(rebuilt['cache_hit'])
        self.assertEqual(run.call_count, 2)
        self.assertNotEqual(first['attempt'], rebuilt['attempt'])

    @patch('backend.score_processing.pipeline.run_command')
    def test_failed_partial_export_does_not_satisfy_retry(self, run):
        def fail_then_succeed(command, log, env, timeout):
            if run.call_count == 1:
                folder = Path(command[command.index('-output') + 1])
                write_mxl(folder / 'partial.mxl')
                raise RuntimeError('simulated crash after partial export')
            self.success(command, log, env, timeout)
        run.side_effect = fail_then_succeed
        result = self.convert(retries=1)
        self.assertEqual(result['status'], 'converted_needs_review')
        self.assertEqual(len(result['previous_failures']), 1)
        self.assertTrue((self.folder / 'attempt-001/failure.json').exists())
        self.assertIn('attempt-002', result['mxl'][0])

    @patch('backend.score_processing.pipeline.run_command')
    def test_exhausted_failure_saved_and_repeatable(self, run):
        run.side_effect = RuntimeError('simulated timeout')
        result = self.convert(retries=1)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(len(result['previous_failures']), 2)
        self.assertEqual(json.loads((self.folder / 'result.json').read_text())['status'], 'failed')
        run.side_effect = self.success
        self.assertEqual(self.convert()['status'], 'converted_needs_review')

    @patch('backend.score_processing.pipeline.run_command')
    def test_renderer_exit_zero_without_images_is_failure(self, run):
        def engine_only(command, log, env, timeout):
            if command[0] == Path('fake-engine'):
                self.success(command, log, env, timeout)
            else:
                log.write_text('renderer returned no output', encoding='utf8')
        run.side_effect = engine_only
        result = self.convert(musescore=Path('fake-musescore'))
        self.assertEqual(result['status'], 'converted_needs_review')
        self.assertEqual(result['render']['status'], 'failed')
        self.assertFalse(self.convert(musescore=Path('fake-musescore'))['cache_hit'])


class ProcessTests(unittest.TestCase):
    def test_timeout_stops_spawned_child(self):
        import time
        temp = WorkspaceTemp()
        self.addCleanup(temp.cleanup)
        ready, finished = temp.path / 'ready.txt', temp.path / 'finished.txt'
        child = (f'from pathlib import Path; import time; Path({str(ready)!r}).write_text("ready"); '
                 f'time.sleep(2); Path({str(finished)!r}).write_text("unexpected")')
        parent = (f'import subprocess,sys,time; subprocess.Popen([sys.executable,"-c",{child!r}]); '
                  'time.sleep(10)')
        with self.assertRaisesRegex(RuntimeError, 'timed out'):
            run_command([sys.executable, '-c', parent], temp.path / 'timeout.log',
                        os.environ.copy(), 1)
        self.assertTrue(ready.exists(), 'Child should start before timeout')
        time.sleep(2.1)
        self.assertFalse(finished.exists(), 'Child must stop with the launcher')


if __name__ == '__main__':
    unittest.main()
