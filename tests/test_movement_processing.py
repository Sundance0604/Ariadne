from pathlib import Path
import json
import shutil
import sys
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.score_processing.movements import book_progress, load_manifest, prepare_image_book, transcribe_movement
from backend.score_processing.pipeline import digest

XML = b'''<score-partwise version="4.0"><part-list><score-part id="P1"><part-name>Flute</part-name>
</score-part></part-list><part id="P1"><measure number="1"><attributes><divisions>1</divisions>
<time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration></note>
</measure></part></score-partwise>'''


def make_book(path, source, pages, missing_data=(), invalid=()):
    body = ''.join(f'<sheet number="{n}" invalid="{str(n in invalid).lower()}">'
                   '<steps>LOAD GRID PAGE</steps></sheet>' for n in pages)
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('book.xml', f'<book path="{source}">{body}</book>')
        for n in pages:
            if n not in missing_data:
                z.writestr(f'sheet#{n}/sheet#{n}.xml', '<sheet/>')


class MovementTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / 'tmp' / f'movement-test-{uuid4().hex}'
        self.root.mkdir(parents=True)
        self.addCleanup(self.cleanup)
        self.pdf = self.root / 'input.pdf'
        self.pdf.write_bytes(b'fake PDF test double')
        self.engine = self.root / 'engine.exe'
        self.engine.write_bytes(b'fake engine')
        self.movement = {'number': 1, 'start_page': 1, 'end_page': 4, 'page_count': 4}
        self.manifest = {'pdf': str(self.pdf), 'pdf_sha256': digest(self.pdf), 'pdf_pages': 4,
                         'movements': [self.movement]}

    def cleanup(self):
        target = self.root.resolve()
        self.assertEqual(target.parent, (ROOT / 'tmp').resolve())
        shutil.rmtree(target)

    def fake_engine(self, command, log, env, timeout):
        start, end = map(int, command[command.index('-sheets') + 1].split('-'))
        folder = Path(command[command.index('-output') + 1])
        input_path = Path(command[-1])
        book_name = input_path.name if input_path.suffix == '.omr' else 'score.omr'
        make_book(folder / book_name, self.pdf, range(start, end + 1))
        with zipfile.ZipFile(folder / 'score.mxl', 'w') as z:
            z.writestr('META-INF/container.xml', '<container><rootfiles><rootfile full-path="score.xml" '
                        'media-type="application/vnd.recordare.musicxml+xml"/></rootfiles></container>')
            z.writestr('score.xml', XML)
        log.write_text('test double', encoding='utf8')

    def convert(self, **kwargs):
        with patch('backend.score_processing.movements.ROOT', self.root), \
             patch('backend.score_processing.movements.find_audiveris', return_value=self.engine), \
             patch('backend.score_processing.movements.prepare_image_book', return_value=self.pdf):
            return transcribe_movement(self.manifest, self.movement, self.root / 'output',
                                       batch_size=2, retries=0, **kwargs)

    def test_manifest_requires_exact_coverage(self):
        path = self.root / 'manifest.json'
        path.write_text(json.dumps(self.manifest))
        self.assertEqual(load_manifest(path)['pdf_pages'], 4)
        self.manifest['movements'][0]['start_page'] = 2
        self.manifest['movements'][0]['page_count'] = 3
        path.write_text(json.dumps(self.manifest))
        with self.assertRaises(ValueError):
            load_manifest(path)

    def test_step_without_sheet_data_and_invalid_page_are_not_completed(self):
        path = self.root / 'score.omr'
        make_book(path, self.pdf, [1, 2, 3], missing_data=[2], invalid=[3])
        progress = book_progress(path, 1, 4)
        self.assertEqual(progress['completed_pages'], [1])
        self.assertEqual(progress['invalid_pages'], [3])
        self.assertEqual(progress['pending_pages'], [2, 4])

    def test_streamed_tiff_pages_and_verified_cache(self):
        from PIL import Image
        folder = self.root / 'tiff-test'
        folder.mkdir()
        document = MagicMock()
        raster = document.__getitem__.return_value.render.return_value
        raster.to_pil.side_effect = lambda: Image.new('RGB', (24, 32), 'white')
        with patch('pypdfium2.PdfDocument') as pdfium:
            pdfium.return_value.__enter__.return_value = document
            image_book = prepare_image_book(self.pdf, self.movement, folder, 450, digest(self.pdf))
            with Image.open(image_book) as picture:
                self.assertEqual(picture.n_frames, 4)
                self.assertEqual(picture.mode, 'L')
            prepare_image_book(self.pdf, self.movement, folder, 450, digest(self.pdf))
            self.assertEqual(pdfium.call_count, 1)
            image_book.write_bytes(image_book.read_bytes() + b'changed')
            prepare_image_book(self.pdf, self.movement, folder, 450, digest(self.pdf))
            self.assertEqual(pdfium.call_count, 2)

    @patch('backend.score_processing.movements.run_command')
    def test_movement_local_sheet_numbers_map_to_physical_pdf_pages(self, run):
        self.movement.update(start_page=81, end_page=84)
        run.side_effect = self.fake_engine
        first = self.convert(through_page=82)
        self.assertEqual(first['completed_pages'], [81, 82])
        second = self.convert()
        self.assertEqual(second['source_pages_in_export'], [81, 82, 83, 84])
        self.assertEqual(second['status'], 'converted_needs_review')
        command = run.call_args.args[0]
        self.assertEqual(command[command.index('-sheets') + 1], '1-4')

    @patch('backend.score_processing.movements.run_command')
    def test_cumulative_export_and_resume_preserve_snapshot(self, run):
        run.side_effect = self.fake_engine
        first = self.convert(through_page=2)
        self.assertEqual(first['status'], 'partial_needs_review')
        original_sha = digest(first['omr'])
        second = self.convert()
        self.assertEqual(second['status'], 'converted_needs_review')
        self.assertEqual(second['source_pages_in_export'], [1, 2, 3, 4])
        self.assertEqual(Path(run.call_args.args[0][-1]).suffix, '.omr')
        self.assertEqual(digest(first['omr']), original_sha)
        self.assertFalse(second['musical_accuracy_verified'])

    @patch('backend.score_processing.movements.run_command')
    def test_engine_exit_zero_with_missing_page_is_failure(self, run):
        def incomplete(command, log, env, timeout):
            self.fake_engine(command, log, env, timeout)
            folder = Path(command[command.index('-output') + 1])
            make_book(folder / 'score.omr', self.pdf, [1])
        run.side_effect = incomplete
        result = self.convert(through_page=2)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['completed_pages'], [1])

    @patch('backend.score_processing.movements.run_command')
    def test_fragments_are_not_reported_as_single_movement(self, run):
        def fragmented(command, log, env, timeout):
            self.fake_engine(command, log, env, timeout)
            folder = Path(command[command.index('-output') + 1])
            shutil.copy2(folder / 'score.mxl', folder / 'score-second.mxl')
        run.side_effect = fragmented
        result = self.convert()
        self.assertEqual(result['status'], 'fragmented_needs_review')
        self.assertEqual(result['export_fragment_count'], 2)

    @patch('backend.score_processing.movements.run_command')
    def test_input_fingerprint_rejected(self, run):
        self.pdf.write_bytes(b'changed')
        with self.assertRaises(ValueError):
            self.convert()
        run.assert_not_called()

    @patch('backend.score_processing.movements.run_command')
    def test_explicit_reviewed_resume_book_takes_priority_over_old_snapshots(self, run):
        run.side_effect = self.fake_engine
        self.convert(through_page=2)
        reviewed = self.root / 'reviewed.omr'
        make_book(reviewed, self.pdf, [1, 2, 3, 4])
        previous_calls = run.call_count
        result = self.convert(resume_book=reviewed)
        first_resumed_command = run.call_args_list[previous_calls].args[0]
        self.assertEqual(Path(first_resumed_command[-1]).name, 'reviewed.omr')
        self.assertEqual(result['status'], 'converted_needs_review')


if __name__ == '__main__':
    unittest.main()
