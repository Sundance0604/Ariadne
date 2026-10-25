"""Reading windows cover the score, including distinct paragraphs on one page."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from analysis_data import build_movement_analysis,load_analysis


class MahlerAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory=ROOT/'works/mahler-4'
        cls.data=load_analysis(ROOT,cls.directory)
        cls.alignment=json.loads((cls.directory/'alignment.json').read_text(encoding='utf-8'))
        cls.mapping=json.loads((cls.directory/'measure-map.json').read_text(encoding='utf-8'))
        cls.metadata=json.loads((cls.directory/'metadata/recording.json').read_text(encoding='utf-8'))
        cls.source=ROOT/cls.metadata['analysis_document']['path']

    def test_full_source_is_live_and_all_four_chapters_are_bound(self):
        self.assertEqual(self.data['source_document']['sha256'],hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.assertIn('第四交响曲',self.data['full_html'])
        self.assertEqual(len(self.data['movement_essays']),4)
        self.assertEqual(len(self.data['annotations']),38)
        for note in self.data['movement_essays']:
            measures=[m for m in self.alignment['measures'] if m.get('movement')==note['movement']]
            self.assertEqual(note['start_measure_id'],measures[0]['measure_id'])
            self.assertEqual(note['end_measure_id'],measures[-1]['measure_id'])
            self.assertEqual(note['locator_precision'],'movement_range')
            self.assertEqual(note['review_status'],'unreviewed')
            self.assertGreater(len(note['markdown']),500)

    def test_reading_windows_are_contiguous_short_and_cover_every_score_page(self):
        notes=self.data['annotations']
        self.assertEqual(self.data['navigation_mode'],'score_segment')
        self.assertEqual(notes[0]['score_start'],[5,0,0])
        self.assertEqual(notes[-1]['score_end'],[128,0,0])
        pages=set()
        for i,note in enumerate(notes):
            self.assertLessEqual(note['end_pdf_page']-note['start_pdf_page'],4)
            self.assertGreater(len(note['markdown']),100)
            self.assertTrue(note['source_ids'])
            self.assertLess(note['start_seconds'],note['end_seconds'])
            pages.update(range(note['start_pdf_page'],note['end_pdf_page']+1))
            if i:self.assertEqual(notes[i-1]['score_end'],note['score_start'])
        self.assertEqual(pages,set(range(5,128)))
        for page in [5,80,112,115]:
            self.assertGreaterEqual(sum(n['start_pdf_page']<=page<=n['end_pdf_page'] for n in notes),2)

    def test_event_suggestions_remain_unlocated_instead_of_equal_duration_slices(self):
        self.assertEqual(len(self.data['event_candidates']),32)
        self.assertEqual(self.data['coverage']['located_event_count'],0)
        for event in self.data['event_candidates']:
            self.assertEqual(event['review_status'],'unlocated')
            for key in ['start_measure_id','end_measure_id','start_seconds','end_seconds']:
                self.assertIsNone(event[key])

    def test_references_keep_explicit_reading_statuses(self):
        self.assertGreaterEqual(len(self.data['references']),7)
        by_id={ref['source_id']:ref for ref in self.data['references']}
        self.assertEqual(by_id['mahler4-ref-6']['kind'],'chapter')
        self.assertEqual(by_id['mahler4-ref-7']['kind'],'thesis')
        self.assertIn('10.1093',by_id['mahler4-ref-6']['doi_url'])
        self.assertTrue(all(ref['reading_status'] for ref in by_id.values()))

    def test_binding_mismatch_is_rejected_and_original_is_not_rewritten(self):
        before=self.source.read_bytes()
        metadata=copy.deepcopy(self.metadata)
        metadata['recording']['audio_sha256']='another-performance'
        with self.assertRaisesRegex(ValueError,'录音'):
            build_movement_analysis(self.source,metadata,self.mapping,self.alignment)
        metadata=copy.deepcopy(self.metadata)
        metadata['analysis_document']['pdf_sha256']='another-score'
        with self.assertRaisesRegex(ValueError,'PDF'):
            build_movement_analysis(self.source,metadata,self.mapping,self.alignment)
        self.assertEqual(self.source.read_bytes(),before)


if __name__=='__main__':unittest.main()
