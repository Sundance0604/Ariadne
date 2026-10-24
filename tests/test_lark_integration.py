"""Validate the supplied Lark package and its listener-copy bindings."""
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from analysis_data import load_analysis
from review_library import track_context,page_count


class LarkIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _,cls.directory=track_context(ROOT,'lark-ascending')
        cls.alignment=json.loads((cls.directory/'alignment.json').read_text(encoding='utf-8'))
        cls.mapping=json.loads((cls.directory/'measure-map.json').read_text(encoding='utf-8'))
        cls.analysis=load_analysis(ROOT,cls.directory)

    def test_regions_belong_to_real_candidates_and_missing_positions_are_flagged(self):
        measures=self.alignment['measures'];regions=self.mapping['measures']
        self.assertEqual(len({m['measure_id'] for m in measures}),len(measures))
        mapped={m['measure_id'] for m in regions}
        self.assertTrue(mapped.issubset({m['measure_id'] for m in measures}))
        for measure in measures:
            if measure['measure_id'] not in mapped:self.assertIn('pdf_coordinate_missing',measure['flags'])
        self.assertEqual(page_count(self.mapping),35)
        self.assertEqual({m['page_number'] for m in regions},set(range(1,36)))
        for m in measures:
            self.assertGreater(m['end_seconds'],m['start_seconds'])
            self.assertGreater(m['midi_end_seconds'],m['midi_start_seconds'])
        self.assertEqual([m['start_seconds'] for m in measures],sorted(m['start_seconds'] for m in measures))

    def test_listener_copy_covers_the_bound_score_and_recording(self):
        data=self.analysis
        self.assertEqual(data['coverage']['missing_pages'],[])
        self.assertEqual(data['coverage']['pdf_pages'],35)
        pages=[p for note in data['annotations'] for p in range(note['start_pdf_page'],note['end_pdf_page']+1)]
        self.assertEqual(pages,list(range(1,36)))
        self.assertEqual(data['source_document']['review_status'],'editorially_revised')
        self.assertEqual(data['recording']['soloists'][0]['original_name'],'Hilary Hahn')
        self.assertIn('Colin Davis',data['recording']['conductor']['original_name'])
        self.assertNotEqual(data['audio_sha256'],load_analysis(ROOT)['audio_sha256'])
        for note in data['annotations']:
            for phrase in ['核验任务','逐页检查','不要未经','必须核对','建议聆听时比较']:
                self.assertNotIn(phrase,note['markdown'])


if __name__=='__main__':unittest.main()
